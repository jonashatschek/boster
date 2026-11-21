"""Properties through the API: import from pasted text, corrections, cooperative linking."""

import pytest

from tests.listing_samples import BOOLI_STYLE, HEMNET_STYLE
from tests.report_factory import make_report_pdf
from tests.uploads import upload_pdf


def field(overview, key):
    return next(f for f in overview["fields"] if f["key"] == key)


def derived(overview, key):
    return next(d for d in overview["derived"] if d["key"] == key)


def add_cooperative(client, **report):
    content = make_report_pdf(**report)
    response = upload_pdf(client, content, "rapport.pdf")
    return response.json()["cooperative_id"]


def test_pasted_text_with_a_link_fills_in_the_facts(client):
    overview = client.post("/api/properties/from-text",
                           json={"text": HEMNET_STYLE, "url": "https://www.hemnet.se/bostad/123"}).json()
    assert overview["retrieval_status"] == "pasted"
    assert field(overview, "asking_price")["value"] == 4_250_000
    assert field(overview, "asking_price")["status"] == "extracted"
    assert "4 250 000 kr" in field(overview, "asking_price")["excerpt"]
    assert overview["source_url"] == "https://www.hemnet.se/bostad/123"
    assert overview["source_name"] == "Hemnet"


def test_listing_link_must_be_a_web_address(client):
    response = client.post("/api/properties/from-text", json={"text": HEMNET_STYLE, "url": "javascript:alert(1)"})
    assert response.status_code == 422
    assert "http" in response.json()["detail"]


def test_link_is_saved_but_never_fetched(client):
    assert client.post("/api/properties/from-url", json={"url": "https://www.hemnet.se/bostad/1"}).status_code in (404, 405)


def test_calculated_price_per_sqm(client):
    overview = client.post("/api/properties/from-text", json={"text": HEMNET_STYLE}).json()
    price_per_sqm = derived(overview, "price_per_sqm")
    assert price_per_sqm["value"] == pytest.approx(4_250_000 / 54.5)
    assert price_per_sqm["formula"] == "Utgångspris / boarea"
    assert derived(overview, "fee_per_sqm_year")["value"] == pytest.approx(3_245 * 12 / 54.5)


def test_missing_price_is_never_estimated(client):
    text = BOOLI_STYLE.replace("Utgångspris 3 950 000 kr\n", "")
    overview = client.post("/api/properties/from-text", json={"text": text}).json()
    assert field(overview, "asking_price")["value"] is None
    assert field(overview, "asking_price")["status"] == "missing"
    assert derived(overview, "price_per_sqm")["value"] is None
    assert derived(overview, "price_per_sqm")["missing_inputs"] == ["Utgångspris"]
    assert "Utgångspris" in overview["missing"]


def test_manual_correction_survives_re_analysis(client):
    overview = client.post("/api/properties/from-text", json={"text": HEMNET_STYLE}).json()
    property_id = overview["id"]
    overview = client.patch(f"/api/properties/{property_id}", json={"monthly_fee": 3_500}).json()
    assert field(overview, "monthly_fee")["status"] == "user_entered"
    overview = client.post(f"/api/properties/{property_id}/text", json={"text": HEMNET_STYLE}).json()
    assert field(overview, "monthly_fee")["value"] == 3_500


def test_verify_field(client):
    overview = client.post("/api/properties/from-text", json={"text": HEMNET_STYLE}).json()
    overview = client.post(f"/api/properties/{overview['id']}/fields/living_area/verify").json()
    assert field(overview, "living_area")["status"] == "verified"


def test_invalid_correction_is_rejected(client):
    overview = client.post("/api/properties/from-text", json={"text": HEMNET_STYLE}).json()
    response = client.patch(f"/api/properties/{overview['id']}", json={"energy_class": "Z"})
    assert response.status_code == 422
    response = client.patch(f"/api/properties/{overview['id']}", json={"unknown_field": 1})
    assert response.status_code == 422


def test_links_to_existing_cooperative_with_exact_name(client):
    cooperative_id = add_cooperative(client, name="HSB Brf Segelflygaren i Stockholm", organisation_number="716416-7939")
    overview = client.post("/api/properties/from-text", json={"text": HEMNET_STYLE}).json()
    assert overview["cooperative"]["id"] == cooperative_id


def test_similar_name_is_suggested_not_linked(client):
    add_cooperative(client, name="Brf Byamännen", organisation_number="769600-0001")
    overview = client.post("/api/properties/from-text", json={"text": BOOLI_STYLE}).json()  # "Brf Byamännen 2".
    assert overview["cooperative"] is None
    assert [c["name"] for c in overview["cooperative_suggestions"]] == ["Brf Byamännen"]


def test_uploading_report_later_links_waiting_property(client):
    overview = client.post("/api/properties/from-text", json={"text": HEMNET_STYLE}).json()
    assert overview["cooperative"] is None
    cooperative_id = add_cooperative(client, name="HSB Brf Segelflygaren i Stockholm", organisation_number="716416-7939")
    overview = client.get(f"/api/properties/{overview['id']}").json()
    assert overview["cooperative"]["id"] == cooperative_id


def test_debt_share_uses_cooperative_figures(client):
    cooperative_id = add_cooperative(client, name="Brf Segelflygaren", organisation_number="716416-7939")
    overview = client.post("/api/properties/from-text", json={"text": HEMNET_STYLE}).json()
    assert overview["cooperative"]["id"] == cooperative_id
    share = derived(overview, "debt_share")
    # The test report has 4 000 kr/kvm per total area but no figure per tenant-owned area.
    assert share["value"] == pytest.approx(54.5 * 4_000)
    assert "totalyta" in share["note"]
    increase = derived(overview, "fee_increase_per_percentage_point")
    assert increase["value"] == pytest.approx(54.5 * 4_000 * 0.01 / 12)


def test_manual_link_and_unlink(client):
    cooperative_id = add_cooperative(client)
    overview = client.post("/api/properties/from-text", json={"text": BOOLI_STYLE}).json()
    overview = client.put(f"/api/properties/{overview['id']}/cooperative", json={"cooperative_id": cooperative_id}).json()
    assert overview["cooperative"]["id"] == cooperative_id
    assert overview["cooperative"]["indicators"]
    overview = client.put(f"/api/properties/{overview['id']}/cooperative", json={"cooperative_id": None}).json()
    assert overview["cooperative"] is None


COOPERATIVE_NAME_LABEL = "Förening enligt annonsen"


def reported_missing(overview):
    """Everything the overview reports as missing: the list and the warning shown on the page."""
    return " ".join(overview["missing"]) + " " + (overview["retrieval_message"] or "").lower()


def test_cooperative_name_is_reported_missing_when_no_cooperative_is_linked(client):
    text = HEMNET_STYLE.replace("Förening\nBRF Segelflygaren\n", "")
    overview = client.post("/api/properties/from-text", json={"text": text}).json()
    assert COOPERATIVE_NAME_LABEL in overview["missing"]
    assert COOPERATIVE_NAME_LABEL.lower() in overview["retrieval_message"]


def test_cooperative_name_is_not_missing_once_a_cooperative_is_linked_manually(client):
    cooperative_id = add_cooperative(client)
    text = HEMNET_STYLE.replace("Förening\nBRF Segelflygaren\n", "")
    overview = client.post("/api/properties/from-text", json={"text": text}).json()
    overview = client.put(f"/api/properties/{overview['id']}/cooperative", json={"cooperative_id": cooperative_id}).json()
    assert COOPERATIVE_NAME_LABEL.lower() not in reported_missing(overview).lower()


def test_cooperative_name_is_not_missing_after_clearing_it_on_a_linked_property(client):
    add_cooperative(client, name="HSB Brf Segelflygaren i Stockholm", organisation_number="716416-7939")
    overview = client.post("/api/properties/from-text", json={"text": HEMNET_STYLE}).json()
    assert overview["cooperative"] is not None
    overview = client.patch(f"/api/properties/{overview['id']}", json={"cooperative_name": None}).json()
    assert overview["cooperative"] is not None
    assert COOPERATIVE_NAME_LABEL.lower() not in reported_missing(overview).lower()


def test_warning_follows_values_filled_in_by_hand(client):
    text = BOOLI_STYLE.replace("Utgångspris 3 950 000 kr\n", "")
    overview = client.post("/api/properties/from-text", json={"text": text}).json()
    assert "utgångspris" in overview["retrieval_message"]
    overview = client.patch(f"/api/properties/{overview['id']}", json={"asking_price": 3_950_000}).json()
    assert "utgångspris" not in (overview["retrieval_message"] or "")


def test_deleting_cooperative_keeps_property(client):
    cooperative_id = add_cooperative(client, name="Brf Segelflygaren", organisation_number="716416-7939")
    overview = client.post("/api/properties/from-text", json={"text": HEMNET_STYLE}).json()
    client.delete(f"/api/cooperatives/{cooperative_id}")
    overview = client.get(f"/api/properties/{overview['id']}").json()
    assert overview["cooperative"] is None
    assert field(overview, "asking_price")["value"] == 4_250_000


def test_delete_property(client):
    overview = client.post("/api/properties/from-text", json={"text": HEMNET_STYLE}).json()
    assert client.delete(f"/api/properties/{overview['id']}").status_code == 204
    assert client.get(f"/api/properties/{overview['id']}").status_code == 404


def test_delete_all_properties_keeps_cooperatives(client):
    cooperative_id = add_cooperative(client, name="HSB Brf Segelflygaren i Stockholm", organisation_number="716416-7939")
    client.post("/api/properties/from-text", json={"text": HEMNET_STYLE})
    client.post("/api/properties/from-text", json={"text": BOOLI_STYLE})
    assert len(client.get("/api/properties").json()) == 2
    assert client.delete("/api/properties").status_code == 204
    assert client.get("/api/properties").json() == []
    assert [c["id"] for c in client.get("/api/cooperatives").json()] == [cooperative_id]


def test_delete_all_cooperatives_keeps_properties_unlinked(client):
    add_cooperative(client, name="HSB Brf Segelflygaren i Stockholm", organisation_number="716416-7939")
    add_cooperative(client, name="Brf Byamännen", organisation_number="769600-0001")
    overview = client.post("/api/properties/from-text", json={"text": HEMNET_STYLE}).json()
    assert overview["cooperative"] is not None
    assert client.delete("/api/cooperatives").status_code == 204
    assert client.get("/api/cooperatives").json() == []
    overview = client.get(f"/api/properties/{overview['id']}").json()
    assert overview["cooperative"] is None
    assert field(overview, "asking_price")["value"] == 4_250_000


def test_delete_all_on_empty_lists(client):
    assert client.delete("/api/properties").status_code == 204
    assert client.delete("/api/cooperatives").status_code == 204


def test_list_shows_cooperative_risk(client):
    add_cooperative(client, name="Brf Segelflygaren", organisation_number="716416-7939")
    client.post("/api/properties/from-text", json={"text": HEMNET_STYLE})
    [item] = client.get("/api/properties").json()
    assert item["asking_price"] == 4_250_000
    assert (item["cooperative_score"], item["cooperative_score_label"]) == (47, None)  # Default report: 47.
    assert "cooperative_overall_level" not in item


def test_list_without_linked_cooperative_has_no_score(client):
    client.post("/api/properties/from-text", json={"text": HEMNET_STYLE})
    [item] = client.get("/api/properties").json()
    assert (item["cooperative_score"], item["cooperative_score_label"]) == (None, None)


