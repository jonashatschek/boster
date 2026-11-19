from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_risk_rules, get_session
from app.domain.risk import RiskRules
from app.models import HousingCooperative, Property
from app.schemas import (
    PropertyCooperativeLink, PropertyFromText, PropertyListItem, PropertyOverview, PropertyText,
    PropertyUpdate, TransportStep, TransportStepResult,
)
from app.services import properties as property_service
from app.services import transport as transport_service
from app.services.properties import PropertyError
from app.services.transport import TransportChoiceError, TransportStepError

router = APIRouter(prefix="/api/properties", tags=["properties"])

SessionDep = Annotated[Session, Depends(get_session)]
RulesDep = Annotated[RiskRules, Depends(get_risk_rules)]


@router.get("", response_model=list[PropertyListItem])
def list_properties(session: SessionDep, rules: RulesDep):
    return property_service.list_properties(session, rules)


@router.post("/from-text", response_model=PropertyOverview, status_code=status.HTTP_201_CREATED)
def add_from_text(request: PropertyFromText, session: SessionDep, rules: RulesDep):
    try:
        listing = property_service.create_from_text(session, request.text, request.url)
    except PropertyError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    return property_service.build_property_overview(session, listing, rules)


@router.get("/{property_id}", response_model=PropertyOverview)
def get_property(property_id: int, session: SessionDep, rules: RulesDep):
    return property_service.build_property_overview(session, _load(session, property_id), rules)


@router.post("/{property_id}/text", response_model=PropertyOverview)
def add_listing_text(property_id: int, request: PropertyText, session: SessionDep, rules: RulesDep):
    """Analyse pasted listing text for an existing property. Manual values are kept."""
    listing = _load(session, property_id)
    property_service.apply_text(session, listing, request.text)
    return property_service.build_property_overview(session, listing, rules)


@router.patch("/{property_id}", response_model=PropertyOverview)
def update_property(property_id: int, update: PropertyUpdate, session: SessionDep, rules: RulesDep):
    listing = _load(session, property_id)
    property_service.update_fields(session, listing, update.model_dump(exclude_unset=True))
    return property_service.build_property_overview(session, listing, rules)


@router.post("/{property_id}/fields/{field}/verify", response_model=PropertyOverview)
def verify_field(property_id: int, field: str, session: SessionDep, rules: RulesDep):
    listing = _load(session, property_id)
    if field not in property_service.FIELDS and field != "description":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Okänt fält.")
    try:
        property_service.verify_field(session, listing, field)
    except PropertyError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    return property_service.build_property_overview(session, listing, rules)


@router.put("/{property_id}/cooperative", response_model=PropertyOverview)
def link_cooperative(property_id: int, request: PropertyCooperativeLink, session: SessionDep, rules: RulesDep):
    listing = _load(session, property_id)
    cooperative = None
    if request.cooperative_id is not None:
        cooperative = session.get(HousingCooperative, request.cooperative_id)
        if cooperative is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Föreningen finns inte.")
    property_service.link_cooperative(session, listing, cooperative)
    return property_service.build_property_overview(session, listing, rules)


@router.post("/{property_id}/transport/step", response_model=TransportStepResult)
def transport_step(property_id: int, step: TransportStep, session: SessionDep):
    """One step of the public transport lookup: read a response and say which request to make next."""
    try:
        return transport_service.run_step(session, _load(session, property_id), step)
    except TransportStepError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except TransportChoiceError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_property(property_id: int, session: SessionDep):
    session.delete(_load(session, property_id))
    session.commit()


def _load(session: Session, property_id: int) -> Property:
    listing = property_service.load_property(session, property_id)
    if listing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bostaden finns inte.")
    return listing
