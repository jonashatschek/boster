"""Public transport near an apartment: parsing the services' responses and choosing stops.

The HTTP calls are made by the frontend; these functions only see the raw responses,
which are untrusted input. Fixtures are described in tests/fixtures/transport/README.md.
"""

import json
from pathlib import Path

import pytest

from app.services.transport import format_walk
from app.transport.nearby import (
    MAX_WALKING_METRES, GeocodeQuery, Place, Stop, TransportLookupError, TransportType, geocode_query,
    nearest_per_type, parse_nearby_stops, parse_walking, walking_request,
)

FIXTURES = Path(__file__).parent / "fixtures" / "transport"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# --- Geocoding query --------------------------------------------------------------------------


@pytest.mark.parametrize("address, street", [
    ("Ringvägen 12, 3 tr", "Ringvägen 12"),
    ("Ringvägen 12", "Ringvägen 12"),
    ("Storgatan 3A", "Storgatan 3A"),
    ("Rusthållarvägen 151 lgh 1102", "Rusthållarvägen 151"),
    ("Sveavägen 40, 2 tr, lgh 1201", "Sveavägen 40"),
    ("Götgatan 8 nb", "Götgatan 8"),
    ("Ringvägen 12 3 tr", "Ringvägen 12"),
    ("Storgatan 3 A", "Storgatan 3 A"),
])
def test_query_uses_the_street_address_without_floor_or_flat(address, street):
    assert geocode_query(address, "Stockholms kommun") == GeocodeQuery(street=street, city="Stockholms kommun")


def test_municipality_is_passed_as_printed():
    assert geocode_query("Ringvägen 12", "Stockholm").city == "Stockholm"


def test_query_text_shows_what_is_looked_up():
    assert geocode_query("Ringvägen 12, 3 tr", "Stockholms kommun").text == "Ringvägen 12, Stockholms kommun"


def test_query_params_restrict_the_search_to_sweden():
    params = geocode_query("Ringvägen 12", "Stockholms kommun").params()
    assert params["street"] == "Ringvägen 12"
    assert params["city"] == "Stockholms kommun"
    assert params["countrycodes"] == "se"
    assert params["limit"] == "5"
    assert params["accept-language"] == "sv"  # Otherwise the match is described in the browser's language.


def test_no_query_without_an_address():
    with pytest.raises(TransportLookupError, match="adress"):
        geocode_query(None, "Stockholms kommun")


# --- Nearby stops -----------------------------------------------------------------------------


def test_stops_and_their_transport_types():
    stops = {stop.name: stop for stop in parse_nearby_stops(fixture("resrobot_nearbystops.json"))}
    zinkensdamm = stops["Zinkensdamm T-bana (Stockholm kn)"]
    assert zinkensdamm.types == {TransportType.SUBWAY, TransportType.BUS}
    assert zinkensdamm.straight_metres == 99
    assert zinkensdamm.ext_id == "740021710"
    assert stops["Stockholm Södra station (Stockholm kn)"].types == {TransportType.COMMUTER_TRAIN, TransportType.BUS}


@pytest.mark.parametrize("classes, types", [
    ([32], {TransportType.SUBWAY}),
    ([16], {TransportType.COMMUTER_TRAIN}),
    ([128], {TransportType.BUS}),
    ([4], set()),  # Regional train only: not a pendeltåg/lokaltåg stop.
    ([2], set()),  # High-speed train.
    ([8], set()),  # Express bus (flygbuss).
    ([64], set()),  # Tram.
])
def test_only_metro_local_train_and_bus_classes_count(classes, types):
    data = {"stopLocationOrCoordLocation": [{"StopLocation": {
        "name": "A", "extId": "1", "lat": 59.3, "lon": 18.0, "dist": 100,
        "productAtStop": [{"cls": c} for c in classes]}}]}
    stops = parse_nearby_stops(data)
    assert {t for stop in stops for t in stop.types} == types


def test_combined_product_bitmask_is_read():
    data = {"stopLocationOrCoordLocation": [{"StopLocation": {
        "name": "A", "extId": "1", "lat": 59.3, "lon": 18.0, "dist": 100, "products": 32 + 128}}]}
    assert parse_nearby_stops(data)[0].types == {TransportType.SUBWAY, TransportType.BUS}


def test_malformed_stops_are_skipped():
    data = {"stopLocationOrCoordLocation": [
        {"StopLocation": {"name": "No position", "extId": "1", "dist": 10, "productAtStop": [{"cls": "32"}]}},
        {"StopLocation": {"name": "Bad distance", "extId": "2", "lat": 59.3, "lon": 18.0, "dist": "far",
                          "productAtStop": [{"cls": "32"}]}},
        {"CoordLocation": {"name": "An address, not a stop"}},
        "garbage",
        {"StopLocation": {"name": "Good", "extId": "3", "lat": 59.3, "lon": 18.0, "dist": 50,
                          "productAtStop": [{"cls": "32"}]}},
    ]}
    assert [stop.name for stop in parse_nearby_stops(data)] == ["Good"]


def test_no_stops_nearby_is_an_empty_list():
    assert parse_nearby_stops({"serverVersion": "2.45"}) == []


def test_resrobot_error_response():
    with pytest.raises(TransportLookupError, match="Trafiklab"):
        parse_nearby_stops({"errorCode": "API_AUTH", "errorText": "Invalid key"})


# --- Choosing stops ---------------------------------------------------------------------------


def stop(name, metres, *types):
    return Stop(name=name, ext_id=name, lat=59.3, lon=18.0, straight_metres=metres, types=frozenset(types))


def test_nearest_stop_per_type_by_straight_line():
    near_bus = stop("Bus", 50, TransportType.BUS)
    metro_and_bus = stop("Metro", 120, TransportType.SUBWAY, TransportType.BUS)
    far_metro = stop("Far metro", 600, TransportType.SUBWAY)
    nearest = nearest_per_type([far_metro, metro_and_bus, near_bus])
    assert nearest == {TransportType.BUS: near_bus, TransportType.SUBWAY: metro_and_bus}


def test_stops_beyond_the_limit_are_never_candidates():
    assert nearest_per_type([stop("Far", MAX_WALKING_METRES + 1, TransportType.SUBWAY)]) == {}


# --- Walking routes ---------------------------------------------------------------------------


def test_walking_request_goes_from_the_address_to_each_stop():
    place = Place(lat=59.3171248, lon=18.0502604, label="x", house_level=True)
    request = walking_request(place, [stop("A", 100, TransportType.BUS)])
    assert request["sources"] == [{"lat": 59.3171248, "lon": 18.0502604}]
    assert request["targets"] == [{"lat": 59.3, "lon": 18.0}]
    assert request["costing"] == "pedestrian"
    assert request["units"] == "kilometers"


def test_walking_distances_and_times():
    walks = parse_walking(fixture("valhalla_matrix.json"), 2)
    assert [(w.metres, w.seconds) for w in walks] == [(163, 125), (864, 630)]


def test_unreachable_stop_has_no_walk():
    data = fixture("valhalla_matrix.json")
    data["sources_to_targets"][0][1]["distance"] = None
    data["sources_to_targets"][0][1]["time"] = None
    walks = parse_walking(data, 2)
    assert walks[0].metres == 163
    assert walks[1] is None


def test_walking_response_with_the_wrong_number_of_routes():
    with pytest.raises(TransportLookupError):
        parse_walking(fixture("valhalla_matrix.json"), 3)


def test_routing_error_response():
    with pytest.raises(TransportLookupError, match="Gångväg"):
        parse_walking(fixture("valhalla_error.json"), 2)


@pytest.mark.parametrize("field, value", [("productAtStop", [{"cls": -1}]), ("products", -1), ("products", 2**40)])
def test_out_of_range_product_classes_are_ignored(field, value):
    data = {"stopLocationOrCoordLocation": [{"StopLocation": {
        "name": "A", "extId": "1", "lat": 59.3, "lon": 18.0, "dist": 100, field: value}}]}
    assert parse_nearby_stops(data)[0].types == set()


def test_recorded_resrobot_response():
    # A real response (2026-11-19) for Ringvägen 12, Stockholm, r=2000. Checked by hand against the raw JSON.
    stops = parse_nearby_stops(fixture("resrobot_nearbystops_recorded.json"))
    assert len(stops) == 105
    nearest = nearest_per_type(stops)
    assert nearest[TransportType.SUBWAY].name == "Zinkensdamm T-bana (Stockholm kn)"
    assert nearest[TransportType.SUBWAY].straight_metres == 25
    assert nearest[TransportType.BUS] == nearest[TransportType.SUBWAY]
    assert nearest[TransportType.COMMUTER_TRAIN].name == "Stockholm södra station"
    assert nearest[TransportType.COMMUTER_TRAIN].straight_metres == 872


# --- Walking text ------------------------------------------------------------------------------


@pytest.mark.parametrize("metres, seconds, text", [
    (163, 125, "163 m (ca 2 min)"),
    (163, 20, "163 m (ca 1 min)"),  # Whole minutes, but never below 1.
    (500, 89, "500 m (ca 1 min)"),
    (500, 91, "500 m (ca 2 min)"),
    (1250, 900, "1 250 m (ca 15 min)"),  # The thousands separator is a non-breaking space.
])
def test_walking_text(metres, seconds, text):
    assert format_walk(metres, seconds) == text
