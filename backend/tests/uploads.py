"""Upload a PDF the way the browser does: the file plus the text of each page.

The browser reads page text with pdf.js; tests use PyMuPDF to produce the same shape.
"""

import json

from app.documents.pymupdf_text import read_pages


def page_text_json(content: bytes) -> str:
    try:
        pages = read_pages(content)
    except Exception:  # Not a PDF: the browser would send no pages either.
        return "[]"
    return json.dumps([{"text": page.text, "words": [list(word) for word in page.words]} for page in pages])


def upload_pdf(client, content: bytes, filename: str = "arsredovisning.pdf", pages: str | None = None):
    return client.post("/api/documents/upload", files={"file": (filename, content, "application/pdf")},
                       data={"pages": page_text_json(content) if pages is None else pages})
