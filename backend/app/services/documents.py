"""Receiving, storing and analysing cooperative documents.

Uploaded files are untrusted input. We only accept PDFs, limit their size, never
execute anything inside them, and treat their text purely as data. The PDF is read
by pdf.js in the browser; this module receives its text page by page.
"""

import hashlib
from enum import StrEnum
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.documents.annual_report import AnnualReportExtraction, DocumentType, extract_annual_report
from app.documents.pdf_layout import PageText
from app.domain.metrics import METRICS
from app.domain.provenance import VerificationStatus
from app.models import DocumentFinding, FinancialObservation, HousingCooperative, SourceDocument
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
               pages: list[PageText] | None) -> SourceDocument:
    """Store and analyse a PDF. Returns the existing document if the same file was uploaded before.

    `pages` is None when the browser could not read the PDF; the file is then stored but not analysed.
    """
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
        original_filename=_safe_filename(filename), sha256=sha256,
        file_name=file_name, document_type=DocumentType.OTHER.value,
        extraction_status=ExtractionStatus.FAILED.value, extraction_messages=[],
    )
    session.add(document)

    try:
        if pages is None:
            raise ValueError("No page text.")
        extraction = extract_annual_report(pages)
    except Exception:  # A malformed PDF must not take the application down.
        document.extraction_messages = ["Dokumentet kunde inte läsas. Filen kan vara skadad eller krypterad."]
        session.commit()
        return document

    _apply_extraction(session, document, extraction)
    session.commit()
    return document


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
