"""Public transport through the API: the step-by-step lookup, storage, staleness and comparison.

The frontend makes each HTTP call the backend asks for and posts back the raw response.
Here the responses come from tests/fixtures/transport.
"""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from tests.listing_samples import HEMNET_STYLE

FIXTURES = Path(__file__).parent / "fixtures" / "transport"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def add_listing(client, text=HEMNET_STYLE):
    return client.post("/api/properties/from-text", json={"text": text}).json()["id"]


def step(client, property_id, stage, body=None, status=200, error=None):
    payload = {"stage": stage}
    if stage != "start":
        payload |= {"status": status, "body": body} if error is None else {"error": error}
    response = client.post(f"/api/properties/{property_id}/transport/step", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def run_lookup(client, property_id, geocode="nominatim_house.json", walking="valhalla_matrix.json"):
    step(client, property_id, "start")
    step(client, property_id, "geocode", fixture(geocode))
    step(client, property_id, "stops", fixture("resrobot_nearbystops.json"))
    return step(client, property_id, "walking", fixture(walking))


def stop_of(transport, kind):
    return next(s for s in transport["stops"] if s["type"] == kind)


# --- Before any lookup --------------------------------------------------------------------------


def test_new_listing_has_no_transport_yet(client):
    overview = client.get(f"/api/properties/{add_listing(client)}").json()
    assert overview["transport"]["status"] == "not_fetched"
    assert overview["transport"]["query"] == "Ringvägen 12, Stockholms kommun"


def test_listing_without_an_address_cannot_be_looked_up(client):
    property_id = add_listing(client, HEMNET_STYLE.replace("Ringvägen 12, 3 tr\n", ""))
    transport = client.get(f"/api/properties/{property_id}").json()["transport"]
    assert transport["status"] == "unavailable"
    assert "adress" in transport["message"]
    response = client.post(f"/api/properties/{property_id}/transport/step", json={"stage": "start"})
    assert response.json()["request"] is None
    assert response.json()["transport"]["status"] == "unavailable"


# --- The steps ----------------------------------------------------------------------------------


def test_steps_ask_for_geocoding_then_stops_then_walking(client):
    property_id = add_listing(client)

    started = step(client, property_id, "start")
    assert started["transport"]["status"] == "pending"
    geocode = started["request"]
    assert geocode["stage"] == "geocode" and geocode["method"] == "GET" and geocode["needs_key"] is False
    url = urlparse(geocode["url"])
    assert url.netloc == "nominatim.openstreetmap.org"
    assert parse_qs(url.query)["street"] == ["Ringvägen 12"]
    assert parse_qs(url.query)["city"] == ["Stockholms kommun"]

    stops = step(client, property_id, "geocode", fixture("nominatim_house.json"))["request"]
    assert stops["stage"] == "stops" and stops["needs_key"] is True
    url = urlparse(stops["url"])
    assert url.netloc == "api.resrobot.se"
    assert "accessId" not in parse_qs(url.query)  # The frontend adds the user's key.
    assert parse_qs(url.query)["r"] == ["2000"]

    walking = step(client, property_id, "stops", fixture("resrobot_nearbystops.json"))["request"]
    assert walking["stage"] == "walking" and walking["method"] == "GET"
    url = urlparse(walking["url"])
    assert url.netloc == "valhalla1.openstreetmap.de"
    # Valhalla doesn't decode "+" as a space in its json parameter ("Failed to parse json request").
    assert "+" not in url.query
    request = json.loads(parse_qs(url.query)["json"][0])
    # One stop per type, the nearest by straight line; Zinkensdamm serves both metro and bus.
    assert len(request["targets"]) == 2
    assert request["costing"] == "pedestrian"

    done = step(client, property_id, "walking", fixture("valhalla_matrix.json"))
    assert done["request"] is None
    assert done["transport"]["status"] == "done"


def test_nearest_stops_with_walking_distance_time_and_source(client):
    transport = run_lookup(client, add_listing(client))["transport"]
    assert [s["type"] for s in transport["stops"]] == ["subway", "commuter_train", "bus"]

    subway = stop_of(transport, "subway")
    assert subway["label"] == "Tunnelbana"
    assert subway["name"] == "Zinkensdamm T-bana (Stockholm kn)"
    assert subway["walking_metres"] == 163
    assert subway["walking_seconds"] == 125
    assert subway["straight_metres"] == 99
    assert subway["status"] == "extracted"
    assert subway["walk_text"] == "163 m (ca 2 min)"

    train = stop_of(transport, "commuter_train")
    assert train["label"] == "Pendeltåg/lokaltåg"
    assert train["name"] == "Stockholm Södra station (Stockholm kn)"
    assert (train["walking_metres"], train["walking_seconds"]) == (864, 630)

    assert stop_of(transport, "bus")["name"] == "Zinkensdamm T-bana (Stockholm kn)"

    assert transport["place_label"].startswith("12, Ringvägen")
    assert transport["house_level"] is True
    assert transport["retrieved_at"]
    assert "Trafiklab" in transport["source"] and "OpenStreetMap" in transport["source"]


def test_result_is_kept_on_the_property_page(client):
    property_id = add_listing(client)
    run_lookup(client, property_id)
    transport = client.get(f"/api/properties/{property_id}").json()["transport"]
    assert transport["status"] == "done"
    assert stop_of(transport, "subway")["walking_metres"] == 163


def test_street_level_match_stops_the_lookup(client):
    # Only the street was found: on a long street the distances could be far off, so none are shown,
    # and the stops and walking routes are never requested.
    property_id = add_listing(client)
    step(client, property_id, "start")
    result = step(client, property_id, "geocode", fixture("nominatim_street_only.json"))
    assert result["request"] is None
    transport = result["transport"]
    assert transport["status"] == "failed"
    assert transport["house_level"] is False
    assert "Husnumret hittades inte" in transport["message"]
    assert transport["stops"] == []


# --- Missing and failed ---------------------------------------------------------------------------


def test_type_without_a_stop_within_two_km(client):
    property_id = add_listing(client)
    step(client, property_id, "start")
    step(client, property_id, "geocode", fixture("nominatim_house.json"))
    stops = fixture("resrobot_nearbystops.json")
    stops["stopLocationOrCoordLocation"] = stops["stopLocationOrCoordLocation"][:2]  # No train station.
    step(client, property_id, "stops", stops)
    matrix = fixture("valhalla_matrix.json")
    matrix["sources_to_targets"][0] = matrix["sources_to_targets"][0][:1]
    transport = step(client, property_id, "walking", matrix)["transport"]

    train = stop_of(transport, "commuter_train")
    assert train["status"] == "missing"
    assert train["name"] is None and train["walking_metres"] is None and train["walk_text"] is None
    assert train["note"] == "Saknas inom 2 km gångavstånd."


def test_stop_more_than_two_km_away_on_foot_is_not_shown(client):
    matrix = fixture("valhalla_matrix.json")
    matrix["sources_to_targets"][0][1]["distance"] = 2.150
    matrix["sources_to_targets"][0][1]["time"] = 1600
    property_id = add_listing(client)
    step(client, property_id, "start")
    step(client, property_id, "geocode", fixture("nominatim_house.json"))
    step(client, property_id, "stops", fixture("resrobot_nearbystops.json"))
    train = stop_of(step(client, property_id, "walking", matrix)["transport"], "commuter_train")
    assert train["status"] == "missing"
    assert train["walking_metres"] is None and train["walk_text"] is None
    assert "Stockholm Södra station" in train["note"] and "2 150 m" in train["note"]


def test_stop_without_a_walking_route(client):
    matrix = fixture("valhalla_matrix.json")
    matrix["sources_to_targets"][0][1]["distance"] = None
    matrix["sources_to_targets"][0][1]["time"] = None
    property_id = add_listing(client)
    step(client, property_id, "start")
    step(client, property_id, "geocode", fixture("nominatim_house.json"))
    step(client, property_id, "stops", fixture("resrobot_nearbystops.json"))
    train = stop_of(step(client, property_id, "walking", matrix)["transport"], "commuter_train")
    assert train["status"] == "missing"
    assert "gångväg" in train["note"]
    assert train["walk_text"] is None


def test_walk_over_a_thousand_metres_uses_a_non_breaking_space(client):
    matrix = fixture("valhalla_matrix.json")
    matrix["sources_to_targets"][0][1]["distance"] = 1.250
    matrix["sources_to_targets"][0][1]["time"] = 900
    first, second = add_listing(client), add_listing(client)
    step(client, first, "start")
    step(client, first, "geocode", fixture("nominatim_house.json"))
    step(client, first, "stops", fixture("resrobot_nearbystops.json"))
    train = stop_of(step(client, first, "walking", matrix)["transport"], "commuter_train")
    assert train["walk_text"] == "1 250 m (ca 15 min)"

    comparison = client.get(f"/api/comparisons/properties?ids={first},{second}").json()
    cell = next(r for r in comparison["rows"] if r["key"] == "transport:commuter_train")["cells"][0]
    assert cell["value"] == "Stockholm Södra station (Stockholm kn), 1 250 m (ca 15 min) till fots"


def test_address_not_found_fails_with_a_reason(client):
    property_id = add_listing(client)
    step(client, property_id, "start")
    result = step(client, property_id, "geocode", fixture("nominatim_not_found.json"))
    assert result["request"] is None
    assert result["transport"]["status"] == "failed"
    assert "hittades inte" in result["transport"]["message"]
    assert result["transport"]["stops"] == []


def test_rejected_key_fails_with_a_reason(client):
    property_id = add_listing(client)
    step(client, property_id, "start")
    step(client, property_id, "geocode", fixture("nominatim_house.json"))
    result = step(client, property_id, "stops", {"errorCode": "API_AUTH", "errorText": "Invalid key"}, status=401)
    assert result["transport"]["status"] == "failed"
    assert "nyckel" in result["transport"]["message"]


def test_server_error_fails_with_a_reason(client):
    property_id = add_listing(client)
    step(client, property_id, "start")
    result = step(client, property_id, "geocode", "<html>Bad gateway</html>", status=502)
    assert result["transport"]["status"] == "failed"
    assert "OpenStreetMap" in result["transport"]["message"] and "502" in result["transport"]["message"]


def test_network_error_and_timeout_fail_with_a_reason(client):
    property_id = add_listing(client)
    step(client, property_id, "start")
    result = step(client, property_id, "geocode", error="timeout")
    assert result["transport"]["status"] == "failed"
    assert "svarade inte i tid" in result["transport"]["message"]


def test_steps_out_of_order_are_refused(client):
    property_id = add_listing(client)
    response = client.post(f"/api/properties/{property_id}/transport/step",
                           json={"stage": "walking", "status": 200, "body": fixture("valhalla_matrix.json")})
    assert response.status_code == 409


# --- Staleness, corrections, storage --------------------------------------------------------------


def test_corrected_address_makes_the_result_stale_and_is_used_next(client):
    property_id = add_listing(client)
    run_lookup(client, property_id)
    client.patch(f"/api/properties/{property_id}", json={"address": "Hornsgatan 5"})

    transport = client.get(f"/api/properties/{property_id}").json()["transport"]
    assert transport["status"] == "stale"
    assert transport["query"] == "Hornsgatan 5, Stockholms kommun"
    assert transport["stops"]  # The old result stays visible, marked as stale.

    url = urlparse(step(client, property_id, "start")["request"]["url"])
    assert parse_qs(url.query)["street"] == ["Hornsgatan 5"]


def test_new_lookup_replaces_the_old_one(client):
    property_id = add_listing(client)
    run_lookup(client, property_id)
    transport = run_lookup(client, property_id)["transport"]
    assert len(transport["stops"]) == 3


def test_export_and_import_keep_the_result(client):
    property_id = add_listing(client)
    run_lookup(client, property_id)
    exported = client.get("/api/backup").content
    client.delete(f"/api/properties/{property_id}")
    response = client.post("/api/backup", content=exported, headers={"content-type": "application/zip"})
    assert response.status_code == 204, response.text
    transport = client.get(f"/api/properties/{property_id}").json()["transport"]
    assert transport["status"] == "done"
    assert stop_of(transport, "subway")["walking_metres"] == 163


def test_deleting_the_apartment_deletes_its_lookup(client):
    property_id = add_listing(client)
    run_lookup(client, property_id)
    client.delete(f"/api/properties/{property_id}")
    new_id = add_listing(client)
    assert client.get(f"/api/properties/{new_id}").json()["transport"]["status"] == "not_fetched"


# --- Comparison -----------------------------------------------------------------------------------


def test_comparison_has_a_row_per_transport_type(client):
    first, second = add_listing(client), add_listing(client)
    run_lookup(client, first)
    comparison = client.get(f"/api/comparisons/properties?ids={first},{second}").json()
    rows = {row["key"]: row for row in comparison["rows"]}

    subway = rows["transport:subway"]
    assert subway["group"] == "Läge"
    assert subway["label"] == "Närmaste tunnelbana"
    found, missing = subway["cells"]
    assert found["value"] == "Zinkensdamm T-bana (Stockholm kn), 163 m (ca 2 min) till fots"
    assert found["status"] == "extracted"
    assert "Trafiklab" in found["excerpt"]
    assert missing["value"] is None and missing["status"] == "missing"
    assert "inte hämtats" in missing["note"]

    assert rows["transport:commuter_train"]["label"] == "Närmaste pendeltåg/lokaltåg"
    assert rows["transport:bus"]["label"] == "Närmaste buss"


def test_rate_limited_geocoding_reports_the_http_status(client):
    property_id = add_listing(client)
    step(client, property_id, "start")
    result = step(client, property_id, "geocode", {"error": "Too many requests"}, status=429)
    assert result["transport"]["status"] == "failed"
    assert "429" in result["transport"]["message"]


def test_comparison_of_an_unfinished_lookup_does_not_claim_it_is_running(client):
    first, second = add_listing(client), add_listing(client)
    step(client, first, "start")  # Abandoned: the tab was closed before the next step.
    comparison = client.get(f"/api/comparisons/properties?ids={first},{second}").json()
    cell = next(r for r in comparison["rows"] if r["key"] == "transport:subway")["cells"][0]
    assert cell["status"] == "missing"
    assert "avbröts" in cell["note"]
