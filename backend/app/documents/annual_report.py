"""Extraction of structured facts from a housing cooperative's annual report (årsredovisning).

The extractor is deliberately conservative. It only reports a figure when a row
label matches a known pattern and the number sits under a recognised year column,
and it records the page and printed label for every value. Anything it is unsure
about becomes a warning, never a guess.
"""

import re
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date
from enum import StrEnum

import pymupdf

from app.domain.metrics import METRICS, AreaBasis, Unit
from app.domain.provenance import ExtractionMethod, ValueOrigin
from app.documents.number_parsing import parse_swedish_number
from app.documents.pdf_layout import PageLayout, read_layout
from app.documents.period_tables import PeriodTableRow, TextRow, clean_label, read_document_rows

# Pages with less text than this are probably scanned images.
_MIN_CHARACTERS_FOR_TEXT_PAGE = 200


class DocumentType(StrEnum):
    ANNUAL_REPORT = "annual_report"
    ECONOMIC_PLAN = "economic_plan"
    MAINTENANCE_PLAN = "maintenance_plan"
    OTHER = "other"


class LandTenure(StrEnum):
    OWNED = "owned"  # Äganderätt / friköpt tomt.
    LEASEHOLD = "leasehold"  # Tomträtt.


@dataclass(frozen=True)
class ExtractedFigure:
    metric_key: str
    fiscal_year: int
    value: float
    page_number: int
    printed_label: str  # The row label exactly as read from the document.
    method: ExtractionMethod
    origin: ValueOrigin
    note: str | None = None


@dataclass(frozen=True)
class TextFinding:
    """A passage that mentions a topic of interest. Quoted, not interpreted."""

    topic: str
    page_number: int
    excerpt: str


@dataclass
class AnnualReportExtraction:
    page_count: int
    text_page_count: int
    document_type: DocumentType
    organisation_number: str | None = None
    cooperative_name: str | None = None
    fiscal_year: int | None = None
    fiscal_period_start: date | None = None
    fiscal_period_end: date | None = None
    land_tenure: LandTenure | None = None
    land_tenure_evidence: TextFinding | None = None
    figures: list[ExtractedFigure] = field(default_factory=list)
    findings: list[TextFinding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def looks_scanned(self) -> bool:
        return self.page_count > 0 and self.text_page_count / self.page_count < 0.5


# --- Row label patterns --------------------------------------------------------------
# Labels are matched after lower-casing and removing footnote markers. Order matters:
# the first matching pattern wins, so the more specific patterns come first.

_KEY_FIGURE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("debt_per_sqm_tenant_owned_area",
     re.compile(r"(skulds[äa]ttning|föreningslån).*(bostadsr[äa]tt|brf|br-yta|upplåten|boyta)")),
    ("debt_per_sqm_total_area", re.compile(r"skulds[äa]ttning|föreningslån.*(kvm|m2|m²)")),
    ("savings_per_sqm", re.compile(r"^sparande")),
    ("interest_sensitivity_pct", re.compile(r"r[äa]ntek[äa]nslighet")),
    ("energy_cost_per_sqm", re.compile(r"energikostnad")),
    ("fee_share_of_revenue_pct", re.compile(r"(årsavgift.*(andel|/\s*totala))|(andel.*årsavgift)")),
    ("annual_fee_per_sqm", re.compile(r"årsavgift.*(kvm|m2|m²)")),
    ("solidity_pct", re.compile(r"^soliditet")),
    ("net_revenue", re.compile(r"^nettoomsättning")),
    ("result_after_financial_items", re.compile(r"^res(ultat|\.)?\s*ef(ter|\.)?\s*fin")),
    ("total_assets", re.compile(r"^balansomslutning")),
]
# Some templates say "boyta" (residential area) where the mandatory key figure is per
# tenant-owned area. The two only differ when the cooperative has rental apartments.
_BOYTA_NOTE = "Redovisat per kvm boyta i dokumentet. Tolkat som yta upplåten med bostadsrätt."

_INCOME_STATEMENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("net_revenue", re.compile(r"^nettoomsättning$")),
    ("operating_result", re.compile(r"^rörelseresultat$")),
    ("result_after_financial_items", re.compile(r"^resultat efter finansiella poster$")),
    ("annual_result", re.compile(r"^årets resultat$")),
    ("depreciation", re.compile(r"^(avskrivningar|av- och nedskrivningar)\b")),
    ("interest_expense", re.compile(r"^räntekostnader och liknande resultatposter$")),
]

_BALANCE_SHEET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("total_assets", re.compile(r"^summa tillgångar$")),
    ("equity", re.compile(r"^summa eget kapital$")),
    ("cash", re.compile(r"^summa kassa och bank$")),
]
_CASH_ROW = re.compile(r"^kassa och bank$")
_CREDIT_INSTITUTION_DEBT_ROW = re.compile(
    r"^(övriga\s+)?(långfristiga\s+|kortfristiga\s+)?skulde?r?\s+till\s+kreditinstitut(,\s*\w+)?$"
)

# Rows that identify what kind of page we are looking at.
_INCOME_STATEMENT_SIGNATURE = re.compile(r"^rörelseresultat$")
_BALANCE_SHEET_SIGNATURE = re.compile(r"^(summa tillgångar|summa eget kapital|summa eget kapital och skulder)$")
_CASH_FLOW_SIGNATURE = re.compile(r"likvida medel vid årets|erlagd ränta|kassaflöde från")

# Metrics whose sign in the statements is negative but which we store as positive costs.
_STORED_AS_POSITIVE = {"interest_expense", "depreciation"}

# Key figures that cannot plausibly be zero. Several report templates print 0 for years
# before the figure became mandatory, so a zero here means "not reported".
_ZERO_MEANS_NOT_REPORTED = {
    "debt_per_sqm_tenant_owned_area", "fee_share_of_revenue_pct", "annual_fee_per_sqm", "energy_cost_per_sqm",
}

# --- Topics for quoted passages -----------------------------------------------------------

_TOPICS: list[tuple[str, re.Pattern]] = [
    ("Stambyte", re.compile(r"stambyte|stamrenovering|relining|stambyten", re.IGNORECASE)),
    ("Tak", re.compile(r"\btak(renovering|byte|omläggning|et)?\b|takomläggning", re.IGNORECASE)),
    ("Fasad", re.compile(r"fasad", re.IGNORECASE)),
    ("Fönster", re.compile(r"fönster", re.IGNORECASE)),
    ("Hiss", re.compile(r"\bhiss(ar|en|arna|renovering|byte)?\b", re.IGNORECASE)),
    ("Dränering", re.compile(r"dränering", re.IGNORECASE)),
    ("Balkonger", re.compile(r"balkong", re.IGNORECASE)),
    ("Ventilation", re.compile(r"ventilation|\bovk\b", re.IGNORECASE)),
    ("Underhållsplan", re.compile(r"underhållsplan", re.IGNORECASE)),
    ("Avgiftsförändringar", re.compile(
        r"(höj|sänk)\w*\s+(års|månads)?avgift|(års|månads)avgift\w*\s+(höj|sänk)|avgiftshöjning|avgiftssänkning",
        re.IGNORECASE)),
    ("Lån och omförhandling", re.compile(r"nyupplåning|nya lån|omförhandl|villkorsändr|amorter", re.IGNORECASE)),
    ("Revisorns uttalanden", re.compile(r"med reservation|avstyrker|anmärkning", re.IGNORECASE)),
]
_MAX_FINDINGS_PER_TOPIC = 8


def extract_annual_report(pdf_bytes: bytes) -> AnnualReportExtraction:
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
        pages = read_layout(document)
    return extract_from_pages(pages)


def extract_from_pages(pages: list[PageLayout]) -> AnnualReportExtraction:
    text_pages = [p for p in pages if len(p.text.strip()) >= _MIN_CHARACTERS_FOR_TEXT_PAGE]
    full_text = "\n".join(p.text for p in pages)
    extraction = AnnualReportExtraction(
        page_count=len(pages), text_page_count=len(text_pages), document_type=_detect_document_type(pages),
    )
    if extraction.looks_scanned:
        extraction.warnings.append(
            "Dokumentet verkar till stor del bestå av inskannade bilder. Text kan inte läsas utan OCR, "
            "som ännu inte stöds. Ange viktiga uppgifter manuellt."
        )

    extraction.organisation_number = _find_organisation_number(full_text)
    extraction.cooperative_name = _find_cooperative_name(pages)
    extraction.fiscal_period_start, extraction.fiscal_period_end = _find_fiscal_period(full_text)

    if extraction.document_type == DocumentType.ANNUAL_REPORT:
        extraction.figures = _extract_figures(pages, extraction.warnings)
        extraction.fiscal_year = _determine_fiscal_year(extraction)
        if extraction.fiscal_year:
            # Areas are described as of the report, so they belong to the report's fiscal year.
            extraction.figures += [replace(area, fiscal_year=extraction.fiscal_year) for area in _extract_areas(pages)]
        _check_period_length(extraction)

    extraction.land_tenure, extraction.land_tenure_evidence = _find_land_tenure(pages)
    extraction.findings = _find_topic_passages(pages)
    return extraction


# --- Identification --------------------------------------------------------------------------


def _detect_document_type(pages: list[PageLayout]) -> DocumentType:
    opening = " ".join(p.text for p in pages[:3]).lower()
    if "årsredovisning" in opening:
        return DocumentType.ANNUAL_REPORT
    if "ekonomisk plan" in opening:
        return DocumentType.ECONOMIC_PLAN
    if "underhållsplan" in opening:
        return DocumentType.MAINTENANCE_PLAN
    return DocumentType.OTHER


_ORGANISATION_NUMBER = re.compile(r"(?<![\d-])(7\d{5})\s?[-–]?\s?(\d{4})(?![\d-])")


def _find_organisation_number(text: str) -> str | None:
    """The most frequent cooperative-style org number (associations start with 7)."""
    candidates = Counter(f"{a}-{b}" for a, b in _ORGANISATION_NUMBER.findall(text))
    if not candidates:
        return None
    return candidates.most_common(1)[0][0]


# "Brf Byamännen 2", "HSB Bostadsrättsförening Segelflygaren i Stockholm". The name stays on
# one line; following words must be capitalised, "i <Place>", or a short number.
_NAME_WORD = r"[A-ZÅÄÖ][\wåäöÅÄÖé\-]*"
_COOPERATIVE_NAME = re.compile(
    rf"((?:HSB[ \t]+|Riksbyggens[ \t]+)?(?:Brf|BRF|Bostadsrätts?förening(?:en)?)[ \t]+"
    rf"{_NAME_WORD}(?:[ \t]+(?:i[ \t]+{_NAME_WORD}|{_NAME_WORD}|\d{{1,3}}(?![\d-]))){{0,3}})"
)


def _find_cooperative_name(pages: list[PageLayout]) -> str | None:
    names = Counter()
    for page in pages:
        for match in _COOPERATIVE_NAME.finditer(page.text.replace("ﬂ", "fl")):
            name = re.sub(r"\s+", " ", match.group(1)).strip()
            name = re.sub(r"\s+(Org|Årsredovisning|ÅRSREDOVISNING)\b.*$", "", name)
            names[name] += 1
    if not names:
        return None
    return names.most_common(1)[0][0]


_FISCAL_PERIOD = re.compile(r"(\d{4}-\d{2}-\d{2})\s*[-–]\s*(\d{4}-\d{2}-\d{2})")


def _find_fiscal_period(text: str) -> tuple[date | None, date | None]:
    match = re.search(r"räkenskapsåret\s+" + _FISCAL_PERIOD.pattern, text, re.IGNORECASE)
    if not match:
        return None, None
    return date.fromisoformat(match.group(1)), date.fromisoformat(match.group(2))


def _determine_fiscal_year(extraction: AnnualReportExtraction) -> int | None:
    if extraction.fiscal_period_end:
        return extraction.fiscal_period_end.year
    statement_years = [f.fiscal_year for f in extraction.figures if f.method == ExtractionMethod.PDF_FINANCIAL_STATEMENT]
    return max(statement_years) if statement_years else None


def _check_period_length(extraction: AnnualReportExtraction) -> None:
    start, end = extraction.fiscal_period_start, extraction.fiscal_period_end
    if not start or not end:
        return
    months = (end.year - start.year) * 12 + end.month - start.month + 1
    if months != 12:
        extraction.warnings.append(
            f"Räkenskapsåret omfattar {months} månader ({start} – {end}). Belopp för året är därför inte "
            f"direkt jämförbara med andra år."
        )


# --- Figures ----------------------------------------------------------------------------------


class _PageKind(StrEnum):
    INCOME_STATEMENT = "income_statement"
    BALANCE_SHEET = "balance_sheet"
    CASH_FLOW = "cash_flow"


def _classify_pages(rows: list[PeriodTableRow | TextRow]) -> dict[int, set[_PageKind]]:
    """Identify statement pages by their content, since not every report prints headings."""
    kinds: dict[int, set[_PageKind]] = {}
    for row in rows:
        if not isinstance(row, PeriodTableRow):
            continue
        label = row.label.lower()
        page_kinds = kinds.setdefault(row.page_number, set())
        if _CASH_FLOW_SIGNATURE.search(label):
            page_kinds.add(_PageKind.CASH_FLOW)
        elif _INCOME_STATEMENT_SIGNATURE.match(label):
            page_kinds.add(_PageKind.INCOME_STATEMENT)
        elif _BALANCE_SHEET_SIGNATURE.match(label):
            page_kinds.add(_PageKind.BALANCE_SHEET)
    # A cash flow analysis repeats "Rörelseresultat", so it is never also an income statement.
    for page_kinds in kinds.values():
        if _PageKind.CASH_FLOW in page_kinds:
            page_kinds.discard(_PageKind.INCOME_STATEMENT)
            page_kinds.discard(_PageKind.BALANCE_SHEET)
    return kinds


def _extract_figures(pages: list[PageLayout], warnings: list[str]) -> list[ExtractedFigure]:
    rows = read_document_rows(pages)
    page_kinds = _classify_pages(rows)
    statement_pages = sorted(p for p, k in page_kinds.items() if k & {_PageKind.INCOME_STATEMENT, _PageKind.BALANCE_SHEET})
    cash_flow_pages = sorted(p for p, k in page_kinds.items() if _PageKind.CASH_FLOW in k)
    first_statement_page = statement_pages[0] if statement_pages else len(pages) + 1
    # Notes come after the cash flow analysis and repeat many labels; ignore everything after it.
    last_statement_page = cash_flow_pages[0] if cash_flow_pages else len(pages) + 1
    if not statement_pages:
        warnings.append("Kunde inte hitta resultat- eller balansräkningen i dokumentet.")

    figures: list[ExtractedFigure] = []
    seen_statement_metrics: set[tuple[str, int]] = set()
    seen_key_figures: set[tuple[str, int]] = set()
    debt_rows: list[tuple[PeriodTableRow, bool]] = []  # (row, is_short_term)
    in_short_term_liabilities = False
    cash_rows: list[PeriodTableRow] = []
    pending_label = ""  # A label-only row that may continue on the next row.

    for row in rows:
        if isinstance(row, TextRow):
            lowered = row.text.lower()
            if "kortfristiga skulder" in lowered:
                in_short_term_liabilities = True
            elif "långfristiga skulder" in lowered:
                in_short_term_liabilities = False
            pending_label = row.text
            continue

        kinds = page_kinds.get(row.page_number, set())
        if row.page_number < first_statement_page:
            _, metric_key = _match_with_continuation(row, pending_label, _KEY_FIGURE_PATTERNS)
            if metric_key:
                figures += _key_figure_values(metric_key, row, seen_key_figures, warnings)
        elif row.page_number < last_statement_page:
            label = row.label.lower()
            if _PageKind.INCOME_STATEMENT in kinds:
                _, metric_key = _match_with_continuation(row, pending_label, _INCOME_STATEMENT_PATTERNS)
                if metric_key:
                    figures += _statement_values(metric_key, row, seen_statement_metrics)
            if _PageKind.BALANCE_SHEET in kinds:
                metric_key = _match(label, _BALANCE_SHEET_PATTERNS)
                if metric_key:
                    figures += _statement_values(metric_key, row, seen_statement_metrics)
                elif _CASH_ROW.match(label):
                    cash_rows.append(row)
                elif _CREDIT_INSTITUTION_DEBT_ROW.match(label):
                    is_short_term = in_short_term_liabilities or "kortfristig" in label
                    debt_rows.append((row, is_short_term))
        pending_label = ""

    if not any(f.metric_key == "cash" for f in figures) and cash_rows:
        figures += _statement_values("cash", cash_rows[0], seen_statement_metrics)
    figures += _sum_debt_rows(debt_rows)
    return figures


def _match_with_continuation(row: PeriodTableRow, pending_label: str,
                             patterns: list[tuple[str, re.Pattern]]) -> tuple[str, str | None]:
    """Match a row label, also trying it joined with the label-only line just above it.

    Long labels wrap: "Av- och nedskrivningar av materiella och" / "immateriella ... 1 291 480".
    When the combined label matches, it is stored on the row as the printed label.
    """
    label = row.label.lower()
    metric_key = _match(label, patterns) if label else None
    if metric_key is None and pending_label:
        combined = clean_label(f"{pending_label} {row.label}")
        metric_key = _match(combined.lower(), patterns)
        if metric_key:
            row.label = combined
    return row.label, metric_key


def _match(label: str, patterns: list[tuple[str, re.Pattern]]) -> str | None:
    for metric_key, pattern in patterns:
        if pattern.search(label):
            return metric_key
    return None


def _key_figure_values(metric_key: str, row: PeriodTableRow, seen: set[tuple[str, int]],
                       warnings: list[str]) -> list[ExtractedFigure]:
    scale, scale_note = _amount_scale(metric_key, row)
    if re.search(r"\bboyta\b", row.label.lower()) and METRICS[metric_key].area_basis == AreaBasis.TENANT_OWNED_AREA:
        scale_note = _BOYTA_NOTE
    figures = []
    for year, raw_value in row.values.items():
        if (metric_key, year) in seen:
            continue
        if raw_value == 0 and metric_key in _ZERO_MEANS_NOT_REPORTED:
            warnings.append(
                f"{METRICS[metric_key].label} för {year} anges som 0 på sidan {row.page_number}. "
                f"Tolkat som att nyckeltalet inte redovisades det året."
            )
            continue
        seen.add((metric_key, year))
        value = raw_value * scale
        note = scale_note
        if not METRICS[metric_key].is_plausible(value):
            note = " ".join(filter(None, [note, "Ovanligt värde. Kontrollera mot dokumentet; det kan vara ett tryckfel."]))
            warnings.append(f"{METRICS[metric_key].label} för {year} anges som {raw_value:g} på sidan "
                            f"{row.page_number}, vilket är ovanligt. Kontrollera värdet.")
        figures.append(ExtractedFigure(
            metric_key, year, value, row.page_number, row.label,
            ExtractionMethod.PDF_KEY_FIGURES_TABLE, ValueOrigin.REPORTED, note,
        ))
    return figures


def _amount_scale(metric_key: str, row: PeriodTableRow) -> tuple[float, str | None]:
    """Monetary amounts in key-figure tables are often in thousands (tkr)."""
    if METRICS[metric_key].unit != Unit.SEK:
        return 1.0, None
    label = row.label.lower()
    if re.search(r"\btkr\b", label) or (re.search(r"\btkr\b", row.header_text.lower()) and "kr" not in label):
        return 1000.0, "Angivet i tkr i dokumentet, omräknat till kronor."
    if re.search(r"\bmkr\b|\bmsek\b", label):
        return 1_000_000.0, "Angivet i mkr i dokumentet, omräknat till kronor."
    return 1.0, None


def _statement_values(metric_key: str, row: PeriodTableRow, seen: set[tuple[str, int]]) -> list[ExtractedFigure]:
    figures = []
    for year, value in row.values.items():
        if (metric_key, year) in seen:
            continue
        seen.add((metric_key, year))
        if metric_key in _STORED_AS_POSITIVE:
            value = abs(value)
        figures.append(ExtractedFigure(
            metric_key, year, value, row.page_number, row.label,
            ExtractionMethod.PDF_FINANCIAL_STATEMENT, ValueOrigin.REPORTED,
        ))
    return figures


def _sum_debt_rows(debt_rows: list[tuple[PeriodTableRow, bool]]) -> list[ExtractedFigure]:
    """Interest-bearing debt is the sum of all 'skulder till kreditinstitut' rows in the balance sheet."""
    if not debt_rows:
        return []
    years = sorted({year for row, _ in debt_rows for year in row.values})
    figures = []
    for year in years:
        total = sum(row.values.get(year, 0.0) for row, _ in debt_rows)
        short_term = sum(row.values.get(year, 0.0) for row, is_short in debt_rows if is_short)
        labels = "; ".join(f"{row.label} (s. {row.page_number})" for row, _ in debt_rows)
        page = debt_rows[0][0].page_number
        figures.append(ExtractedFigure(
            "interest_bearing_debt", year, total, page, labels, ExtractionMethod.PDF_FINANCIAL_STATEMENT,
            ValueOrigin.REPORTED, "Summa av raderna för skulder till kreditinstitut i balansräkningen.",
        ))
        figures.append(ExtractedFigure(
            "short_term_interest_bearing_debt", year, short_term, page, labels,
            ExtractionMethod.PDF_FINANCIAL_STATEMENT, ValueOrigin.REPORTED,
            "Summa av kortfristiga skulder till kreditinstitut i balansräkningen.",
        ))
    return figures


# --- Areas ------------------------------------------------------------------------------------

_AREA_UNIT = r"(?:kvm|k?vm|m2|m²)"
_AREA_NUMBER = r"(\d{1,3}(?:[  ]\d{3})+|\d+)"
_AREA_TEXT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("residential_area", re.compile(rf"(?:total\s+)?bostads(?:area|yta)n?\s*\(?\s*{_AREA_NUMBER}\s*{_AREA_UNIT}",
                                    re.IGNORECASE)),
    ("commercial_area", re.compile(rf"(?:total\s+)?lokal(?:area|yta)n?\s*\(?\s*{_AREA_NUMBER}\s*{_AREA_UNIT}",
                                   re.IGNORECASE)),
    # Standard abbreviations: BOA (bostadsarea) and LOA (lokalarea).
    ("residential_area", re.compile(rf"\bBOA\s*\(?\s*{_AREA_NUMBER}\s*{_AREA_UNIT}")),
    ("commercial_area", re.compile(rf"\bLOA\s*\(?\s*{_AREA_NUMBER}\s*{_AREA_UNIT}")),
    ("tenant_owned_area", re.compile(
        rf"lägenheter\s*\(upplåtna med bostadsrätt\)\s*{_AREA_NUMBER}(?!\s*\d)", re.IGNORECASE)),
]
# The management report rarely runs past page 12; later pages are statements and notes.
_AREA_PAGES = 12
_AREA_HEADER_WORDS = {
    "bostadsyta": "residential_area", "boyta": "residential_area", "lokalyta": "commercial_area",
    "totalyta": "total_area", "total yta": "total_area",
}


def _extract_areas(pages: list[PageLayout]) -> list[ExtractedFigure]:
    """Areas, taken from the management report, where the property and key figures are described.

    Every distinct value is kept. Reports sometimes give different areas in different
    places (for example from a ground lease contract and from the key figure notes),
    and the user should see that instead of us picking one.
    """
    found: dict[tuple[str, float], ExtractedFigure] = {}
    for page in pages[:_AREA_PAGES]:
        text = re.sub(r"[ \t]*\n[ \t]*", " ", page.text)
        for metric_key, pattern in _AREA_TEXT_PATTERNS:
            for match in pattern.finditer(text):
                value = parse_swedish_number(match.group(1))
                if value and value > 10:
                    found.setdefault((metric_key, value), ExtractedFigure(
                        metric_key, 0, value, page.page_number, match.group(0).strip(),
                        ExtractionMethod.PDF_TEXT_PATTERN, ValueOrigin.REPORTED,
                    ))
        for figure in _areas_from_header_table(page).values():
            found.setdefault((figure.metric_key, figure.value), figure)
    return list(found.values())


def _areas_from_header_table(page: PageLayout) -> dict[str, ExtractedFigure]:
    """Tables like 'Bostadsyta  Lokalyta  Totalyta' followed by a row of numbers."""
    for index, row in enumerate(page.rows[:-1]):
        headers = [(cell, _AREA_HEADER_WORDS[cell.text.lower()]) for cell in row.cells
                   if cell.text.lower() in _AREA_HEADER_WORDS]
        if len(headers) < 2:
            continue
        for value_row in page.rows[index + 1:index + 4]:
            numbers = [cell for cell in value_row.cells if cell.is_numeric]
            if len(numbers) < len(headers):
                continue
            result = {}
            for header, metric_key in headers:
                nearest = min(numbers, key=lambda cell: abs(cell.center - header.center))
                result[metric_key] = ExtractedFigure(
                    metric_key, 0, nearest.number, page.page_number, header.text,
                    ExtractionMethod.PDF_TEXT_PATTERN, ValueOrigin.REPORTED,
                )
            return result
    return {}


# --- Running text -----------------------------------------------------------------------------


def _find_land_tenure(pages: list[PageLayout]) -> tuple[LandTenure | None, TextFinding | None]:
    for page in pages[:10]:
        for line in page.text.splitlines():
            lowered = line.lower()
            if "tomträtt" in lowered:
                return LandTenure.LEASEHOLD, TextFinding("Mark", page.page_number, line.strip())
    for page in pages[:10]:
        for line in page.text.splitlines():
            if re.search(r"friköpt|äger marken|med äganderätt", line, re.IGNORECASE):
                return LandTenure.OWNED, TextFinding("Mark", page.page_number, line.strip())
    return None, None


def _find_topic_passages(pages: list[PageLayout]) -> list[TextFinding]:
    findings: list[TextFinding] = []
    counts: Counter = Counter()
    for page in pages:
        lines = [line.strip() for line in page.text.splitlines()]
        for index, line in enumerate(lines):
            if not line or re.search(r"\.\s?\.\s?\.", line):  # Skip table-of-contents lines.
                continue
            for topic, pattern in _TOPICS:
                if counts[topic] >= _MAX_FINDINGS_PER_TOPIC or not pattern.search(line):
                    continue
                excerpt = line
                # Planned-maintenance tables put the year on the line before the measure.
                if index > 0 and re.fullmatch(r"(19|20)\d{2}(\s*[-–]\s*(19|20)\d{2})?", lines[index - 1]):
                    excerpt = f"{lines[index - 1]}: {line}"
                findings.append(TextFinding(topic, page.page_number, excerpt[:400]))
                counts[topic] += 1
    return findings
