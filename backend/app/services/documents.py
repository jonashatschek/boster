"""Receiving, storing and analysing cooperative documents.

Uploaded files and downloaded documents are untrusted input. We only accept PDFs,
limit their size, never execute anything inside them, and treat their text purely
as data.
"""

import hashlib
from enum import StrEnum
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.documents.annual_report import AnnualReportExtraction, DocumentType, extract_annual_report
from app.domain.metrics import METRICS
from app.domain.provenance import VerificationStatus
from app.models import DocumentFinding, FinancialObservation, HousingCooperative, SourceDocument
from app.net_safety import UnsafeUrlError, check_public_http_url, reject_private_host
from app.services.properties import link_matching_properties


class ExtractionStatus(StrEnum):
    SUCCEEDED = "succeeded"  # Figures were found.
    PARTIAL = "partial"  # The document was read, but few or no figures were found.
    NEEDS_OCR = "needs_ocr"  # Mostly scanned images.
    FAILED = "failed"  # The file could not be read at all.


class DocumentError(Exception):
    """A problem the user can act on. The message is shown in the UI, in Swedish."""


_PDF_MAGIC = b"%PDF-"


def ingest_pdf(session: Session, settings: Settings, content: bytes, filename: str,
               document_url: str | None = None) -> SourceDocument:
    """Store and analyse a PDF. Returns the existing document if the same file was uploaded before."""
    if len(content) > settings.max_document_bytes:
        raise DocumentError(f"Filen är för stor (max {settings.max_document_bytes // (1024 * 1024)} MB).")
    if not content.startswith(_PDF_MAGIC):
        raise DocumentError("Filen är inte en PDF.")

    sha256 = hashlib.sha256(content).hexdigest()
    existing = session.scalar(select(SourceDocument).where(SourceDocument.sha256 == sha256))
    if existing:
        return existing

    settings.document_directory.mkdir(parents=True, exist_ok=True)
    file_name = f"{sha256}.pdf"
    (settings.document_directory / file_name).write_bytes(content)

    document = SourceDocument(
        original_filename=_safe_filename(filename), document_url=document_url, sha256=sha256,
        file_name=file_name, document_type=DocumentType.OTHER.value,
        extraction_status=ExtractionStatus.FAILED.value, extraction_messages=[],
    )
    session.add(document)

    try:
        extraction = extract_annual_report(content)
    except Exception:  # A malformed PDF must not take the application down.
        document.extraction_messages = ["Dokumentet kunde inte läsas. Filen kan vara skadad eller krypterad."]
        session.commit()
        return document

    _apply_extraction(session, document, extraction)
    session.commit()
    return document


def download_pdf(settings: Settings, url: str) -> tuple[bytes, str]:
    """Download a PDF from a public URL. Returns (content, filename)."""
    try:
        check_public_http_url(url)
    except UnsafeUrlError as error:
        raise DocumentError(str(error)) from error

    try:
        with httpx.Client(timeout=settings.document_download_timeout_seconds, follow_redirects=True) as client:
            with client.stream("GET", url, headers={"User-Agent": "Boster/0.1 (personal use)"}) as response:
                if response.status_code in (401, 403):
                    raise DocumentError("Sidan kräver inloggning eller nekar åtkomst. Ladda ner filen och ladda upp den här.")
                if response.status_code >= 400:
                    raise DocumentError(f"Dokumentet kunde inte hämtas (HTTP {response.status_code}).")
                try:
                    reject_private_host(response.url.host)  # After redirects.
                except UnsafeUrlError as error:
                    raise DocumentError(str(error)) from error
                content = bytearray()
                for chunk in response.iter_bytes():
                    content += chunk
                    if len(content) > settings.max_document_bytes:
                        raise DocumentError("Dokumentet är för stort.")
    except httpx.TimeoutException as error:
        raise DocumentError("Det tog för lång tid att hämta dokumentet. Försök igen eller ladda upp filen.") from error
    except httpx.HTTPError as error:
        raise DocumentError("Dokumentet kunde inte hämtas. Kontrollera länken.") from error

    filename = unquote(Path(urlparse(str(response.url)).path).name) or "dokument.pdf"
    return bytes(content), filename


def reassign_document(session: Session, document: SourceDocument, cooperative: HousingCooperative) -> None:
    """Move a document, and the figures read from it, to another cooperative (correcting a wrong match)."""
    document.cooperative = cooperative
    for observation in document.observations:
        observation.cooperative = cooperative
    session.commit()


def delete_document(session: Session, settings: Settings, document: SourceDocument) -> None:
    path = settings.document_directory / document.file_name
    session.delete(document)
    session.commit()
    path.unlink(missing_ok=True)


def document_path(settings: Settings, document: SourceDocument) -> Path:
    return settings.document_directory / document.file_name


def _apply_extraction(session: Session, document: SourceDocument, extraction: AnnualReportExtraction) -> None:
    document.document_type = extraction.document_type.value
    document.page_count = extraction.page_count
    document.reporting_year = extraction.fiscal_year
    document.fiscal_period_start = extraction.fiscal_period_start
    document.fiscal_period_end = extraction.fiscal_period_end
    document.extraction_messages = list(extraction.warnings)

    if extraction.looks_scanned:
        document.extraction_status = ExtractionStatus.NEEDS_OCR.value
    elif len(extraction.figures) >= 5:
        document.extraction_status = ExtractionStatus.SUCCEEDED.value
    else:
        document.extraction_status = ExtractionStatus.PARTIAL.value
        if extraction.document_type == DocumentType.ANNUAL_REPORT:
            document.extraction_messages.append(
                "Få eller inga nyckeltal kunde läsas automatiskt. Ange viktiga uppgifter manuellt."
            )

    cooperative = _find_or_create_cooperative(session, extraction)
    document.cooperative = cooperative
    if cooperative is None:
        document.extraction_messages.append(
            "Ingen förening kunde identifieras i dokumentet. Koppla dokumentet till en förening manuellt."
        )
        return

    if extraction.land_tenure and cooperative.land_tenure is None:
        cooperative.land_tenure = extraction.land_tenure.value
        evidence = extraction.land_tenure_evidence
        cooperative.land_tenure_source = f"{document.original_filename}, s. {evidence.page_number}: ”{evidence.excerpt}”"

    for figure in extraction.figures:
        session.add(FinancialObservation(
            cooperative=cooperative, source_document=document, metric_key=figure.metric_key,
            fiscal_year=figure.fiscal_year, value=figure.value, unit=METRICS[figure.metric_key].unit.value,
            source_page=figure.page_number, printed_label=figure.printed_label,
            extraction_method=figure.method.value, verification_status=VerificationStatus.EXTRACTED.value,
            note=figure.note,
        ))
    for finding in extraction.findings:
        document.findings.append(DocumentFinding(topic=finding.topic, page_number=finding.page_number,
                                                 excerpt=finding.excerpt))


def _find_or_create_cooperative(session: Session, extraction: AnnualReportExtraction) -> HousingCooperative | None:
    """Match on organisation number only. Similar names are never merged automatically."""
    if extraction.organisation_number:
        cooperative = session.scalar(select(HousingCooperative).where(
            HousingCooperative.organisation_number == extraction.organisation_number))
        if cooperative:
            return cooperative
    if not extraction.organisation_number and not extraction.cooperative_name:
        return None
    cooperative = HousingCooperative(
        organisation_number=extraction.organisation_number,
        name=extraction.cooperative_name or f"Förening {extraction.organisation_number}",
    )
    session.add(cooperative)
    link_matching_properties(session, cooperative)
    return cooperative


def _safe_filename(filename: str) -> str:
    name = Path(filename.replace("\\", "/")).name.strip() or "dokument.pdf"
    return name[:200]
