"""Public transport lookup for an apartment, one step at a time.

The backend makes no network calls. For each step it tells the frontend which request to
make; the frontend posts back the raw response, and the backend reads it, stores what it
found and asks for the next request:

    start → geocode (Nominatim) → [choose] → stops (Trafiklab ResRobot) → walking (Valhalla) → done

The lookup waits at "choose" when the address is ambiguous: no municipality in the listing, or
not exactly one hit with the listing's municipality and house number. The user then picks one
of Nominatim's hits (which also sets the municipality) or continues without transport ("skipped").

A failure at any step ends the lookup with a reason. The stored result keeps the address it
was looked up with, so it is shown as stale once the apartment's address changes.
"""

import json
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

from sqlalchemy.orm import Session

from app.domain.provenance import VerificationStatus
from app.models import Property, TransportLookup, TransportStop
from app.schemas import AddressCandidate, ExternalRequest, TransportInfo, TransportStep, TransportStopOut, TransportStepResult
from app.transport.nearby import (
    MAX_WALKING_METRES, MAX_WALKING_TEXT, NOMINATIM_URL, RESROBOT_URL, TRANSPORT_LABELS, VALHALLA_URL, Candidate,
    GeocodeQuery, Place, Stop, TransportLookupError, TransportType, automatic_choice, geocode_query,
    nearby_stops_params, nearest_per_type, order_candidates, parse_candidates, parse_nearby_stops, parse_walking,
    same_municipality, walking_request,
)

DONE, FAILED, CHOOSE, SKIPPED = "done", "failed", "choose", "skipped"
SOURCE = ("Adressen: OpenStreetMap (Nominatim). Hållplatser: Trafiklab ResRobot. "
          "Gångväg och tid: OpenStreetMap (Valhalla).")
STREET_LEVEL = ("Husnumret hittades inte i OpenStreetMap, bara gatan. Avstånden till hållplatser skulle då bli "
                "osäkra, så de visas inte. Kontrollera adressen.")
NOT_FETCHED = "Kollektivtrafiken har inte hämtats."
NOT_FOUND = "Adressen hittades inte i OpenStreetMap. Kontrollera adressen och kommunen."

_SERVICES = {"geocode": "OpenStreetMap", "stops": "Trafiklab", "walking": "OpenStreetMaps ruttjänst"}
_NEXT = {"start": "geocode", "geocode": "stops", "stops": "walking", "walking": DONE}


class TransportStepError(Exception):
    """A step was sent out of order. The message is shown in the UI, in Swedish."""


class TransportChoiceError(Exception):
    """The chosen address isn't one of those offered. The message is shown in the UI, in Swedish."""


def current_query(listing: Property) -> GeocodeQuery:
    return geocode_query(listing.address, listing.municipality)


def run_step(session: Session, listing: Property, step: TransportStep) -> TransportStepResult:
    if step.stage == "start":
        return _start(session, listing)
    if step.stage == "skip":
        return _skip(session, listing)
    if step.stage == "choose":
        return _choose(session, listing, step.choice)

    lookup = listing.transport
    if lookup is None or lookup.stage != step.stage:
        raise TransportStepError("Hämtningen av kollektivtrafik har startats om. Försök igen.")
    try:
        request = _receive(lookup, step)
    except TransportLookupError as error:
        lookup.stage, lookup.message = FAILED, str(error)
        lookup.stops.clear()
        request = None
    lookup.retrieved_at = datetime.now(timezone.utc)
    session.commit()
    return TransportStepResult(request=request, transport=transport_info(listing))


def _start(session: Session, listing: Property) -> TransportStepResult:
    try:
        query = current_query(listing)
    except TransportLookupError:
        return TransportStepResult(request=None, transport=transport_info(listing))
    listing.transport = None  # A new lookup replaces the old one.
    session.flush()
    listing.transport = TransportLookup(query=query.text, stage="geocode")
    session.commit()
    request = ExternalRequest(stage="geocode", service="nominatim", method="GET",
                              url=f"{NOMINATIM_URL}?{urlencode(query.params())}", needs_key=False)
    return TransportStepResult(request=request, transport=transport_info(listing))


def _receive(lookup: TransportLookup, step: TransportStep) -> ExternalRequest | None:
    service = _SERVICES[step.stage]
    if step.error == "timeout":
        raise TransportLookupError(f"{service} svarade inte i tid. Försök igen senare.")
    if step.error == "network":
        raise TransportLookupError(f"Kunde inte nå {service}. Kontrollera internetanslutningen och försök igen.")

    body = step.body
    if step.status != 200 and not isinstance(body, (dict, list)):
        raise TransportLookupError(f"{service} kunde inte svara (HTTP {step.status}). Försök igen senare.")

    if step.stage == "geocode":
        _require_ok(step, service)  # Nominatim has no error format of its own to read first.
        query = current_query(lookup.property)
        candidates, truncated = parse_candidates(body, query.limit)
        if not candidates and body and not any(_has_house_number(hit) for hit in body):
            lookup.house_level = False  # Only the street: on a long street the distances could be far off.
            raise TransportLookupError(STREET_LEVEL)
        if not candidates:
            raise TransportLookupError(NOT_FOUND)
        chosen = automatic_choice(candidates, query)
        if chosen:
            return _continue_from(lookup, chosen)
        lookup.stage = CHOOSE
        lookup.candidates = [vars(c) for c in order_candidates(candidates, query)]
        lookup.truncated = truncated
        return None

    if step.stage == "stops":
        stops = parse_nearby_stops(body)
        _require_ok(step, service)
        nearest = nearest_per_type(stops)
        lookup.stops = [TransportStop(transport_type=kind.value, name=stop.name, ext_id=stop.ext_id, lat=stop.lat,
                                      lon=stop.lon, straight_metres=stop.straight_metres)
                        for kind, stop in nearest.items()]
        targets = _targets(lookup)
        if not targets:
            lookup.stage = DONE
            return None
        lookup.stage = "walking"
        place = Place(lat=lookup.place_lat, lon=lookup.place_lon, label="", house_level=bool(lookup.house_level))
        request = walking_request(place, targets)
        return ExternalRequest(stage="walking", service="valhalla", method="GET",
                               url=f"{VALHALLA_URL}?json={quote(json.dumps(request, separators=(',', ':')))}",
                               needs_key=False)  # Valhalla doesn't read "+" as a space.

    # Walking.
    targets = _targets(lookup)
    walks = parse_walking(body, len(targets))
    _require_ok(step, service)
    by_position = {(t.lat, t.lon): walk for t, walk in zip(targets, walks)}
    for stop in lookup.stops:
        walk = by_position[(stop.lat, stop.lon)]
        stop.walking_metres = walk.metres if walk else None
        stop.walking_seconds = walk.seconds if walk else None
    lookup.stage = DONE
    return None


def _continue_from(lookup: TransportLookup, chosen: Candidate) -> ExternalRequest:
    """Use this address and ask for the stops near it."""
    place = chosen.place
    lookup.place_label, lookup.place_lat, lookup.place_lon, lookup.house_level = place.label, place.lat, place.lon, True
    lookup.candidates, lookup.truncated = None, None
    lookup.stage = "stops"
    return ExternalRequest(stage="stops", service="resrobot", method="GET",
                           url=f"{RESROBOT_URL}?{urlencode(nearby_stops_params(place))}", needs_key=True)


def _choose(session: Session, listing: Property, choice: int | None) -> TransportStepResult:
    """The user picked one of the offered addresses. Its municipality becomes the apartment's, as the user's value."""
    lookup = listing.transport
    if lookup is None or lookup.stage != CHOOSE:
        raise TransportStepError("Det finns inga adresser att välja bland. Ladda om sidan och försök igen.")
    try:
        unchanged = lookup.query == current_query(listing).text
    except TransportLookupError:  # The address was removed.
        unchanged = False
    if not unchanged:
        raise TransportStepError("Adressen har ändrats. Ladda om sidan och välj igen.")
    if choice is None or not 0 <= choice < len(lookup.candidates or []):
        raise TransportChoiceError("Välj en av de föreslagna adresserna.")
    chosen = Candidate(**lookup.candidates[choice])
    listing.municipality = chosen.municipality
    sources = dict(listing.field_sources or {})
    sources["municipality"] = {  # Same shape as other manual values: the user's choice wins over the listing.
        "status": VerificationStatus.USER_ENTERED.value, "method": "address_choice",
        "excerpt": f"Vald bland förslag från OpenStreetMap: ”{chosen.display_name}”", "note": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    listing.field_sources = sources
    lookup.query = current_query(listing).text  # The lookup now matches the apartment's address.
    request = _continue_from(lookup, chosen)
    lookup.retrieved_at = datetime.now(timezone.utc)
    session.commit()
    return TransportStepResult(request=request, transport=transport_info(listing))


def _skip(session: Session, listing: Property) -> TransportStepResult:
    """Continue without public transport for this address. Remembered until the address changes."""
    try:
        query = current_query(listing)
    except TransportLookupError as error:
        raise TransportStepError(str(error)) from error
    listing.transport = None
    session.flush()
    listing.transport = TransportLookup(query=query.text, stage=SKIPPED)
    session.commit()
    return TransportStepResult(request=None, transport=transport_info(listing))


def _has_house_number(hit) -> bool:
    return isinstance(hit, dict) and isinstance(hit.get("address"), dict) and bool(hit["address"].get("house_number"))


def _require_ok(step: TransportStep, service: str) -> None:
    if step.status != 200:
        raise TransportLookupError(f"{service} kunde inte svara (HTTP {step.status}). Försök igen senare.")


def _targets(lookup: TransportLookup) -> list[Stop]:
    """Each stop once, even when it is the nearest of several types."""
    unique = {}
    for stop in lookup.stops:
        unique.setdefault((stop.lat, stop.lon), Stop(name=stop.name, ext_id=stop.ext_id, lat=stop.lat, lon=stop.lon,
                                                     straight_metres=stop.straight_metres, types=frozenset()))
    return list(unique.values())


# --- Reading ----------------------------------------------------------------------------------


def transport_info(listing: Property) -> TransportInfo:
    lookup = listing.transport
    try:
        query, unavailable = current_query(listing).text, None
    except TransportLookupError as error:
        query, unavailable = None, str(error)

    if unavailable:
        return TransportInfo(status="unavailable", message=unavailable, query=None,
                             looked_up_query=lookup.query if lookup else None, place_label=None, house_level=None,
                             retrieved_at=None, source=None, stops=[])
    if lookup is None:
        return TransportInfo(status="not_fetched", message=None, query=query, looked_up_query=None, place_label=None,
                             house_level=None, retrieved_at=None, source=None, stops=[])

    if lookup.query != query:
        status = "stale"
    elif lookup.stage in (DONE, FAILED, CHOOSE, SKIPPED):
        status = lookup.stage
    else:
        status = "pending"
    message = lookup.message if lookup.stage == FAILED else None
    offered = [Candidate(**c) for c in lookup.candidates or []] if lookup.stage == CHOOSE else []
    if offered and listing.municipality and not any(same_municipality(listing.municipality, c) for c in offered):
        message = f"Inga träffar i {listing.municipality}. Välj bland träffarna nedan eller kontrollera kommunen."
    return TransportInfo(
        status=status, message=message, query=query, looked_up_query=lookup.query,
        place_label=lookup.place_label, house_level=lookup.house_level, retrieved_at=lookup.retrieved_at,
        source=SOURCE, stops=_stops(lookup) if lookup.stage == DONE else [],
        candidates=[AddressCandidate(label=c.label, municipality=c.municipality) for c in offered],
        truncated=bool(lookup.truncated) if offered else False,
    )


def _stops(lookup: TransportLookup) -> list[TransportStopOut]:
    stored = {stop.transport_type: stop for stop in lookup.stops}
    result = []
    for kind in TransportType:
        stop = stored.get(kind.value)
        label = TRANSPORT_LABELS[kind]
        if stop is None:
            result.append(_missing(kind, f"Saknas inom {MAX_WALKING_TEXT} gångavstånd."))
        elif stop.walking_metres is None:
            result.append(_missing(kind, f"Närmaste hållplats fågelvägen, {stop.name} ({_metres(stop.straight_metres)}), "
                                         f"men ingen gångväg dit kunde beräknas.", stop.straight_metres))
        elif stop.walking_metres > MAX_WALKING_METRES:
            result.append(_missing(kind, f"Närmaste hållplats fågelvägen, {stop.name}, ligger "
                                         f"{_metres(stop.walking_metres)} bort till fots, mer än {MAX_WALKING_TEXT}.",
                                   stop.straight_metres))
        else:
            result.append(TransportStopOut(
                type=kind.value, label=label, status=VerificationStatus.EXTRACTED.value, name=stop.name,
                walking_metres=stop.walking_metres, walking_seconds=stop.walking_seconds,
                straight_metres=stop.straight_metres, note=None,
            ))
    return result


def _missing(kind: TransportType, note: str, straight_metres: int | None = None) -> TransportStopOut:
    return TransportStopOut(type=kind.value, label=TRANSPORT_LABELS[kind], status=VerificationStatus.MISSING.value,
                            name=None, walking_metres=None, walking_seconds=None, straight_metres=straight_metres,
                            note=note)


def _metres(value: int) -> str:
    return f"{value:,} m".replace(",", " ")


def format_walk(metres: int, seconds: int) -> str:
    """"163 m (ca 2 min)": the routing service's distance and time, rounded to whole minutes (at least 1)."""
    return f"{_metres(metres)} (ca {max(1, round(seconds / 60))} min)"
