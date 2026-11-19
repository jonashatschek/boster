"""Public transport near an apartment: build queries and read the services' responses.

The frontend makes the HTTP calls (the Python code stays offline); this module decides
what to ask and reads the raw answers, which are untrusted input:

1. Nominatim (OpenStreetMap) turns the listing's address into coordinates.
2. Trafiklab ResRobot ``location.nearbystops`` lists stops near those coordinates.
3. Valhalla (OpenStreetMap) calculates the walking route to the nearest stop of each type.

Nothing is estimated: a distance or time is shown only when the routing service returned it.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

MAX_WALKING_METRES = 2000  # Stops farther away than this on foot are not shown.
MAX_WALKING_TEXT = f"{MAX_WALKING_METRES / 1000:g} km".replace(".", ",")  # "2 km", for the UI.

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
RESROBOT_URL = "https://api.resrobot.se/v2.1/location.nearbystops"
VALHALLA_URL = "https://valhalla1.openstreetmap.de/sources_to_targets"

# Rough bounding box of Sweden, to reject a match in another country.
_SWEDEN = (55.0, 69.2, 10.5, 24.3)


class TransportType(StrEnum):
    SUBWAY = "subway"
    COMMUTER_TRAIN = "commuter_train"
    BUS = "bus"


TRANSPORT_LABELS = {
    TransportType.SUBWAY: "Tunnelbana",
    TransportType.COMMUTER_TRAIN: "Pendeltåg/lokaltåg",
    TransportType.BUS: "Buss",
}

# ResRobot product classes (bitmask), from Trafiklab's "ResRobot data types" page. Only these
# count: 16 is "local trains" (pendeltåg, but also e.g. Roslagsbanan and Öresundståg), so it is
# labelled "Pendeltåg/lokaltåg". Regional trains (4), express buses (8) and trams (64) are left out.
_CLASSES = {32: TransportType.SUBWAY, 16: TransportType.COMMUTER_TRAIN, 128: TransportType.BUS}
_MAX_PRODUCTS = 1023  # All documented classes (1–512) together.


class TransportLookupError(Exception):
    """Why the lookup could not be completed. The message is shown in the UI, in Swedish."""


# --- Geocoding --------------------------------------------------------------------------------

# Parts of a listing address that are not part of the street address: floor ("3 tr", "2 vån"),
# flat number ("lgh 1102") and floor abbreviations ("nb", "bv", "ög").
_NOT_STREET = re.compile(r"\s+(lgh\.?\s*\d+|\d+\s*(tr|trappor|vån|våning)\.?|nb|bv|ög)\b.*$", re.IGNORECASE)


@dataclass(frozen=True)
class GeocodeQuery:
    street: str
    city: str

    @property
    def text(self) -> str:
        return f"{self.street}, {self.city}"

    def params(self) -> dict[str, str]:
        return {"street": self.street, "city": self.city, "countrycodes": "se", "format": "jsonv2",
                "addressdetails": "1", "limit": "1", "accept-language": "sv"}


def geocode_query(address: str | None, municipality: str | None) -> GeocodeQuery:
    """The structured address search. The municipality is passed as printed in the listing."""
    street = _NOT_STREET.sub("", (address or "").split(",")[0]).strip()
    if not street:
        raise TransportLookupError("Bostaden saknar adress, så kollektivtrafiken kan inte hämtas.")
    if not municipality or not municipality.strip():
        raise TransportLookupError("Bostaden saknar kommun. Ange kommunen, så att adressen inte hittas i fel ort.")
    return GeocodeQuery(street=street, city=municipality.strip())


@dataclass(frozen=True)
class Place:
    lat: float
    lon: float
    label: str  # Nominatim's description of the match.
    house_level: bool  # False when only the street, not the house number, was found.


def parse_geocode(data) -> Place:
    if data == []:
        raise TransportLookupError("Adressen hittades inte i OpenStreetMap. Kontrollera adressen och kommunen.")
    if not isinstance(data, list) or not isinstance(data[0], dict):
        raise TransportLookupError("Oväntat svar från OpenStreetMap (adressökning).")
    match = data[0]
    lat, lon = _number(match.get("lat")), _number(match.get("lon"))
    if lat is None or lon is None:
        raise TransportLookupError("Oväntat svar från OpenStreetMap (adressökning).")
    if not (_SWEDEN[0] <= lat <= _SWEDEN[1] and _SWEDEN[2] <= lon <= _SWEDEN[3]):
        raise TransportLookupError("Adressen hittades inte i Sverige.")
    address = match.get("address") if isinstance(match.get("address"), dict) else {}
    label = match.get("display_name")
    return Place(lat=lat, lon=lon, label=label if isinstance(label, str) else "",
                 house_level=bool(address.get("house_number")))


# --- Nearby stops -----------------------------------------------------------------------------


def nearby_stops_params(place: Place) -> dict[str, str]:
    """ResRobot query without the key; the frontend adds its own ``accessId``."""
    return {"originCoordLat": f"{place.lat:.6f}", "originCoordLong": f"{place.lon:.6f}",
            "r": str(MAX_WALKING_METRES), "maxNo": "1000", "format": "json", "lang": "sv"}


@dataclass(frozen=True)
class Stop:
    name: str
    ext_id: str
    lat: float
    lon: float
    straight_metres: int  # ResRobot's distance from the address (undocumented; likely straight-line).
    types: frozenset[TransportType]


def parse_nearby_stops(data) -> list[Stop]:
    if not isinstance(data, dict):
        raise TransportLookupError("Oväntat svar från Trafiklab (hållplatser).")
    if "errorCode" in data:
        raise TransportLookupError(_resrobot_error(data))
    entries = data.get("stopLocationOrCoordLocation") or []
    if not isinstance(entries, list):
        raise TransportLookupError("Oväntat svar från Trafiklab (hållplatser).")
    stops = []
    for entry in entries:
        item = entry.get("StopLocation") if isinstance(entry, dict) else None
        if isinstance(item, dict) and (stop := _stop(item)):
            stops.append(stop)
    return stops


def _stop(item: dict) -> Stop | None:
    name, ext_id = item.get("name"), item.get("extId")
    lat, lon, dist = _number(item.get("lat")), _number(item.get("lon")), _number(item.get("dist"))
    if not isinstance(name, str) or not name.strip() or lat is None or lon is None or dist is None or dist < 0:
        return None
    values = [product.get("cls") for product in item.get("productAtStop") or [] if isinstance(product, dict)]
    mask = 0
    for value in [*values, item.get("products")]:
        number = _number(value)
        if number is not None and 0 <= number <= _MAX_PRODUCTS:  # A negative value would set every bit.
            mask |= int(number)
    types = frozenset(kind for bit, kind in _CLASSES.items() if mask & bit)
    return Stop(name=name.strip(), ext_id=str(ext_id or ""), lat=lat, lon=lon, straight_metres=round(dist),
                types=types)


def _resrobot_error(data: dict) -> str:
    if str(data.get("errorCode", "")).startswith("API_AUTH"):
        return "Trafiklab godkände inte Bosters nyckel, så hållplatser kan inte hämtas just nu."
    if str(data.get("errorCode", "")).startswith("API_QUOTA"):
        return "Bosters Trafiklab-nyckel har använts för mycket för tillfället. Försök igen senare."
    return "Trafiklab kunde inte svara på frågan om hållplatser."


def nearest_per_type(stops: list[Stop]) -> dict[TransportType, Stop]:
    """The nearest stop of each type by ResRobot's distance, within the walking limit.

    A walk is never shorter than the straight line, so a stop farther than the limit
    can't be within walking distance.
    """
    nearest: dict[TransportType, Stop] = {}
    for stop in sorted(stops, key=lambda s: s.straight_metres):
        if stop.straight_metres > MAX_WALKING_METRES:
            continue
        for kind in stop.types:
            nearest.setdefault(kind, stop)
    return {kind: nearest[kind] for kind in TransportType if kind in nearest}


# --- Walking routes ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Walk:
    metres: int
    seconds: int


def walking_request(place: Place, stops: list[Stop]) -> dict:
    """Valhalla matrix request: from the address to each stop, on foot."""
    return {"sources": [{"lat": place.lat, "lon": place.lon}],
            "targets": [{"lat": stop.lat, "lon": stop.lon} for stop in stops],
            "costing": "pedestrian", "units": "kilometers"}


def parse_walking(data, count: int) -> list[Walk | None]:
    """One walk per target, in order; None when the routing service found no route."""
    if isinstance(data, dict) and "error_code" in data:
        raise TransportLookupError("Gångvägen kunde inte beräknas av OpenStreetMaps ruttjänst.")
    rows = data.get("sources_to_targets") if isinstance(data, dict) else None
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], list) or len(rows[0]) != count:
        raise TransportLookupError("Oväntat svar från OpenStreetMaps ruttjänst (gångvägar).")
    walks: list[Walk | None] = []
    for cell in rows[0]:
        distance = _number(cell.get("distance")) if isinstance(cell, dict) else None
        time = _number(cell.get("time")) if isinstance(cell, dict) else None
        walks.append(Walk(metres=round(distance * 1000), seconds=round(time))
                     if distance is not None and time is not None and distance >= 0 and time >= 0 else None)
    return walks


def _number(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value == value and abs(value) != float("inf") else None
    if isinstance(value, str):
        try:
            return _number(float(value))
        except ValueError:
            return None
    return None
