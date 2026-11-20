from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_risk_rules, get_session
from app.domain.risk import RiskRules
from app.schemas import CooperativeComparison, PropertyComparison
from app.services import comparison as comparison_service
from app.services import cooperatives as cooperative_service
from app.services import properties as property_service
from app.services import property_comparison as property_comparison_service

router = APIRouter(prefix="/api/comparisons", tags=["comparisons"])

SessionDep = Annotated[Session, Depends(get_session)]
RulesDep = Annotated[RiskRules, Depends(get_risk_rules)]


def _parse_ids(ids: str, minimum: int, maximum: int, invalid: str, plural: str) -> list[int]:
    """Comma-separated positive ids, duplicates removed, between `minimum` and `maximum` of them."""
    try:
        parsed = list(dict.fromkeys(int(part) for part in ids.split(",") if part.strip()))
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, invalid) from error
    if any(parsed_id <= 0 for parsed_id in parsed):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, invalid)
    if not minimum <= len(parsed) <= maximum:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Välj mellan {minimum} och {maximum} {plural} att jämföra.")
    return parsed


@router.get("/cooperatives", response_model=CooperativeComparison)
def compare_cooperatives(
    session: SessionDep,
    rules: RulesDep,
    ids: Annotated[str, Query(description="Comma-separated cooperative ids, e.g. 1,3,5")],
):
    cooperative_ids = _parse_ids(ids, comparison_service.MIN_COOPERATIVES, comparison_service.MAX_COOPERATIVES,
                                 "Ogiltiga förenings-id.", "föreningar")
    cooperatives = []
    for cooperative_id in cooperative_ids:
        cooperative = cooperative_service.load_cooperative(session, cooperative_id)
        if cooperative is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Föreningen {cooperative_id} finns inte.")
        cooperatives.append(cooperative)
    return comparison_service.compare_cooperatives(cooperatives, rules)


@router.get("/properties", response_model=PropertyComparison)
def compare_properties(
    session: SessionDep,
    rules: RulesDep,
    ids: Annotated[str, Query(description="Comma-separated property ids, e.g. 1,3")],
):
    property_ids = _parse_ids(ids, property_comparison_service.MIN_PROPERTIES,
                              property_comparison_service.MAX_PROPERTIES, "Ogiltiga bostads-id.", "bostäder")
    listings = []
    for property_id in property_ids:
        listing = property_service.load_property(session, property_id)
        if listing is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Bostaden {property_id} finns inte.")
        listings.append(listing)
    return property_comparison_service.compare_properties(session, listings, rules)
