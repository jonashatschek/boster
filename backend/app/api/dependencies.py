"""Shared FastAPI dependencies. The app stores its settings, database and rules on app.state."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.risk import RiskRules


def get_session(request: Request) -> Iterator[Session]:
    yield from request.app.state.database.session()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_risk_rules(request: Request) -> RiskRules:
    return request.app.state.risk_rules
