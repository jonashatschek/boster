"""Public transport lookup for an apartment, one step at a time.

The backend makes no network calls. For each step it tells the frontend which request to
make; the frontend posts back the raw response, and the backend reads it, stores what it
found and asks for the next request:

    start → geocode (Nominatim) → stops (Trafiklab ResRobot) → walking (Valhalla) → done

A failure at any step ends the lookup with a reason. The stored result keeps the address it
was looked up with, so it is shown as stale once the apartment's address changes.
"""

import json
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

from sqlalchemy.orm import Session

from app.domain.provenance import VerificationStatus
from app.models import Property, TransportLookup, TransportStop
from app.schemas import ExternalRequest, TransportInfo, TransportStep, TransportStopOut, TransportStepResult
from app.transport.nearby import (
    MAX_WALKING_METRES, MAX_WALKING_TEXT, NOMINATIM_URL, RESROBOT_URL, TRANSPORT_LABELS, VALHALLA_URL, GeocodeQuery, Place, Stop,
    TransportLookupError, TransportType, geocode_query, nearby_stops_params, nearest_per_type, parse_geocode,
    parse_nearby_stops, parse_walking, walking_request,
)

DONE, FAILED = "done", "failed"
SOURCE = ("Adressen: OpenStreetMap (Nominatim). Hållplatser: Trafiklab ResRobot. "
          "Gångväg och tid: OpenStreetMap (Valhalla).")
STREET_LEVEL = ("Adressen hittades bara på gatunivå (husnumret finns inte i OpenStreetMap), "
                "så avstånden räknas från gatan, inte från huset.")
NOT_FETCHED = "Kollektivtrafiken har inte hämtats."

_SERVICES = {"geocode": "OpenStreetMap", "stops": "Trafiklab", "walking": "OpenStreetMaps ruttjänst"}
_NEXT = {"start": "geocode", "geocode": "stops", "stops": "walking", "walking": DONE}


class TransportStepError(Exception):
    """A step was sent out of order. The message is shown in the UI, in Swedish."""


def current_query(listing: Property) -> GeocodeQuery:
    return geocode_query(listing.address, listing.municipality)


def run_step(session: Session, listing: Property, step: TransportStep) -> TransportStepResult:
    if step.stage == "start":
        return _start(session, listing)

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
        place = parse_geocode(body)
        lookup.place_label, lookup.place_lat, lookup.place_lon = place.label, place.lat, place.lon
        lookup.house_level = place.house_level
        lookup.stage = "stops"
        return ExternalRequest(stage="stops", service="resrobot", method="GET",
                               url=f"{RESROBOT_URL}?{urlencode(nearby_stops_params(place))}", needs_key=True)

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
    elif lookup.stage in (DONE, FAILED):
        status = lookup.stage
    else:
        status = "pending"
    message = lookup.message if lookup.stage == FAILED else (STREET_LEVEL if lookup.house_level is False else None)
    return TransportInfo(
        status=status, message=message, query=query, looked_up_query=lookup.query,
        place_label=lookup.place_label, house_level=lookup.house_level, retrieved_at=lookup.retrieved_at,
        source=SOURCE, stops=_stops(lookup) if lookup.stage == DONE else [],
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
