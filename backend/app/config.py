"""Application settings, read from environment variables or backend/.env."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIRECTORY = Path(__file__).parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIRECTORY / ".env", extra="ignore")

    data_directory: Path = BACKEND_DIRECTORY / "data"
    risk_rules_path: Path = BACKEND_DIRECTORY / "config" / "risk_rules.toml"
    max_document_bytes: int = 60 * 1024 * 1024
    document_download_timeout_seconds: float = 30.0
    # Origins allowed to call the API from a browser (the Vite dev server).
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # SecretStr keeps keys out of logs and error messages.
    trafiklab_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_directory / 'boster.db'}"

    @property
    def document_directory(self) -> Path:
        return self.data_directory / "documents"


@lru_cache
def get_settings() -> Settings:
    return Settings()
