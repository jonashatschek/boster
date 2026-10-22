"""Reading tables whose columns are fiscal years.

Both the multi-year overview (flerårsöversikt) and the financial statements are
laid out as a label column followed by one column per fiscal year. A row of period
labels ("2025", "2024/2025", "2025-08-31", ...) starts a table. Every following row
on the same page is read by assigning each number to the nearest year column.
"""

import re
from dataclasses import dataclass

from app.documents.number_parsing import parse_fiscal_year_label
from app.documents.pdf_layout import Cell, PageLayout, Row


@dataclass(frozen=True)
class PeriodColumn:
    fiscal_year: int
    label: str
    x0: float
    x1: float


@dataclass
class PeriodTableRow:
    page_number: int
    label: str
    values: dict[int, float]  # Fiscal year → value. Missing cells are simply absent.
    header_text: str  # Text of the header row, used to detect units like "tkr".
    unassigned_numbers: list[str]  # Numbers that could not be placed in a column.


@dataclass
class TextRow:
    """A row without a period table, kept so that section headings can be detected."""

    page_number: int
    text: str


def find_period_header(row: Row) -> list[PeriodColumn] | None:
    columns = []
    for cell in row.cells:
        year = parse_fiscal_year_label(cell.text)
        if year is not None:
            columns.append(PeriodColumn(year, cell.text, cell.x0, cell.x1))
    years = [column.fiscal_year for column in columns]
    if len(columns) >= 2 and len(set(years)) == len(years):
        return columns
    return None


def read_document_rows(pages: list[PageLayout]) -> list[PeriodTableRow | TextRow]:
    """All rows of the document in reading order, table rows annotated with their year values."""
    result: list[PeriodTableRow | TextRow] = []
    for page in pages:
        columns: list[PeriodColumn] | None = None
        header_text = ""
        for row in page.rows:
            header = find_period_header(row)
            if header:
                columns, header_text = header, row.text
                result.append(TextRow(page.page_number, row.text))
                continue
            if columns is None or not any(cell.is_numeric for cell in row.cells):
                result.append(TextRow(page.page_number, row.text))
                continue
            result.append(_read_table_row(row, columns, header_text))
    return result


def _read_table_row(row: Row, columns: list[PeriodColumn], header_text: str) -> PeriodTableRow:
    first_column_start = min(column.x0 for column in columns)
    pitch = _column_pitch(columns)
    label_parts: list[str] = []
    values: dict[int, float] = {}
    unassigned: list[str] = []

    for cell in row.cells:
        number = cell.number
        if number is None:
            if cell.x1 < first_column_start and not cell.is_empty_marker:
                label_parts.append(cell.text)
            continue
        column = _nearest_column(cell, columns, pitch)
        if column is None or column.fiscal_year in values:
            # Note references ("Not 14", "11") end up here, as do stray numbers.
            unassigned.append(cell.text)
        else:
            values[column.fiscal_year] = number

    return PeriodTableRow(row.page_number, clean_label(" ".join(label_parts)), values, header_text, unassigned)


def _column_pitch(columns: list[PeriodColumn]) -> float:
    centers = sorted((c.x0 + c.x1) / 2 for c in columns)
    gaps = [b - a for a, b in zip(centers, centers[1:])]
    return min(gaps) if gaps else 100.0


def _nearest_column(cell: Cell, columns: list[PeriodColumn], pitch: float) -> PeriodColumn | None:
    """Match by right edge, centre or left edge, whichever aligns best (tables are usually right-aligned)."""

    def distance(column: PeriodColumn) -> float:
        return min(abs(cell.x1 - column.x1), abs(cell.center - (column.x0 + column.x1) / 2), abs(cell.x0 - column.x0))

    best = min(columns, key=distance)
    return best if distance(best) < pitch * 0.45 else None


def clean_label(text: str) -> str:
    """Normalise a row label: drop footnote stars and note references, collapse whitespace.

    Note references appear as "Not 14", a trailing "Not" whose number sits in its own
    column, or a trailing list such as "4, 5, 6, 7,".
    """
    text = text.replace("*", " ")
    text = re.sub(r"\bnot\s*\d+\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"(\s+\d{1,2},?)+\s*$", "", text)
    text = re.sub(r"\s+not\s*$", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()
