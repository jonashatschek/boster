"""Side-by-side comparison of saved apartments.

Each row is one fact, calculation or cooperative figure; each cell keeps the status and
source it has on the property page. Nothing is ranked, and nothing missing is filled in.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain.metrics import METRICS
from app.domain.provenance import VerificationStatus
from app.domain.risk import RiskRules
from app.models import Property
from app.schemas import (
    ComparedProperty, CooperativeOverview, DerivedValue, PropertyComparison, PropertyComparisonCell,
    PropertyComparisonRow,
)
from app.services.cooperatives import build_overview, load_cooperative
from app.services.properties import FIELDS, derived_values, listing_field, missing_important_fields
from app.services.transport import format_walk, transport_info
from app.transport.nearby import TRANSPORT_LABELS, TransportType

MIN_PROPERTIES = 2
MAX_PROPERTIES = 4

MISSING = VerificationStatus.MISSING.value
NO_COOPERATIVE = "Ingen förening kopplad"

# (group, keys). A key is a listing field, or a calculated value from `derived_values` if in _CALCULATED.
_CALCULATED = {"price_per_sqm", "fee_per_sqm_year"}
_LAYOUT: list[tuple[str, list[str]]] = [
    ("Bostaden", ["asking_price", "price_per_sqm", "living_area", "rooms", "monthly_fee", "fee_per_sqm_year",
                  "construction_year"]),
    ("Läge", ["address", "neighborhood", "municipality"]),
    ("Egenskaper", ["floor", "elevator", "balcony", "energy_class", "fee_includes"]),
]
_ESTIMATES = ["debt_share", "fee_increase_per_percentage_point"]
_ESTIMATE_NOTE = ("Uppskattning baserad på boarean, inte på lägenhetens andelstal. "
                  "Jämförelsen bygger här på uppskattningar, inte kontrollerade uppgifter.")


@dataclass
class _Apartment:
    listing: Property
    overview: CooperativeOverview | None
    derived: dict[str, DerivedValue]

    @property
    def name(self) -> str:
        return self.listing.address or self.listing.title or f"Bostad {self.listing.id}"


def compare_properties(session: Session, listings: list[Property], rules: RiskRules) -> PropertyComparison:
    apartments, overviews = [], {}
    for listing in listings:
        cooperative_id = listing.housing_cooperative_id
        if cooperative_id and cooperative_id not in overviews:  # Apartments in the same cooperative share it.
            cooperative = load_cooperative(session, cooperative_id)
            overviews[cooperative_id] = build_overview(cooperative, rules) if cooperative else None
        overview = overviews.get(cooperative_id) if cooperative_id else None
        derived = {value.key: value for value in derived_values(listing, overview)}
        apartments.append(_Apartment(listing, overview, derived))

    rows = []
    for group, keys in _LAYOUT:
        rows += [_derived_row(key, group, apartments) if key in _CALCULATED else _field_row(key, group, apartments)
                 for key in keys]
        if group == "Läge":
            rows += _transport_rows(apartments)
    rows += _cooperative_rows(apartments, rules)
    rows += [_derived_row(key, "Uppskattningar", apartments, is_estimate=True) for key in _ESTIMATES]
    rows.append(_field_row("fee_changes", "Underhåll", apartments))
    rows.append(_maintenance_row(apartments))

    return PropertyComparison(properties=[_compared(a) for a in apartments], rows=rows, warnings=_warnings(apartments))


def _compared(apartment: _Apartment) -> ComparedProperty:
    listing, overview = apartment.listing, apartment.overview
    return ComparedProperty(
        id=listing.id, title=listing.title, address=listing.address, source_name=listing.source_name,
        cooperative_id=overview.cooperative.id if overview else None,
        cooperative_name=overview.cooperative.name if overview else listing.cooperative_name,
        fiscal_year=overview.latest_fiscal_year if overview else None,
        overall_level=overview.risk.overall_level if overview else None,
        overall_label=overview.risk.overall_label if overview else None,
        maintenance=overview.findings if overview else [],
    )


def _field_row(key: str, group: str, apartments: list[_Apartment]) -> PropertyComparisonRow:
    spec = FIELDS[key]
    cells = []
    for apartment in apartments:
        field = listing_field(apartment.listing, key, spec)
        cells.append(PropertyComparisonCell(property_id=apartment.listing.id, value=field.value, status=field.status,
                                            excerpt=field.excerpt, note=field.note))
    return PropertyComparisonRow(key=key, group=group, label=spec.label, kind=spec.kind, unit=spec.unit, cells=cells)


def _derived_row(key: str, group: str, apartments: list[_Apartment], is_estimate: bool = False) -> PropertyComparisonRow:
    cells = []
    for apartment in apartments:
        derived = apartment.derived[key]
        formula = derived.formula
        if derived.inputs:
            formula += " (" + ", ".join(f"{name}: {value}" for name, value in derived.inputs.items()) + ")"
        if derived.value is None:
            if is_estimate and apartment.overview is None:
                reason = _no_cooperative_note(apartment.listing)
            elif derived.missing_inputs:
                reason = f"Saknar {', '.join(derived.missing_inputs).lower()}."
            else:
                reason = derived.note
            cells.append(PropertyComparisonCell(property_id=apartment.listing.id, value=None, status=MISSING,
                                                excerpt=formula, note=reason))
        else:
            status = VerificationStatus.ESTIMATED.value if is_estimate else "calculated"
            cells.append(PropertyComparisonCell(property_id=apartment.listing.id, value=derived.value,
                                                status=status, excerpt=formula, note=derived.note))
    first = apartments[0].derived[key]
    return PropertyComparisonRow(key=key, group=group, label=first.label, kind="number", unit=first.unit,
                                 is_estimate=is_estimate, note=_ESTIMATE_NOTE if is_estimate else None, cells=cells)


def _maintenance_row(apartments: list[_Apartment]) -> PropertyComparisonRow:
    """Which topics the cooperative's reports mention. The quotes themselves are in `properties[].maintenance`."""
    cells = []
    for apartment in apartments:
        property_id = apartment.listing.id
        if apartment.overview is None:
            cells.append(PropertyComparisonCell(property_id=property_id, value=None, status=MISSING,
                                                note=_no_cooperative_note(apartment.listing)))
            continue
        topics = list(dict.fromkeys(finding.topic for finding in apartment.overview.findings))
        if topics:
            cells.append(PropertyComparisonCell(property_id=property_id, value=", ".join(topics),
                                                status=VerificationStatus.EXTRACTED.value))
        else:
            cells.append(PropertyComparisonCell(property_id=property_id, value=None, status=MISSING,
                                                note="Inga omnämnanden hittades i föreningens dokument."))
    return PropertyComparisonRow(key="maintenance_topics", group="Underhåll",
                                 label="Underhåll och lån enligt årsredovisningen", kind="findings", unit=None,
                                 cells=cells)


_TRANSPORT_NOTES = {
    "not_fetched": "Kollektivtrafiken har inte hämtats. Öppna bostadens sida för att hämta den.",
    "pending": "Hämtningen av kollektivtrafik avbröts eller pågår fortfarande. Öppna bostadens sida för att hämta den.",
    "stale": "Adressen har ändrats sedan kollektivtrafiken hämtades. Öppna bostadens sida för att hämta den igen.",
    "choose": "Adressen finns på flera ställen. Välj adress på bostadens sida.",
    "skipped": "Bostaden visas utan kollektivtrafik. Välj adress på bostadens sida för att hämta den.",
}


def _transport_rows(apartments: list[_Apartment]) -> list[PropertyComparisonRow]:
    """The nearest metro, local train and bus stop, with the walk there, as on the property page."""
    infos = [transport_info(apartment.listing) for apartment in apartments]
    rows = []
    for kind in TransportType:
        cells = []
        for apartment, info in zip(apartments, infos):
            property_id = apartment.listing.id
            if info.status != "done":
                note = _TRANSPORT_NOTES.get(info.status) or info.message
                cells.append(PropertyComparisonCell(property_id=property_id, value=None, status=MISSING, note=note))
                continue
            stop = next(s for s in info.stops if s.type == kind.value)
            if stop.walking_metres is None:
                cells.append(PropertyComparisonCell(property_id=property_id, value=None, status=MISSING,
                                                    note=stop.note))
                continue
            value = f"{stop.name}, {format_walk(stop.walking_metres, stop.walking_seconds)} till fots"
            excerpt = (f"{info.source} Hämtad {info.retrieved_at:%Y-%m-%d} för ”{info.looked_up_query}”. "
                       f"Närmaste hållplats fågelvägen; gångvägen är beräknad dit.")
            cells.append(PropertyComparisonCell(property_id=property_id, value=value, status=stop.status,
                                                excerpt=excerpt, note=info.message))
        rows.append(PropertyComparisonRow(key=f"transport:{kind.value}", group="Läge",
                                          label=f"Närmaste {TRANSPORT_LABELS[kind].lower()}", kind="text", unit=None,
                                          cells=cells))
    return rows


def _no_cooperative_note(listing: Property) -> str:
    if listing.cooperative_name:
        return f"{NO_COOPERATIVE}. Annonsen anger ”{listing.cooperative_name}”."
    return f"{NO_COOPERATIVE}."


def _cooperative_rows(apartments: list[_Apartment], rules: RiskRules) -> list[PropertyComparisonRow]:
    name_cells, overall_cells = [], []
    for apartment in apartments:
        overview, property_id = apartment.overview, apartment.listing.id
        if overview is None:
            note = _no_cooperative_note(apartment.listing)
            name_cells.append(PropertyComparisonCell(property_id=property_id, value=None, status=MISSING, note=note))
            overall_cells.append(PropertyComparisonCell(property_id=property_id, value=None, status=MISSING, note=note))
            continue
        name_cells.append(_cooperative_name_cell(apartment))
        overall_cells.append(PropertyComparisonCell(
            property_id=property_id, value=overview.risk.overall_label, status="calculated",
            note=overview.risk.overall_rule, level=overview.risk.overall_level,
            level_label=overview.risk.overall_label, fiscal_year=overview.risk.fiscal_year,
        ))

    rows = [
        PropertyComparisonRow(key="cooperative", group="Förening", label="Förening", kind="text", unit=None,
                              cells=name_cells),
        PropertyComparisonRow(key="cooperative_overall", group="Förening", label="Samlad riskbedömning",
                              kind="level", unit=None, cells=overall_cells),
    ]
    for key in rules.indicators:
        definition = METRICS[key]
        rows.append(PropertyComparisonRow(
            key=f"risk:{key}", group="Förening", label=definition.label, kind="number", unit=definition.unit.value,
            note=definition.description, cells=[_indicator_cell(apartment, key) for apartment in apartments],
        ))
    return rows


def _cooperative_name_cell(apartment: _Apartment) -> PropertyComparisonCell:
    """The linked cooperative, with how the link was made (exact name match or by the user)."""
    listing, cooperative = apartment.listing, apartment.overview.cooperative
    link = (listing.field_sources or {}).get("housing_cooperative", {})
    if link.get("method") == "name_match":
        how = f"Kopplad på exakt namn: annonsen anger ”{link.get('excerpt')}”."
        status = link.get("status", VerificationStatus.EXTRACTED.value)
    else:  # Linked by the user (the only other way a link is made).
        how, status = "Kopplad manuellt.", VerificationStatus.USER_ENTERED.value
    return PropertyComparisonCell(
        property_id=listing.id, value=cooperative.name, status=status, excerpt=how,
        note=f"Org.nr {cooperative.organisation_number}" if cooperative.organisation_number else None,
    )


def _indicator_cell(apartment: _Apartment, key: str) -> PropertyComparisonCell:
    overview, property_id = apartment.overview, apartment.listing.id
    if overview is None:
        return PropertyComparisonCell(property_id=property_id, value=None, status=MISSING,
                                      note=_no_cooperative_note(apartment.listing))
    year = overview.latest_fiscal_year
    series = next((s for s in overview.metrics if s.key == key), None)
    current = next((v for v in series.values if v.fiscal_year == year), None) if series else None
    indicator = next((i for i in overview.risk.indicators if i.key == key), None)
    if current is None or current.display_value is None:
        status = current.display_status if current else MISSING
        return PropertyComparisonCell(property_id=property_id, value=None, status=status, fiscal_year=year,
                                      note=f"Saknas för räkenskapsår {year}." if year else "Saknas.")
    return PropertyComparisonCell(
        property_id=property_id, value=current.display_value, status=current.display_status, fiscal_year=year,
        level=indicator.level if indicator else None, level_label=indicator.level_label if indicator else None,
        excerpt=_metric_source(current), note=current.warning,
    )


def _metric_source(value) -> str | None:
    """Where a cooperative figure comes from: the report page and printed label, or our formula."""
    if value.display_origin == "calculated" and value.calculated:
        return f"Beräknat: {value.calculated.formula}"
    if value.reported and value.reported.sources:
        parts = []
        for source in value.reported.sources:
            if source.document_name is None:
                parts.append("Manuellt angivet")
                continue
            page = f", s. {source.page}" if source.page else ""
            label = f": ”{source.printed_label}”" if source.printed_label else ""
            parts.append(f"{source.document_name}{page}{label}")
        return "; ".join(parts)
    return None


def _warnings(apartments: list[_Apartment]) -> list[str]:
    warnings = []
    linked = [a for a in apartments if a.overview]
    if len({a.overview.latest_fiscal_year for a in linked}) > 1:
        listing = ", ".join(f"{a.overview.cooperative.name} {a.overview.latest_fiscal_year or 'okänt år'}"
                            for a in linked)
        warnings.append(f"Föreningarna jämförs på olika räkenskapsår: {listing}.")
    for apartment in apartments:
        if apartment.overview is None:
            warnings.append(f"{apartment.name} har ingen kopplad förening, så föreningens nyckeltal och "
                            f"uppskattningarna saknas. Ladda upp föreningens årsredovisning eller koppla en förening "
                            f"på bostadens sida.")
    debt_measures = {a.derived["debt_share"].formula for a in apartments if a.derived["debt_share"].value is not None}
    if len(debt_measures) > 1:
        warnings.append("Uppskattningarna av lån och avgiftshöjning bygger på olika mått: "
                        + " respektive ".join(f"”{measure}”" for measure in sorted(debt_measures))
                        + ". Skuldsättning per kvm totalyta och per kvm bostadsrättsyta är inte jämförbara, "
                          "så jämför dessa rader med försiktighet.")
    for apartment in apartments:
        missing_fields = missing_important_fields(apartment.listing)
        if apartment.overview:  # The linked cooperative makes the listing's cooperative name unnecessary.
            missing_fields.pop("cooperative_name", None)
        missing = [label.lower() for label in missing_fields.values()]
        if missing:
            warnings.append(f"{apartment.name} saknar {', '.join(missing)}. Saknade värden visas som ”Saknas”, "
                            f"aldrig som noll.")
    return warnings
