"""Print the positioned rows of selected PDF pages, for debugging table extraction.

Usage: python -m scripts.dump_rows path/to/report.pdf 9 10 11
"""

import sys
from pathlib import Path

import pymupdf

from app.documents.pdf_layout import read_layout
from app.documents.period_tables import PeriodTableRow, read_document_rows


def main(path: str, page_numbers: list[int]) -> None:
    with pymupdf.open(stream=Path(path).read_bytes(), filetype="pdf") as document:
        pages = read_layout(document)
    for row in read_document_rows([pages[n - 1] for n in page_numbers]):
        if isinstance(row, PeriodTableRow):
            print(f"p{row.page_number} TABLE {row.label!r} {row.values} unassigned={row.unassigned_numbers}")
        else:
            print(f"p{row.page_number} TEXT  {row.text[:110]!r}")


if __name__ == "__main__":
    main(sys.argv[1], [int(n) for n in sys.argv[2:]])
