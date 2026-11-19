"""Choosing the address through the API (#21): the lookup stops at "choose" and waits for the user."""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from tests.listing_samples import HEMNET_STYLE
from tests.real_listings import AGENT_PILOTGATAN

FIXTURES = Path(__file__).parent / "fixtures" / "transport"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def add_listing(client, text=AGENT_PILOTGATAN):
    return client.post("/api/properties/from-text", json={"text": text}).json()["id"]


def post_step(client, property_id, payload):
    return client.post(f"/api/properties/{property_id}/transport/step", json=payload)


def step(client, property_id, stage, body=None, **extra):
    payload = {"stage": stage, **extra}
    if body is not None:
        payload |= {"status": 200, "body": body}
    response = post_step(client, property_id, payload)
    assert response.status_code == 200, response.text
    return response.json()


def field(client, property_id, key):
    overview = client.get(f"/api/properties/{property_id}").json()
    return next(f for f in overview["fields"] if f["key"] == key)


def transport(client, property_id):
    return client.get(f"/api/properties/{property_id}").json()["transport"]


def query_of(request):
    return parse_qs(urlparse(request["url"]).query)


# --- Without a municipality -------------------------------------------------------------------------


def test_without_a_municipality_the_lookup_can_start(client):
    property_id = add_listing(client)
    assert transport(client, property_id)["status"] == "not_fetched"
    request = step(client, property_id, "start")["request"]
    assert query_of(request)["street"] == ["Pilotgatan 16"]
    assert "city" not in query_of(request)
    assert query_of(request)["limit"] == ["10"]


def test_without_a_municipality_the_user_chooses(client):
    property_id = add_listing(client)
    step(client, property_id, "start")
    result = step(client, property_id, "geocode", fixture("nominatim_choice_pilotgatan.json"))
    assert result["request"] is None
    info = result["transport"]
    assert info["status"] == "choose"
    assert [c["label"] for c in info["candidates"]] == [
        "Pilotgatan 16, Bagarmossen, Stockholms kommun",
        "Pilotgatan 16, Bärby hage, Uppsala kommun",
    ]
    assert info["truncated"] is False
    assert transport(client, property_id)["status"] == "choose"  # Kept until the user decides.


def test_a_single_hit_is_still_confirmed_without_a_municipality(client):
    property_id = add_listing(client)
    step(client, property_id, "start")
    info = step(client, property_id, "geocode", fixture("nominatim_house.json"))["transport"]
    assert info["status"] == "choose"
    assert len(info["candidates"]) == 1


def test_choosing_sets_the_municipality_and_continues_from_that_place(client):
    property_id = add_listing(client)
    step(client, property_id, "start")
    step(client, property_id, "geocode", fixture("nominatim_choice_pilotgatan.json"))

    result = step(client, property_id, "choose", choice=0)
    request = result["request"]
    assert request["stage"] == "stops"
    assert query_of(request)["originCoordLat"] == ["59.265529"]  # Pilotgatan 16 in Stockholm, not Uppsala (59.88).
    assert result["transport"]["status"] == "pending"  # Not stale: the lookup now has the chosen municipality.
    assert result["transport"]["query"] == "Pilotgatan 16, Stockholms kommun"

    municipality = field(client, property_id, "municipality")
    assert municipality["value"] == "Stockholms kommun"
    assert municipality["status"] == "user_entered"
    assert "Vald bland förslag från OpenStreetMap" in municipality["excerpt"]
    assert "16, Pilotgatan" in municipality["excerpt"]

    step(client, property_id, "stops", fixture("resrobot_nearbystops.json"))
    done = step(client, property_id, "walking", fixture("valhalla_matrix.json"))["transport"]
    assert done["status"] == "done"
    assert transport(client, property_id)["status"] == "done"


def test_invalid_choice_is_refused(client):
    property_id = add_listing(client)
    step(client, property_id, "start")
    step(client, property_id, "geocode", fixture("nominatim_choice_pilotgatan.json"))
    response = post_step(client, property_id, {"stage": "choose", "choice": 5})
    assert response.status_code == 422
    assert transport(client, property_id)["status"] == "choose"


def test_choosing_when_nothing_is_offered_is_refused(client):
    property_id = add_listing(client)
    assert post_step(client, property_id, {"stage": "choose", "choice": 0}).status_code == 409


def test_a_full_page_of_hits_is_flagged(client):
    property_id = add_listing(client, AGENT_PILOTGATAN.replace("Pilotgatan 16, 1tr", "Storgatan 3"))
    step(client, property_id, "start")
    info = step(client, property_id, "geocode", fixture("nominatim_choice_storgatan.json"))["transport"]
    assert info["status"] == "choose"
    assert len(info["candidates"]) == 7
    assert info["truncated"] is True


def test_no_hits_fails_with_a_reason(client):
    property_id = add_listing(client)
    step(client, property_id, "start")
    info = step(client, property_id, "geocode", fixture("nominatim_not_found.json"))["transport"]
    assert info["status"] == "failed"
    assert "hittades inte" in info["message"]


def test_re_reading_the_listing_keeps_the_chosen_municipality(client):
    property_id = add_listing(client)
    step(client, property_id, "start")
    step(client, property_id, "geocode", fixture("nominatim_choice_pilotgatan.json"))
    step(client, property_id, "choose", choice=0)
    client.post(f"/api/properties/{property_id}/text",
                json={"text": AGENT_PILOTGATAN.replace("Skarpnäck, Skarpnäck", "Bärby, Uppsala kommun")})
    assert field(client, property_id, "municipality")["value"] == "Stockholms kommun"


# --- With a municipality ----------------------------------------------------------------------------


def test_one_exact_hit_in_the_municipality_continues_without_asking(client):
    property_id = add_listing(client, HEMNET_STYLE)  # Ringvägen 12, Stockholms kommun.
    step(client, property_id, "start")
    result = step(client, property_id, "geocode", fixture("nominatim_house.json"))
    assert result["request"]["stage"] == "stops"


def test_hits_only_in_other_municipalities_ask(client):
    text = HEMNET_STYLE.replace("Ringvägen 12, 3 tr", "Parkvägen 3")
    property_id = add_listing(client, text)
    step(client, property_id, "start")
    info = step(client, property_id, "geocode", fixture("nominatim_choice_parkvagen_wrong_municipality.json"))["transport"]
    assert info["status"] == "choose"
    assert len(info["candidates"]) == 4
    assert "Inga träffar i Stockholms kommun" in info["message"]


def test_listing_municipality_with_one_exact_hit_among_others_continues(client):
    text = HEMNET_STYLE.replace("Ringvägen 12, 3 tr", "Parkvägen 3").replace("Stockholms kommun", "Solna kommun")
    property_id = add_listing(client, text)
    step(client, property_id, "start")
    result = step(client, property_id, "geocode", fixture("nominatim_choice_parkvagen_wrong_municipality.json"))
    assert result["request"]["stage"] == "stops"
    assert query_of(result["request"])["originCoordLat"][0].startswith("59.36")  # Råsunda, Solna.


def test_other_house_numbers_ask(client):
    text = HEMNET_STYLE.replace("Ringvägen 12, 3 tr", "Storgatan 1").replace("Stockholms kommun", "Umeå kommun")
    property_id = add_listing(client, text)
    step(client, property_id, "start")
    info = step(client, property_id, "geocode", fixture("nominatim_choice_umea_letters.json"))["transport"]
    assert info["status"] == "choose"
    assert [c["label"].split(",")[0] for c in info["candidates"]] == ["Storgatan 1A", "Storgatan 1b", "Storgatan 1c"]


# --- Continuing without transport -------------------------------------------------------------------


def test_skipping_is_remembered(client):
    property_id = add_listing(client)
    step(client, property_id, "start")
    step(client, property_id, "geocode", fixture("nominatim_choice_pilotgatan.json"))
    info = step(client, property_id, "skip")["transport"]
    assert info["status"] == "skipped"
    assert transport(client, property_id)["status"] == "skipped"


def test_skipping_works_before_any_lookup(client):
    property_id = add_listing(client)
    assert step(client, property_id, "skip")["transport"]["status"] == "skipped"


def test_a_new_address_ends_the_skip(client):
    property_id = add_listing(client)
    step(client, property_id, "skip")
    client.patch(f"/api/properties/{property_id}", json={"address": "Hornsgatan 5"})
    assert transport(client, property_id)["status"] == "stale"


def test_choosing_again_after_skipping(client):
    property_id = add_listing(client)
    step(client, property_id, "skip")
    request = step(client, property_id, "start")["request"]
    assert request["stage"] == "geocode"


# --- Comparison -------------------------------------------------------------------------------------


def test_comparison_explains_a_pending_choice_and_a_skip(client):
    choosing, skipped = add_listing(client), add_listing(client)
    step(client, choosing, "start")
    step(client, choosing, "geocode", fixture("nominatim_choice_pilotgatan.json"))
    step(client, skipped, "skip")
    comparison = client.get(f"/api/comparisons/properties?ids={choosing},{skipped}").json()
    first, second = next(r for r in comparison["rows"] if r["key"] == "transport:subway")["cells"]
    assert first["status"] == second["status"] == "missing"
    assert "Välj adress" in first["note"]
    assert "utan kollektivtrafik" in second["note"]


def test_house_level_hits_that_cant_be_used_are_not_called_street_level(client):
    data = fixture("nominatim_house.json")
    data[0]["lat"], data[0]["lon"] = "52.52", "13.40"  # A house in Berlin.
    property_id = add_listing(client)
    step(client, property_id, "start")
    info = step(client, property_id, "geocode", data)["transport"]
    assert info["status"] == "failed"
    assert "bara gatan" not in info["message"]
    assert info["house_level"] is not False  # A retry stays possible.


def test_choosing_for_an_old_address_is_refused(client):
    property_id = add_listing(client)
    step(client, property_id, "start")
    step(client, property_id, "geocode", fixture("nominatim_choice_pilotgatan.json"))
    client.patch(f"/api/properties/{property_id}", json={"address": "Kungsgatan 5"})
    response = post_step(client, property_id, {"stage": "choose", "choice": 0})
    assert response.status_code == 409
    assert field(client, property_id, "municipality")["value"] is None
