import json
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, get_settings
from app.config import Settings
from app.documents.pdf_layout import pages_from_json
from app.models import HousingCooperative, SourceDocument
from app.schemas import DocumentReassign, DocumentSummary
from app.services import documents as document_service
from app.services.documents import DocumentError

router = APIRouter(prefix="/api/documents", tags=["documents"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.post("/upload", response_model=DocumentSummary, status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile, pages: Annotated[str, Form()], session: SessionDep,
                          settings: SettingsDep):
    """Store a PDF. `pages` is the text of each page as read by pdf.js in the browser (see pdf_layout.PageText)."""
    content = await file.read(settings.max_document_bytes + 1)
    try:
        page_text = pages_from_json(json.loads(pages))
    except ValueError:  # Includes json.JSONDecodeError.
        page_text = None  # Stored, but reported as unreadable.
    try:
        return document_service.ingest_pdf(session, settings, content, file.filename or "dokument.pdf", page_text)
    except DocumentError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.get("/{document_id}", response_model=DocumentSummary)
def get_document(document_id: int, session: SessionDep):
    return _get_document(session, document_id)


@router.get("/{document_id}/file")
def get_document_file(document_id: int, session: SessionDep, settings: SettingsDep):
    document = _get_document(session, document_id)
    path = document_service.document_path(settings, document)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filen saknas.")
    return Response(path.read_bytes(), media_type="application/pdf")


@router.patch("/{document_id}", response_model=DocumentSummary)
def reassign_document(document_id: int, request: DocumentReassign, session: SessionDep):
    document = _get_document(session, document_id)
    cooperative = session.get(HousingCooperative, request.cooperative_id)
    if cooperative is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Föreningen finns inte.")
    document_service.reassign_document(session, document, cooperative)
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, session: SessionDep, settings: SettingsDep):
    document_service.delete_document(session, settings, _get_document(session, document_id))


def _get_document(session: Session, document_id: int) -> SourceDocument:
    document = session.get(SourceDocument, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dokumentet finns inte.")
    return document
