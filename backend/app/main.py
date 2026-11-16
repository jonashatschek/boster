"""FastAPI application.

In production it runs inside the visitor's browser with Pyodide (see app/browser.py).
Tests call it with FastAPI's TestClient.
"""

from fastapi import FastAPI

from app.api import backup, comparisons, cooperatives, documents, properties
from app.config import Settings, get_settings
from app.db import Database
from app.domain.risk import load_risk_rules


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.data_directory.mkdir(parents=True, exist_ok=True)

    database = Database(settings.database_url)
    database.create_tables()

    app = FastAPI(title="Boster", description="Analys av bostadsrätter och bostadsrättsföreningar")
    app.state.settings = settings
    app.state.database = database
    app.state.risk_rules = load_risk_rules(settings.risk_rules_path)

    app.include_router(documents.router)
    app.include_router(cooperatives.router)
    app.include_router(comparisons.router)
    app.include_router(properties.router)
    app.include_router(backup.router)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app
