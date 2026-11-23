from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_risk_rules, get_session, get_settings
from app.config import Settings
from app.domain.metrics import METRICS
from app.domain.provenance import ExtractionMethod, VerificationStatus
from app.domain.risk import RiskRules
from app.models import FinancialObservation, HousingCooperative
from app.schemas import (
    CooperativeListItem, CooperativeOverview, CooperativeUpdate, MaintenanceAnswerIn, ManualObservationCreate,
    MetricDefinitionOut,
)
from app.services import cooperatives as cooperative_service
from app.services import documents as document_service

router = APIRouter(prefix="/api", tags=["cooperatives"])

SessionDep = Annotated[Session, Depends(get_session)]
RulesDep = Annotated[RiskRules, Depends(get_risk_rules)]


@router.get("/metrics", response_model=list[MetricDefinitionOut])
def list_metrics():
    return [
        MetricDefinitionOut(key=d.key, label=d.label, unit=d.unit.value, category=d.category.value,
                            description=d.description, area_basis=d.area_basis.value if d.area_basis else None)
        for d in METRICS.values()
    ]


@router.get("/cooperatives", response_model=list[CooperativeListItem])
def list_cooperatives(session: SessionDep, rules: RulesDep):
    return cooperative_service.list_cooperatives(session, rules)


@router.delete("/cooperatives", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_cooperatives(session: SessionDep, settings: Annotated[Settings, Depends(get_settings)]):
    """Deletes every cooperative with its documents and figures in one transaction. Apartments are kept, unlinked.

    The PDF files are removed only after the commit, so a failure never leaves documents without their file.
    """
    cooperatives = session.scalars(select(HousingCooperative)).all()
    files = [document_service.document_path(settings, d) for c in cooperatives for d in c.documents]
    for cooperative in cooperatives:
        for document in list(cooperative.documents):
            session.delete(document)
        session.delete(cooperative)
    session.commit()
    for path in files:
        path.unlink(missing_ok=True)


@router.get("/cooperatives/{cooperative_id}", response_model=CooperativeOverview)
def get_cooperative(cooperative_id: int, session: SessionDep, rules: RulesDep):
    return cooperative_service.build_overview(_load(session, cooperative_id), rules)


@router.patch("/cooperatives/{cooperative_id}", response_model=CooperativeOverview)
def update_cooperative(cooperative_id: int, update: CooperativeUpdate, session: SessionDep, rules: RulesDep):
    cooperative = _load(session, cooperative_id)
    changes = update.model_dump(exclude_unset=True)
    if "organisation_number" in changes and changes["organisation_number"] != cooperative.organisation_number:
        taken = session.scalar(select(HousingCooperative).where(
            HousingCooperative.organisation_number == changes["organisation_number"]))
        if taken:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"Organisationsnumret används redan av {taken.name}. Flytta dokumenten dit i stället.")
    if "land_tenure" in changes:
        cooperative.land_tenure_source = "Angivet manuellt."
    for field, value in changes.items():
        setattr(cooperative, field, value)
    session.commit()
    return cooperative_service.build_overview(_load(session, cooperative_id), rules)


@router.delete("/cooperatives/{cooperative_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cooperative(cooperative_id: int, session: SessionDep,
                       settings: Annotated[Settings, Depends(get_settings)]):
    """Deletes the cooperative together with its documents and all figures."""
    cooperative = _load(session, cooperative_id)
    for document in list(cooperative.documents):
        document_service.delete_document(session, settings, document)
    session.delete(cooperative)
    session.commit()


@router.post("/cooperatives/{cooperative_id}/observations", response_model=CooperativeOverview,
             status_code=status.HTTP_201_CREATED)
def add_manual_observation(cooperative_id: int, request: ManualObservationCreate, session: SessionDep,
                           rules: RulesDep):
    cooperative = _load(session, cooperative_id)
    definition = METRICS.get(request.metric_key)
    if definition is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Okänt nyckeltal: {request.metric_key}")
    session.add(FinancialObservation(
        cooperative=cooperative, source_document=None, metric_key=request.metric_key,
        fiscal_year=request.fiscal_year, value=request.value, unit=definition.unit.value, source_page=None,
        printed_label=None, extraction_method=ExtractionMethod.MANUAL.value,
        verification_status=VerificationStatus.USER_ENTERED.value, note=request.note,
    ))
    session.commit()
    return cooperative_service.build_overview(_load(session, cooperative_id), rules)


@router.post("/observations/{observation_id}/verify", response_model=CooperativeOverview)
def verify_observation(observation_id: int, session: SessionDep, rules: RulesDep):
    """Mark an extracted value as checked against the source by the user."""
    observation = _observation(session, observation_id)
    observation.verification_status = VerificationStatus.VERIFIED.value
    session.commit()
    return cooperative_service.build_overview(_load(session, observation.cooperative_id), rules)


@router.delete("/observations/{observation_id}", response_model=CooperativeOverview)
def delete_manual_observation(observation_id: int, session: SessionDep, rules: RulesDep):
    """Only manually entered values can be deleted; extracted values belong to their document."""
    observation = _observation(session, observation_id)
    if observation.extraction_method != ExtractionMethod.MANUAL.value:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Värden från dokument kan inte tas bort. Ange ett manuellt värde som ersätter det.")
    cooperative_id = observation.cooperative_id
    session.delete(observation)
    session.commit()
    return cooperative_service.build_overview(_load(session, cooperative_id), rules)


@router.put("/cooperatives/{cooperative_id}/maintenance/{name}", response_model=CooperativeOverview)
def answer_maintenance(cooperative_id: int, name: str, request: MaintenanceAnswerIn, session: SessionDep,
                       rules: RulesDep):
    """The user's answer to a maintenance question. Only the user answers these; extraction never does."""
    cooperative = _load(session, cooperative_id)
    if rules.score is None or f"maintenance:{name}" not in rules.score.maintenance:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Okänd underhållsfråga.")
    cooperative_service.answer_maintenance(session, cooperative, name, request.answer)
    return cooperative_service.build_overview(_load(session, cooperative_id), rules)


def _load(session: Session, cooperative_id: int) -> HousingCooperative:
    session.expire_all()  # Make sure relationships reflect the latest commit.
    cooperative = cooperative_service.load_cooperative(session, cooperative_id)
    if cooperative is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Föreningen finns inte.")
    return cooperative


def _observation(session: Session, observation_id: int) -> FinancialObservation:
    observation = session.get(FinancialObservation, observation_id)
    if observation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Värdet finns inte.")
    return observation
