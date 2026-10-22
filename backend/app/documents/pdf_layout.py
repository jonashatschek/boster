"""Turn PDF pages into rows of positioned cells.

Plain text extraction loses the table structure of annual reports: thousands
separators split numbers into several words, and reading order sometimes mixes
note references with amounts. Here we keep word coordinates, group words on the
same baseline into rows, and merge words that sit close together into cells.
Tables can then be read by matching cells to column headers by position.
"""

from dataclasses import dataclass, field

import pymupdf

from app.documents.number_parsing import is_empty_cell, is_thousands_group, parse_swedish_number

# Words whose vertical centres differ by less than this many points share a row.
_ROW_TOLERANCE = 2.5
# Words separated by less than this fraction of the line height belong to one cell.
_CELL_GAP_FACTOR = 0.55


@dataclass
class Cell:
    text: str
    x0: float
    x1: float
    y0: float
    y1: float

    @property
    def center(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def number(self) -> float | None:
        return parse_swedish_number(self.text)

    @property
    def is_numeric(self) -> bool:
        return self.number is not None

    @property
    def is_empty_marker(self) -> bool:
        return is_empty_cell(self.text)


@dataclass
class Row:
    page_number: int  # 1-based, as shown in PDF viewers.
    y: float
    cells: list[Cell] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(cell.text for cell in self.cells)


@dataclass
class PageLayout:
    page_number: int
    rows: list[Row]
    text: str  # Plain text in PyMuPDF reading order, used for running-text patterns.


def read_layout(document: pymupdf.Document) -> list[PageLayout]:
    return [
        PageLayout(page_number=index + 1, rows=_rows_for_page(page, index + 1), text=page.get_text())
        for index, page in enumerate(document)
    ]


def _rows_for_page(page: pymupdf.Page, page_number: int) -> list[Row]:
    # Each word is (x0, y0, x1, y1, text, block, line, word_index).
    words = [w for w in page.get_text("words") if w[4].strip()]
    words.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))

    grouped: list[list[tuple]] = []
    for word in words:
        center = (word[1] + word[3]) / 2
        if grouped:
            previous = grouped[-1]
            previous_center = sum((w[1] + w[3]) / 2 for w in previous) / len(previous)
            if abs(center - previous_center) <= _ROW_TOLERANCE:
                previous.append(word)
                continue
        grouped.append([word])

    rows = []
    for row_words in grouped:
        row_words.sort(key=lambda w: w[0])
        rows.append(Row(page_number=page_number, y=min(w[1] for w in row_words), cells=_merge_into_cells(row_words)))
    return rows


def _merge_into_cells(row_words: list[tuple]) -> list[Cell]:
    cells: list[Cell] = []
    for x0, y0, x1, y1, text, *_ in row_words:
        if cells:
            last = cells[-1]
            gap = x0 - last.x1
            line_height = max(y1 - y0, last.y1 - last.y0)
            if gap <= line_height * _CELL_GAP_FACTOR and _may_join(last.text, text):
                last.text = f"{last.text} {text}"
                last.x1, last.y0, last.y1 = x1, min(last.y0, y0), max(last.y1, y1)
                continue
        cells.append(Cell(text=text, x0=x0, x1=x1, y0=y0, y1=y1))
    return cells


def _may_join(left: str, right: str) -> bool:
    """Decide whether two neighbouring words are parts of the same cell.

    Text joins text, and a number joins its own thousands groups. A number never
    joins a text label, which keeps note references and amounts apart.
    """
    left_is_number = parse_swedish_number(left) is not None or left.strip() in "-−–"
    right_is_number = parse_swedish_number(right) is not None
    if left_is_number and right_is_number:
        return is_thousands_group(right) and not left.rstrip().endswith("%")
    if left_is_number != right_is_number:
        # Allow ranges like "2024 - 2025" and dates split around a dash.
        return right.strip() in "-–" or left.strip().endswith(("-", "–"))
    return True
