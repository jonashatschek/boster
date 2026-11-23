"""Comparing apartments side by side through the API."""

import pytest

from tests.listing_samples import BOOLI_STYLE, HEMNET_STYLE
from tests.report_factory import make_report_pdf
from tests.uploads import upload_pdf

MAINTENANCE_NOTES = (
    "Stambyte genomfördes under året i samtliga trapphus.",
    "Föreningen planerar takomläggning år 2027 enligt underhållsplanen.",
)


def add_cooperative(client, **report) -> int:
    response = upload_pdf(client, make_report_pdf(**report), "rapport.pdf")
    assert response.status_code == 201, response.text
    return response.json()["cooperative_id"]


def add_property(client, text) -> int:
    response = client.post("/api/properties/from-text", json={"text": text})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def compare(client, *ids):
    return client.get("/api/comparisons/properties", params={"ids": ",".join(map(str, ids))})


def row(comparison, key):
    return next(r for r in comparison["rows"] if r["key"] == key)


def values(comparison, key):
    return [cell["value"] for cell in row(comparison, key)["cells"]]


@pytest.fixture
def two_properties(client):
    """Ringvägen (linked to Brf Segelflygaren, with maintenance notes) and Kungsholmsgatan (no cooperative)."""
    cooperative = add_cooperative(client, name="Brf Segelflygaren", notes=MAINTENANCE_NOTES)
    linked = add_property(client, HEMNET_STYLE)
    unlinked = add_property(client, BOOLI_STYLE)
    return linked, unlinked, cooperative


# --- Rows ---------------------------------------------------------------------------------------


def test_listing_facts_side_by_side(client, two_properties):
    linked, unlinked, _ = two_properties
    comparison = compare(client, linked, unlinked).json()
    assert [p["id"] for p in comparison["properties"]] == [linked, unlinked]
    assert [p["address"] for p in comparison["properties"]] == ["Ringvägen 12, 3 tr", "Kungsholmsgatan 8"]
    assert values(comparison, "asking_price") == [4_250_000, 3_950_000]
    assert values(comparison, "living_area") == [54.5, 41]
    assert values(comparison, "rooms") == [2, 1.5]
    assert values(comparison, "monthly_fee") == [3_245, 2_410]
    assert values(comparison, "construction_year") == [1929, 1937]
    assert values(comparison, "balcony") == [True, False]
    assert row(comparison, "address")["group"] == "Läge"
    assert row(comparison, "energy_class")["group"] == "Egenskaper"


def test_price_per_sqm_is_calculated_with_its_formula(client, two_properties):
    comparison = compare(client, *two_properties[:2]).json()
    price_per_sqm = row(comparison, "price_per_sqm")
    assert [c["value"] for c in price_per_sqm["cells"]] == [pytest.approx(4_250_000 / 54.5),
                                                              pytest.approx(3_950_000 / 41)]
    assert all(c["status"] == "calculated" for c in price_per_sqm["cells"])
    assert "Utgångspris / boarea" in price_per_sqm["cells"][0]["excerpt"]
    assert price_per_sqm["is_estimate"] is False


def test_cooperative_name_and_risk_indicators_per_apartment(client, two_properties):
    linked, unlinked, cooperative = two_properties
    comparison = compare(client, linked, unlinked).json()
    assert comparison["properties"][0]["cooperative_id"] == cooperative
    assert values(comparison, "cooperative") == ["Brf Segelflygaren", None]
    debt = row(comparison, "risk:debt_per_sqm_total_area")
    assert debt["group"] == "Förening"
    first = debt["cells"][0]
    assert (first["value"], first["fiscal_year"], first["status"]) == (4_000, 2025, "extracted")
    assert first["level"] is not None and first["level_label"]
    assert first["excerpt"] == "rapport.pdf, s. 2: ”Skuldsättning, kr/kvm”"  # Provenance: document, page, label.
    score = row(comparison, "cooperative_score")
    assert score["label"] == "Föreningens poäng"
    linked_cell, unlinked_cell = score["cells"]
    assert linked_cell["value"] == 41 == comparison["properties"][0]["cooperative_score"]
    assert linked_cell["note"] == (
        "Baserat på 4 av 6 nyckeltal och marken (77 % av vikten), 0 av 2 trender och 0 av 3 underhållssvar.")
    assert linked_cell["level"] is None  # A number, not a verdict colour.
    assert unlinked_cell["value"] is None and unlinked_cell["status"] == "missing"
    assert "overall_level" not in comparison["properties"][0]


def test_maintenance_topics_with_pages(client, two_properties):
    comparison = compare(client, *two_properties[:2]).json()
    linked, unlinked = comparison["properties"]
    topics = {finding["topic"] for finding in linked["maintenance"]}
    assert {"Stambyte", "Tak"} <= topics
    stambyte = next(f for f in linked["maintenance"] if f["topic"] == "Stambyte")
    assert stambyte["page"] == 4
    assert "Stambyte genomfördes" in stambyte["excerpt"]
    assert unlinked["maintenance"] == []
    topics_row = row(comparison, "maintenance_topics")
    assert (topics_row["group"], topics_row["kind"]) == ("Underhåll", "findings")
    linked_cell, unlinked_cell = topics_row["cells"]
    assert "Stambyte" in linked_cell["value"] and linked_cell["status"] == "extracted"
    assert (unlinked_cell["value"], unlinked_cell["status"]) == (None, "missing")
    assert "Ingen förening kopplad" in unlinked_cell["note"]


def test_announced_fee_changes_row(client, two_properties):
    linked, unlinked, _ = two_properties
    client.patch(f"/api/properties/{linked}", json={"fee_changes": "Avgiften höjs med 5 % från 1 januari."})
    comparison = compare(client, linked, unlinked).json()
    fee_changes = row(comparison, "fee_changes")
    assert fee_changes["group"] == "Underhåll"
    assert values(comparison, "fee_changes") == ["Avgiften höjs med 5 % från 1 januari.", None]


def test_estimates_are_marked(client, two_properties):
    comparison = compare(client, *two_properties[:2]).json()
    for key in ("debt_share", "fee_increase_per_percentage_point"):
        estimate = row(comparison, key)
        assert estimate["is_estimate"] is True
        assert estimate["cells"][0]["value"] == pytest.approx(54.5 * 4_000 if key == "debt_share"
                                                              else 54.5 * 4_000 * 0.01 / 12)
        assert estimate["cells"][0]["status"] == "estimated"  # An approximation, not a calculated fact.
        assert estimate["cells"][1]["value"] is None  # No cooperative, so nothing to base it on.
        assert "Ingen förening kopplad" in estimate["cells"][1]["note"]


def test_warns_when_estimates_use_different_debt_measures(client, two_properties):
    linked, _, _ = two_properties
    add_cooperative(client, name="Brf Byamännen 2", organisation_number="769600-5678",
                    key_figures=[("Skuldsättning per kvm upplåten med bostadsrätt, kr/kvm", "5 000", "5 100")])
    other = add_property(client, BOOLI_STYLE)
    comparison = compare(client, linked, other).json()
    excerpts = [cell["excerpt"] for cell in row(comparison, "debt_share")["cells"]]
    assert "totalyta" in excerpts[0] and "bostadsrättsyta" in excerpts[1]
    assert any("olika mått" in w and "totalyta" in w and "bostadsrättsyta" in w for w in comparison["warnings"])


def test_manually_linked_cooperative_keeps_its_provenance(client, two_properties):
    linked, unlinked, cooperative = two_properties
    client.put(f"/api/properties/{unlinked}/cooperative", json={"cooperative_id": cooperative})
    cells = row(compare(client, linked, unlinked).json(), "cooperative")["cells"]
    assert (cells[0]["status"], cells[0]["excerpt"]) == ("extracted", "Kopplad på exakt namn: annonsen anger ”BRF Segelflygaren”.")
    assert (cells[1]["status"], cells[1]["excerpt"]) == ("user_entered", "Kopplad manuellt.")


def test_listing_cooperative_name_is_not_reported_missing_when_linked(client, two_properties):
    linked, unlinked, _ = two_properties
    client.patch(f"/api/properties/{linked}", json={"cooperative_name": None})
    comparison = compare(client, linked, unlinked).json()
    assert comparison["properties"][0]["cooperative_id"] is not None
    assert not any(w.startswith("Ringvägen") for w in comparison["warnings"])


# --- Status, provenance and missing values ---------------------------------------------------------


def test_values_keep_status_and_source(client, two_properties):
    linked, unlinked, _ = two_properties
    client.patch(f"/api/properties/{unlinked}", json={"asking_price": 3_800_000})
    cells = row(compare(client, linked, unlinked).json(), "asking_price")["cells"]
    assert cells[0]["status"] == "extracted"
    assert "4 250 000 kr" in cells[0]["excerpt"]
    assert (cells[1]["value"], cells[1]["status"]) == (3_800_000, "user_entered")


def test_missing_value_is_missing_not_zero(client, two_properties):
    linked, unlinked, _ = two_properties
    client.patch(f"/api/properties/{linked}", json={"asking_price": None, "monthly_fee": 0})
    comparison = compare(client, linked, unlinked).json()
    price = row(comparison, "asking_price")["cells"][0]
    assert (price["value"], price["status"]) == (None, "missing")
    fee = row(comparison, "monthly_fee")["cells"][0]
    assert (fee["value"], fee["status"]) == (0, "user_entered")
    price_per_sqm = row(comparison, "price_per_sqm")["cells"][0]
    assert (price_per_sqm["value"], price_per_sqm["status"]) == (None, "missing")
    assert "utgångspris" in price_per_sqm["note"].lower()


def test_apartment_without_cooperative(client, two_properties):
    linked, unlinked, _ = two_properties
    comparison = compare(client, linked, unlinked).json()
    assert comparison["properties"][1]["cooperative_id"] is None
    cell = row(comparison, "cooperative")["cells"][1]
    assert cell["status"] == "missing"
    assert "Ingen förening kopplad" in cell["note"]
    assert "Byamännen 2" in cell["note"]  # The name the listing gives, for the user to act on.
    debt = row(comparison, "risk:debt_per_sqm_total_area")["cells"][1]
    assert (debt["value"], debt["status"], debt["level"]) == (None, "missing", None)
    assert any("Kungsholmsgatan 8" in w and "ingen kopplad förening" in w for w in comparison["warnings"])


def test_no_ranking(client, two_properties):
    comparison = compare(client, *two_properties[:2]).json()
    assert all("rank" not in p for p in comparison["properties"])
    assert all("rank" not in cell and "best" not in cell for r in comparison["rows"] for cell in r["cells"])


def test_warns_when_fiscal_years_differ(client, two_properties):
    linked, _, _ = two_properties
    add_cooperative(client, name="Brf Byamännen 2", organisation_number="769600-5678",
                    period=("2024-01-01", "2024-12-31"), previous_period_end="2023-12-31")
    other = add_property(client, BOOLI_STYLE)
    comparison = compare(client, linked, other).json()
    assert [p["fiscal_year"] for p in comparison["properties"]] == [2025, 2024]
    assert any("olika räkenskapsår" in w for w in comparison["warnings"])


# --- Selection -----------------------------------------------------------------------------------


def test_rejects_invalid_too_few_too_many_and_unknown_ids(client, two_properties):
    linked, unlinked, _ = two_properties
    assert compare(client, "x").status_code == 422
    assert "Ogiltiga" in compare(client, "x").json()["detail"]
    too_few = compare(client, linked)
    assert too_few.status_code == 422 and "mellan 2 och 4" in too_few.json()["detail"]
    assert compare(client, linked, linked).status_code == 422  # Duplicates count once.
    extra = [add_property(client, BOOLI_STYLE) for _ in range(3)]
    assert compare(client, linked, unlinked, *extra).status_code == 422
    unknown = compare(client, linked, 999)
    assert unknown.status_code == 404 and "999" in unknown.json()["detail"]


@pytest.mark.parametrize("invalid_id", ["-1", "0"])
def test_id_of_zero_or_below_is_invalid_not_unknown(client, two_properties, invalid_id):
    # Ids are always positive, so these get the malformed-id answer, not "Bostaden 0 finns inte."
    _, unlinked, _ = two_properties
    response = compare(client, invalid_id, unlinked)
    assert response.status_code == 422
    assert response.json()["detail"] == "Ogiltiga bostads-id."
