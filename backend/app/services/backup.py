"""Export all data to a zip file, and replace all data with an exported file.

The data lives only in the visitor's browser, so an export is the way to keep a copy,
move to another device, or share with someone else. An import is untrusted input:
we only accept the exact files an export writes, check the database before using it,
and limit the unpacked size.
"""

import io
import json
import re
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.db import Database

FORMAT_VERSION = 1
_MANIFEST = "manifest.json"
_DATABASE = "boster.db"
_DOCUMENT = re.compile(r"^documents/[0-9a-f]{64}\.pdf$")
_REQUIRED_TABLES = {"housing_cooperatives", "source_documents", "financial_observations", "properties"}


class BackupError(Exception):
    """The message is shown to the user, in Swedish."""


def export_data(settings: Settings) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        manifest = {"app": "boster", "format": FORMAT_VERSION, "exported_at": datetime.now(timezone.utc).isoformat()}
        archive.writestr(_MANIFEST, json.dumps(manifest, indent=2))
        archive.writestr(_DATABASE, _database_snapshot(settings.database_path), compress_type=zipfile.ZIP_DEFLATED)
        if settings.document_directory.exists():
            for path in sorted(settings.document_directory.glob("*.pdf")):
                if _DOCUMENT.match(f"documents/{path.name}"):
                    archive.write(path, f"documents/{path.name}")  # PDFs are already compressed.
    return buffer.getvalue()


def import_data(settings: Settings, database: Database, content: bytes) -> None:
    """Replace all data with the contents of an export. Nothing changes unless the file is valid."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as error:
        raise BackupError("Filen är inte en export från Boster.") from error

    with archive, tempfile.TemporaryDirectory() as staging_name:
        staging = Path(staging_name)
        _check_members(settings, archive)
        (staging / _DATABASE).write_bytes(archive.read(_DATABASE))
        _check_database(staging / _DATABASE)
        documents = staging / "documents"
        documents.mkdir()
        for name in archive.namelist():
            if _DOCUMENT.match(name):
                (documents / Path(name).name).write_bytes(archive.read(name))
        _replace_data(settings, database, staging)


def _database_snapshot(database_path: Path) -> bytes:
    """A consistent copy of the database, made with SQLite's backup API."""
    with tempfile.TemporaryDirectory() as directory:
        copy_path = Path(directory) / _DATABASE
        source = sqlite3.connect(database_path)
        target = sqlite3.connect(copy_path)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        return copy_path.read_bytes()


def _check_members(settings: Settings, archive: zipfile.ZipFile) -> None:
    names = archive.namelist()
    if _MANIFEST not in names or _DATABASE not in names:
        raise BackupError("Filen är inte en export från Boster.")
    unexpected = [name for name in names if name not in (_MANIFEST, _DATABASE) and not _DOCUMENT.match(name)]
    if unexpected:
        raise BackupError("Filen innehåller okända filer och kan inte importeras.")
    if sum(info.file_size for info in archive.infolist()) > settings.max_backup_bytes:
        raise BackupError("Filen är för stor för att importeras.")
    try:
        manifest = json.loads(archive.read(_MANIFEST))
    except ValueError as error:
        raise BackupError("Filen är inte en export från Boster.") from error
    if not isinstance(manifest, dict) or manifest.get("app") != "boster":
        raise BackupError("Filen är inte en export från Boster.")
    if not isinstance(manifest.get("format"), int) or manifest["format"] > FORMAT_VERSION:
        raise BackupError("Filen kommer från en nyare version av Boster. Ladda om sidan och försök igen.")


def _check_database(path: Path) -> None:
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise BackupError("Databasen i filen är skadad.")
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            connection.close()
    except sqlite3.DatabaseError as error:
        raise BackupError("Databasen i filen kan inte läsas.") from error
    if not _REQUIRED_TABLES <= tables:
        raise BackupError("Filen är inte en export från Boster.")


def _replace_data(settings: Settings, database: Database, staging: Path) -> None:
    database.engine.dispose()  # Close every connection to the old database file.
    database_path = settings.database_path
    for suffix in ("", "-journal", "-wal", "-shm"):
        Path(f"{database_path}{suffix}").unlink(missing_ok=True)
    shutil.rmtree(settings.document_directory, ignore_errors=True)

    settings.data_directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(staging / _DATABASE, database_path)
    shutil.copytree(staging / "documents", settings.document_directory)
    database.create_tables()  # An export from an older version may lack newer columns.
