"""Read page text with PyMuPDF, for tests and scripts run on a desktop Python.

The app itself runs in the browser and reads PDFs with pdf.js instead
(frontend/src/pdf/pageText.ts). This module is left out of the browser bundle.
PyMuPDF is a development dependency only.
"""

import pymupdf

from app.documents.pdf_layout import PageText


def read_pages(pdf_bytes: bytes) -> list[PageText]:
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
        return [
            PageText(text=page.get_text(), words=[tuple(word[:5]) for word in page.get_text("words")])
            for page in document
        ]
