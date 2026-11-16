from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.dependencies import get_settings
from app.config import Settings
from app.services import backup as backup_service
from app.services.backup import BackupError

router = APIRouter(prefix="/api/backup", tags=["backup"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("")
def export_data(settings: SettingsDep):
    """All data (database and documents) as a zip file."""
    return Response(backup_service.export_data(settings), media_type="application/zip")


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
async def import_data(request: Request, settings: SettingsDep):
    """Replace all data with an exported zip file, sent as the request body."""
    content = await request.body()
    try:
        backup_service.import_data(settings, request.app.state.database, content)
    except BackupError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
