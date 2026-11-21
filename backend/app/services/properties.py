"""Apartments: import from listings, manual corrections, cooperative linking and analysis."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.provenance import VerificationStatus
from app.domain.risk import RiskRules
from app.listings.sources import InvalidListingUrl, source_name, validate_listing_url
from app.listings.text_extraction import ListingFacts, extract_from_text
from app.models import HousingCooperative, Property
from app.schemas import (
    CooperativeListItem, DerivedValue, LinkedCooperative, PropertyField, PropertyListItem, PropertyOverview,
)
from app.services.cooperatives import (
    CORE_METRICS, build_overview, list_cooperatives, load_cooperative, score_label, score_value,
)
from app.services.transport import transport_info


class RetrievalStatus(StrEnum):
    PASTED = "pasted"  # Read from text pasted by the user.
    MANUAL = "manual"  # Entered by hand.
    # Earlier versions fetched listing pages; data imported from them can still have these.
    FETCHED = "fetched"
    FETCH_FAILED = "fetch_failed"


@dataclass(frozen=True)
class FieldSpec:
    label: str
    kind: str
    unit: str | None = None
    important: bool = False  # Listed as missing when absent.


FIELDS: dict[str, FieldSpec] = {
    "address": FieldSpec("Adress", "text", important=True),
    "neighborhood": FieldSpec("Område", "text"),
    "municipality": FieldSpec("Kommun", "text"),
    "asking_price": FieldSpec("Utgångspris", "number", "kr", important=True),
    "living_area": FieldSpec("Boarea", "number", "m²", important=True),
    "rooms": FieldSpec("Antal rum", "number", "rum", important=True),
    "monthly_fee": FieldSpec("Månadsavgift", "number", "kr/mån", important=True),
    "fee_includes": FieldSpec("I avgiften ingår", "text"),
    "fee_changes": FieldSpec("Kommande avgiftsförändringar", "text"),
    "floor": FieldSpec("Våning", "text"),
    "elevator": FieldSpec("Hiss", "boolean"),
    "balcony": FieldSpec("Balkong/uteplats", "boolean"),
    "construction_year": FieldSpec("Byggår", "integer"),
    "energy_class": FieldSpec("Energiklass", "text"),
    "cooperative_name": FieldSpec("Förening enligt annonsen", "text", important=True),
    "listing_date": FieldSpec("Publicerad", "date"),
    "title": FieldSpec("Rubrik", "text"),
}
_EXTRACTABLE = set(FIELDS) | {"description", "balcony_description"}
_USER_STATUSES = {VerificationStatus.USER_ENTERED.value, VerificationStatus.VERIFIED.value}


class PropertyError(Exception):
    """A problem the user can act on. The message is shown in the UI, in Swedish."""


# --- Creating and updating ------------------------------------------------------------------


def create_from_text(session: Session, text: str, url: str | None = None) -> Property:
    url = url.strip() if url else None
    if url:
        try:
            validate_listing_url(url)
        except InvalidListingUrl as error:
            raise PropertyError(str(error)) from error
    listing = Property(source_url=url, source_name=source_name(url) if url else "Inklistrad text",
                       field_sources={}, retrieval_status=RetrievalStatus.PASTED.value)
    session.add(listing)
    apply_text(session, listing, text)
    return listing


def apply_text(session: Session, listing: Property, text: str) -> None:
    """(Re-)analyse pasted listing text. Values the user entered or verified are never overwritten."""
    facts = extract_from_text(text)
    _apply_facts(listing, facts, source="Inklistrad annonstext")
    listing.listing_text = text[:200_000]
    listing.retrieval_status = RetrievalStatus.PASTED.value
    listing.retrieved_at = datetime.now(timezone.utc)
    _link_by_name(session, listing)
    session.commit()


def update_fields(session: Session, listing: Property, changes: dict) -> None:
    """Manual corrections. A manual value is marked as entered by the user and wins over extraction."""
    sources = dict(listing.field_sources or {})
    for name, value in changes.items():
        setattr(listing, name, value)
        if value is None:
            sources.pop(name, None)
        else:
            sources[name] = _source(VerificationStatus.USER_ENTERED, "manual", None)
    listing.field_sources = sources
    if "cooperative_name" in changes:
        _link_by_name(session, listing)
    session.commit()


def verify_field(session: Session, listing: Property, name: str) -> None:
    sources = dict(listing.field_sources or {})
    if name not in sources or getattr(listing, name, None) is None:
        raise PropertyError("Det finns inget värde att markera som kontrollerat.")
    sources[name] = {**sources[name], "status": VerificationStatus.VERIFIED.value}
    listing.field_sources = sources
    session.commit()


def link_cooperative(session: Session, listing: Property, cooperative: HousingCooperative | None) -> None:
    listing.cooperative = cooperative
    sources = dict(listing.field_sources or {})
    if cooperative is None:
        sources.pop("housing_cooperative", None)
    else:
        sources["housing_cooperative"] = _source(VerificationStatus.USER_ENTERED, "manual", None)
    listing.field_sources = sources
    session.commit()


def link_matching_properties(session: Session, cooperative: HousingCooperative) -> None:
    """Called when a cooperative is created from a report: link waiting listings with exactly that name."""
    key = normalize_cooperative_name(cooperative.name)
    if not key:
        return
    for listing in session.scalars(select(Property).where(Property.housing_cooperative_id.is_(None))):
        if listing.cooperative_name and normalize_cooperative_name(listing.cooperative_name) == key:
            listing.cooperative = cooperative
            sources = dict(listing.field_sources or {})
            sources["housing_cooperative"] = _source(VerificationStatus.EXTRACTED, "name_match", listing.cooperative_name)
            listing.field_sources = sources


def _apply_facts(listing: Property, facts: ListingFacts, source: str) -> None:
    sources = dict(listing.field_sources or {})
    for name, extracted in facts.fields.items():
        if name not in _EXTRACTABLE:
            continue
        if sources.get(name, {}).get("status") in _USER_STATUSES:
            continue  # The user's value stands.
        setattr(listing, name, extracted.value)
        sources[name] = _source(VerificationStatus.EXTRACTED, extracted.method, f"{source}: ”{extracted.excerpt}”",
                                extracted.note)
    listing.field_sources = sources


def _source(status: VerificationStatus, method: str, excerpt: str | None, note: str | None = None) -> dict:
    return {"status": status.value, "method": method, "excerpt": excerpt, "note": note,
            "updated_at": datetime.now(timezone.utc).isoformat()}


def missing_important_fields(listing: Property) -> dict[str, str]:
    """Important facts the listing lacks: field name → label.

    The listing's cooperative name is not needed once a cooperative is linked.
    """
    return {name: spec.label for name, spec in FIELDS.items()
            if spec.important and getattr(listing, name) is None
            and not (name == "cooperative_name" and listing.housing_cooperative_id)}


def _completeness_message(listing: Property) -> str | None:
    """Built from the current values each time, so it never goes stale. Only for pasted listings."""
    if listing.retrieval_status != RetrievalStatus.PASTED.value:
        return None
    missing = list(missing_important_fields(listing).values())
    if not missing:
        return None
    return f"Kunde inte hitta: {', '.join(missing).lower()}. Fyll i dem manuellt eller klistra in annonstexten."


# --- Cooperative matching --------------------------------------------------------------------


def normalize_cooperative_name(name: str) -> str:
    """Comparable form of a cooperative name: "HSB Brf Segelflygaren i Stockholm" → "segelflygaren".

    Only prefixes and a trailing "i <ort>" are removed. Numbers and other words are kept,
    so "Byamännen" and "Byamännen 2" stay different.
    """
    text = name.lower().replace("ﬂ", "fl")
    text = re.sub(r"[\"'”“.,]", " ", text)
    text = re.sub(r"^\s*(hsb|riksbyggen|riksbyggens|sbc)\s+", "", text)
    text = re.sub(r"^\s*(bostadsrättsföreningen|bostadsrättsförening|bostadsrättföreningen|brf)\s+", "", text)
    text = re.sub(r"\s+i\s+[\wåäö]+\s*$", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _link_by_name(session: Session, listing: Property) -> None:
    if listing.housing_cooperative_id or not listing.cooperative_name:
        return
    match = _cooperative_by_name(session, listing.cooperative_name)
    if match:
        listing.cooperative = match
        sources = dict(listing.field_sources or {})
        sources["housing_cooperative"] = _source(VerificationStatus.EXTRACTED, "name_match", listing.cooperative_name)
        listing.field_sources = sources


def _cooperative_by_name(session: Session, name: str) -> HousingCooperative | None:
    key = normalize_cooperative_name(name)
    matches = [c for c in session.scalars(select(HousingCooperative)) if normalize_cooperative_name(c.name) == key]
    return matches[0] if len(matches) == 1 else None  # Ambiguous matches are left to the user.


# --- Reading ----------------------------------------------------------------------------------


def load_property(session: Session, property_id: int) -> Property | None:
    return session.scalar(select(Property).where(Property.id == property_id))


def list_properties(session: Session, rules: RiskRules) -> list[PropertyListItem]:
    listings = session.scalars(select(Property).order_by(Property.updated_at.desc())).all()
    overviews = {}
    items = []
    for listing in listings:
        cooperative_id = listing.housing_cooperative_id
        if cooperative_id and cooperative_id not in overviews:
            overviews[cooperative_id] = build_overview(load_cooperative(session, cooperative_id), rules)
        overview = overviews.get(cooperative_id) if cooperative_id else None
        items.append(PropertyListItem(
            id=listing.id, title=listing.title, address=listing.address, source_name=listing.source_name,
            asking_price=listing.asking_price, living_area=listing.living_area, rooms=listing.rooms,
            monthly_fee=listing.monthly_fee, cooperative_id=cooperative_id,
            cooperative_name=overview.cooperative.name if overview else listing.cooperative_name,
            cooperative_score=score_value(overview.score) if overview else None,
            cooperative_score_label=score_label(overview.score) if overview else None,
            retrieval_status=listing.retrieval_status, updated_at=listing.updated_at,
        ))
    return items


def build_property_overview(session: Session, listing: Property, rules: RiskRules) -> PropertyOverview:
    linked = None
    cooperative_overview = None
    if listing.housing_cooperative_id:
        cooperative = load_cooperative(session, listing.housing_cooperative_id)
        if cooperative:
            cooperative_overview = build_overview(cooperative, rules)
            linked = LinkedCooperative(
                id=cooperative.id, name=cooperative.name, organisation_number=cooperative.organisation_number,
                fiscal_year=cooperative_overview.latest_fiscal_year,
                score=score_value(cooperative_overview.score), score_label=score_label(cooperative_overview.score),
                land_tenure=cooperative.land_tenure,
                indicators=cooperative_overview.risk.indicators,
                completeness_available=len(cooperative_overview.completeness.available),
                completeness_total=len(CORE_METRICS),
            )

    suggestions: list[CooperativeListItem] = []
    if linked is None and listing.cooperative_name:
        key = normalize_cooperative_name(listing.cooperative_name)
        suggestions = [c for c in list_cooperatives(session, rules)
                       if key and (key in normalize_cooperative_name(c.name) or normalize_cooperative_name(c.name) in key)]

    return PropertyOverview(
        id=listing.id, title=listing.title, source_url=listing.source_url, source_name=listing.source_name,
        retrieval_status=listing.retrieval_status, retrieval_message=_completeness_message(listing),
        retrieved_at=listing.retrieved_at, created_at=listing.created_at, updated_at=listing.updated_at,
        fields=[listing_field(listing, name, spec) for name, spec in FIELDS.items()],
        description=listing_field(listing, "description", FieldSpec("Beskrivning", "longtext")),
        derived=derived_values(listing, cooperative_overview),
        cooperative=linked, cooperative_suggestions=suggestions,
        missing=list(missing_important_fields(listing).values()),
        has_listing_text=bool(listing.listing_text),
        transport=transport_info(listing),
    )


def listing_field(listing: Property, name: str, spec: FieldSpec) -> PropertyField:
    value = getattr(listing, name)
    source = (listing.field_sources or {}).get(name, {})
    if name == "balcony" and value and listing.balcony_description:
        note = f"Annonsen anger: {listing.balcony_description}"
    else:
        note = source.get("note")
    return PropertyField(
        key=name, label=spec.label, value=value, kind=spec.kind, unit=spec.unit,
        status=source.get("status", VerificationStatus.MISSING.value) if value is not None else VerificationStatus.MISSING.value,
        method=source.get("method"), excerpt=source.get("excerpt"), note=note,
    )


# --- Calculated figures -------------------------------------------------------------------------


def _format_number(value: float, unit: str) -> str:
    text = f"{value:,.0f}".replace(",", " ") if abs(value) >= 100 else f"{value:g}".replace(".", ",")
    return f"{text} {unit}"


def derived_values(listing: Property, cooperative_overview) -> list[DerivedValue]:
    area, price, fee = listing.living_area, listing.asking_price, listing.monthly_fee
    values = [
        _derived("price_per_sqm", "Pris per kvm", "kr/m²", "Utgångspris / boarea",
                 {"Utgångspris": (price, "kr"), "Boarea": (area, "m²")},
                 lambda: price / area),
        _derived("fee_per_sqm_year", "Årsavgift per kvm", "kr/m²",
                 "Månadsavgift × 12 / boarea", {"Månadsavgift": (fee, "kr/mån"), "Boarea": (area, "m²")},
                 lambda: fee * 12 / area,
                 note="Jämför med föreningens genomsnittliga årsavgift per kvm."),
    ]

    debt_per_sqm, debt_label, debt_year, debt_note = _cooperative_debt_per_sqm(cooperative_overview)
    debt_inputs = {"Boarea": (area, "m²"), debt_label: (debt_per_sqm, "kr/m²")}
    share_note = ("En uppskattning: lägenhetens verkliga andel bestäms av dess andelstal, som kan skilja sig från "
                  "andelen av ytan.")
    if debt_year:
        share_note += f" Föreningens skuldsättning avser räkenskapsår {debt_year}."
    if debt_note:
        share_note += " " + debt_note
    values.append(_derived("debt_share", "Lägenhetens andel av föreningens lån (ungefärlig)", "kr",
                           f"Boarea × {debt_label.lower()}", debt_inputs,
                           lambda: area * debt_per_sqm, note=share_note))
    values.append(_derived("fee_increase_per_percentage_point",
                           "Möjlig avgiftshöjning om räntan stiger 1 procentenhet", "kr/mån",
                           f"Boarea × {debt_label.lower()} × 1 % / 12", debt_inputs,
                           lambda: area * debt_per_sqm * 0.01 / 12,
                           note="Förutsätter att föreningen höjer avgiften för att täcka hela räntehöjningen, "
                                "och att alla lån får den nya räntan. " + share_note))
    return values


def _cooperative_debt_per_sqm(overview) -> tuple[float | None, str, int | None, str | None]:
    """Debt per m² of tenant-owned area if known, else per m² of total area (with a note)."""
    label = "Föreningens skuldsättning per kvm bostadsrättsyta"
    if overview is None:
        return None, label, None, None
    year = overview.latest_fiscal_year
    for key, chosen_label, note in (
        ("debt_per_sqm_tenant_owned_area", label, None),
        ("debt_per_sqm_total_area", "Föreningens skuldsättning per kvm totalyta",
         "Skuldsättning per kvm bostadsrättsyta saknas, så skuldsättning per kvm totalyta används. "
         "Det ger en något lägre andel."),
    ):
        series = next((s for s in overview.metrics if s.key == key), None)
        value = next((v.display_value for v in series.values if v.fiscal_year == year), None) if series else None
        if value is not None:
            return value, chosen_label, year, note
    return None, label, year, None


def _derived(key: str, label: str, unit: str, formula: str, inputs: dict[str, tuple[float | None, str]],
             compute, note: str | None = None) -> DerivedValue:
    missing = [name for name, (value, _) in inputs.items() if value is None]
    shown = {name: _format_number(value, input_unit) for name, (value, input_unit) in inputs.items() if value is not None}
    if missing:
        return DerivedValue(key=key, label=label, value=None, unit=unit, formula=formula, inputs=shown,
                            missing_inputs=missing, note=note)
    try:
        value = compute()
    except ZeroDivisionError:
        return DerivedValue(key=key, label=label, value=None, unit=unit, formula=formula, inputs=shown,
                            missing_inputs=[], note="Kan inte beräknas eftersom nämnaren är noll.")
    return DerivedValue(key=key, label=label, value=value, unit=unit, formula=formula, inputs=shown,
                        missing_inputs=[], note=note)

