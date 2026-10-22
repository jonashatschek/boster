"""Properties through the API: import from URL or text, corrections, cooperative linking."""

import pytest

from app.listings import fetching
from app.listings.fetching import FetchedPage, ListingFetchError
from app.services import properties as property_service
from tests.listing_samples import AGENT_HTML, BOOLI_STYLE, HEMNET_STYLE
from tests.report_factory import make_report_pdf


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """URL validation resolves hostnames; keep tests offline and deterministic."""
    monkeypatch.setattr(property_service, "validate_listing_url", lambda url: None)


def blocked_site(monkeypatch):
    def fetch(url, timeout_seconds):
        raise ListingFetchError("Hemnet tillåter inte automatisk hämtning av annonsen (HTTP 403). " + fetching.PASTE_ADVICE)
    monkeypatch.setattr(property_service, "fetch_listing_page", fetch)


def agent_site(monkeypatch):
    monkeypatch.setattr(property_service, "fetch_listing_page", lambda url, timeout_seconds: FetchedPage(url, AGENT_HTML))


def field(overview, key):
    return next(f for f in overview["fields"] if f["key"] == key)


def derived(overview, key):
    return next(d for d in overview["derived"] if d["key"] == key)


def add_cooperative(client, **report):
    content = make_report_pdf(**report)
    response = client.post("/api/documents/upload", files={"file": ("rapport.pdf", content, "application/pdf")})
    return response.json()["cooperative_id"]


def test_blocked_site_still_creates_property_with_advice(client, monkeypatch):
    blocked_site(monkeypatch)
    response = client.post("/api/properties/from-url", json={"url": "https://www.hemnet.se/bostad/123"})
    assert response.status_code == 201
    overview = response.json()
    assert overview["retrieval_status"] == "fetch_failed"
    assert "klistra in" in overview["retrieval_message"].lower()
    assert overview["source_name"] == "Hemnet"
    assert field(overview, "asking_price")["status"] == "missing"


def test_pasting_text_after_a_blocked_fetch_fills_in_the_facts(client, monkeypatch):
    blocked_site(monkeypatch)
    overview = client.post("/api/properties/from-url", json={"url": "https://www.hemnet.se/bostad/123"}).json()
    overview = client.post(f"/api/properties/{overview['id']}/text", json={"text": HEMNET_STYLE}).json()
    assert overview["retrieval_status"] == "pasted"
    assert field(overview, "asking_price")["value"] == 4_250_000
    assert field(overview, "asking_price")["status"] == "extracted"
    assert "4 250 000 kr" in field(overview, "asking_price")["excerpt"]
    assert overview["source_url"] == "https://www.hemnet.se/bostad/123"


def test_fetched_agent_page(client, monkeypatch):
    agent_site(monkeypatch)
    overview = client.post("/api/properties/from-url", json={"url": "https://maklare.example/objekt/1"}).json()
    assert overview["retrieval_status"] == "fetched"
    assert field(overview, "living_area")["value"] == 71
    assert field(overview, "living_area")["method"] == "structured_data"
    assert overview["has_listing_text"]


def test_same_url_twice_returns_the_same_property(client, monkeypatch):
    agent_site(monkeypatch)
    first = client.post("/api/properties/from-url", json={"url": "https://maklare.example/objekt/1"}).json()
    second = client.post("/api/properties/from-url", json={"url": "https://maklare.example/objekt/1"}).json()
    assert first["id"] == second["id"]
    assert len(client.get("/api/properties").json()) == 1


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


def test_list_shows_cooperative_risk(client):
    add_cooperative(client, name="Brf Segelflygaren", organisation_number="716416-7939")
    client.post("/api/properties/from-text", json={"text": HEMNET_STYLE})
    [item] = client.get("/api/properties").json()
    assert item["asking_price"] == 4_250_000
    assert item["cooperative_overall_level"] is not None
