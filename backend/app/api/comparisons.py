from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_risk_rules, get_session
from app.domain.risk import RiskRules
from app.schemas import CooperativeComparison
from app.services import comparison as comparison_service
from app.services import cooperatives as cooperative_service

router = APIRouter(prefix="/api/comparisons", tags=["comparisons"])


@router.get("/cooperatives", response_model=CooperativeComparison)
def compare_cooperatives(
    session: Annotated[Session, Depends(get_session)],
    rules: Annotated[RiskRules, Depends(get_risk_rules)],
    ids: Annotated[str, Query(description="Comma-separated cooperative ids, e.g. 1,3,5")],
):
    try:
        cooperative_ids = list(dict.fromkeys(int(part) for part in ids.split(",") if part.strip()))
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Ogiltiga förenings-id.") from error
    minimum, maximum = comparison_service.MIN_COOPERATIVES, comparison_service.MAX_COOPERATIVES
    if not minimum <= len(cooperative_ids) <= maximum:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Välj mellan {minimum} och {maximum} föreningar att jämföra.")

    cooperatives = []
    for cooperative_id in cooperative_ids:
        cooperative = cooperative_service.load_cooperative(session, cooperative_id)
        if cooperative is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Föreningen {cooperative_id} finns inte.")
        cooperatives.append(cooperative)
    return comparison_service.compare_cooperatives(cooperatives, rules)
