"""Choosing the apartment's address among Nominatim's hits (#21).

Boster continues on its own only when exactly one hit has the listing's municipality and the
exact house number; otherwise the user chooses. Fixtures: tests/fixtures/transport/README.md.
"""

import json
from pathlib import Path

import pytest

from app.transport.nearby import (
    GeocodeQuery, TransportLookupError, automatic_choice, geocode_query, order_candidates, parse_candidates,
)

FIXTURES = Path(__file__).parent / "fixtures" / "transport"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# --- The query ----------------------------------------------------------------------------------


def test_without_a_municipality_the_whole_country_is_searched():
    query = geocode_query("Pilotgatan 16, 1tr", None)
    assert query == GeocodeQuery(street="Pilotgatan 16", city=None)
    assert query.text == "Pilotgatan 16"
    params = query.params()
    assert "city" not in params
    assert params["limit"] == "10"
    assert params["countrycodes"] == "se"


def test_with_a_municipality_more_than_one_hit_is_requested():
    params = geocode_query("Ringvägen 12", "Stockholms kommun").params()
    assert params["city"] == "Stockholms kommun"
    assert params["limit"] == "5"  # Enough to notice that a street exists more than once.


def test_no_query_without_an_address():
    with pytest.raises(TransportLookupError, match="adress"):
        geocode_query(None, None)


# --- Reading the hits -----------------------------------------------------------------------------


def test_candidates_in_two_municipalities():
    candidates, truncated = parse_candidates(fixture("nominatim_choice_pilotgatan.json"), limit=10)
    assert [c.label for c in candidates] == [
        "Pilotgatan 16, Bagarmossen, Stockholms kommun",
        "Pilotgatan 16, Bärby hage, Uppsala kommun",
    ]
    assert candidates[0].municipality == "Stockholms kommun"
    assert candidates[0].display_name.startswith("16, Pilotgatan")
    assert truncated is False


def test_duplicates_are_merged_and_a_full_page_is_flagged():
    candidates, truncated = parse_candidates(fixture("nominatim_choice_storgatan.json"), limit=10)
    assert len(candidates) == 7  # Ten hits; Göteborg, Linköping and Sundsvall appear twice.
    assert truncated is True  # As many hits as asked for: there may be more.


def test_street_level_hits_are_not_candidates():
    candidates, _ = parse_candidates(fixture("nominatim_street_only.json"), limit=5)
    assert candidates == []


def test_hit_without_a_municipality_is_not_a_candidate():
    data = fixture("nominatim_house.json")
    del data[0]["address"]["municipality"]
    del data[0]["address"]["city"]
    candidates, _ = parse_candidates(data, limit=5)
    assert candidates == []


def test_no_hits():
    assert parse_candidates([], limit=5) == ([], False)


@pytest.mark.parametrize("data", [None, "text", {"lat": 1}])
def test_malformed_response(data):
    with pytest.raises(TransportLookupError):
        parse_candidates(data, limit=5)


def test_hit_outside_sweden_is_not_a_candidate():
    data = fixture("nominatim_house.json")
    data[0]["lat"], data[0]["lon"] = "52.52", "13.40"
    assert parse_candidates(data, limit=5) == ([], False)


# --- Continue on our own, or ask -----------------------------------------------------------------


def test_one_exact_hit_in_the_municipality_continues():
    candidates, _ = parse_candidates(fixture("nominatim_house.json"), limit=5)
    chosen = automatic_choice(candidates, geocode_query("Ringvägen 12, 3 tr", "Stockholms kommun"))
    assert chosen == candidates[0]


def test_municipality_as_a_city_name_matches():
    # Booli gives "Stockholm"; OpenStreetMap says "Stockholms kommun".
    candidates, _ = parse_candidates(fixture("nominatim_house.json"), limit=5)
    assert automatic_choice(candidates, geocode_query("Ringvägen 12", "Stockholm")) == candidates[0]


def test_without_a_municipality_the_user_always_chooses():
    candidates, _ = parse_candidates(fixture("nominatim_house.json"), limit=10)
    assert len(candidates) == 1
    assert automatic_choice(candidates, geocode_query("Ringvägen 12", None)) is None


def test_hits_in_other_municipalities_are_never_taken():
    # Nominatim's city parameter doesn't filter: "Parkvägen 3, Stockholms kommun" gives Solna and others.
    candidates, _ = parse_candidates(fixture("nominatim_choice_parkvagen_wrong_municipality.json"), limit=5)
    assert len(candidates) == 4  # Haninge appears twice.
    assert "Stockholms kommun" not in {c.municipality for c in candidates}
    assert automatic_choice(candidates, geocode_query("Parkvägen 3", "Stockholms kommun")) is None


def test_other_house_numbers_are_never_taken():
    # "Storgatan 1" in Umeå: only 1A, 1b and 1c exist in OpenStreetMap.
    candidates, _ = parse_candidates(fixture("nominatim_choice_umea_letters.json"), limit=5)
    assert [c.house_number for c in candidates] == ["1A", "1b", "1c"]
    assert automatic_choice(candidates, geocode_query("Storgatan 1", "Umeå kommun")) is None
    assert automatic_choice(candidates, geocode_query("Storgatan 1B", "Umeå kommun")) == candidates[1]
    assert automatic_choice(candidates, geocode_query("Storgatan 1 b", "Umeå kommun")) == candidates[1]


def test_several_exact_hits_in_the_municipality_ask():
    candidates, _ = parse_candidates(fixture("nominatim_choice_pilotgatan.json"), limit=10)
    both_in_stockholm = [candidates[0], candidates[1].__class__(**{**candidates[1].__dict__,
                                                                    "municipality": "Stockholms kommun"})]
    assert automatic_choice(both_in_stockholm, geocode_query("Pilotgatan 16", "Stockholms kommun")) is None


def test_hits_in_the_listings_municipality_come_first():
    candidates, _ = parse_candidates(fixture("nominatim_choice_pilotgatan.json"), limit=10)
    ordered = order_candidates(list(reversed(candidates)), geocode_query("Pilotgatan 16", "Stockholms kommun"))
    assert ordered[0].municipality == "Stockholms kommun"


def test_listing_municipality_with_kommun_matches_a_hit_named_by_city():
    data = fixture("nominatim_house.json")
    del data[0]["address"]["municipality"]  # Only city="Stockholm" is left.
    candidates, _ = parse_candidates(data, limit=5)
    assert candidates[0].municipality == "Stockholm"
    assert automatic_choice(candidates, geocode_query("Ringvägen 12", "Stockholms kommun")) == candidates[0]


def test_town_names_the_municipality_when_nothing_else_does():
    data = fixture("nominatim_house.json")
    address = data[0]["address"]
    del address["municipality"], address["city"]
    address["town"] = "Vännäs"
    candidates, _ = parse_candidates(data, limit=5)
    assert candidates[0].municipality == "Vännäs"
