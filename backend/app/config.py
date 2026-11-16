"""Application settings.

The app runs in the visitor's browser (see app/browser.py), so there is no server
to hold secrets: settings are plain values, not read from the environment.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

BACKEND_DIRECTORY = Path(__file__).parents[1]


class Settings(BaseModel):
    data_directory: Path = BACKEND_DIRECTORY / "data"
    risk_rules_path: Path = BACKEND_DIRECTORY / "config" / "risk_rules.toml"
    max_document_bytes: int = 60 * 1024 * 1024
    # An imported backup may hold many PDFs; this caps its unpacked size.
    max_backup_bytes: int = 2 * 1024 * 1024 * 1024

    @property
    def database_path(self) -> Path:
        return self.data_directory / "boster.db"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"

    @property
    def document_directory(self) -> Path:
        return self.data_directory / "documents"


@lru_cache
def get_settings() -> Settings:
    return Settings()
