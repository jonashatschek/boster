"""End-to-end tests through the HTTP API: upload a report, read the analysis, correct values."""

from pathlib import Path

import pytest

from tests.report_factory import make_report_pdf
from tests.uploads import upload_pdf

SAMPLES = Path(__file__).parents[2] / "sample_documents"


def upload(client, content, filename="arsredovisning.pdf"):
    return upload_pdf(client, content, filename)


def series(overview, key):
    return next(m for m in overview["metrics"] if m["key"] == key)


def year_value(overview, key, year):
    return next(v for v in series(overview, key)["values"] if v["fiscal_year"] == year)


def test_upload_creates_cooperative_with_sourced_figures(client):
    response = upload(client, make_report_pdf())
    assert response.status_code == 201, response.text
    document = response.json()
    assert document["document_type"] == "annual_report"
    assert document["reporting_year"] == 2025

    overview = client.get(f"/api/cooperatives/{document['cooperative_id']}").json()
    assert overview["cooperative"]["name"] == "Brf Provhuset"
    assert overview["cooperative"]["organisation_number"] == "769600-1234"
    assert overview["cooperative"]["land_tenure"] == "leasehold"

    debt = year_value(overview, "interest_bearing_debt", 2025)
    assert debt["display_value"] == 40_000_000
    assert debt["display_status"] == "extracted"
    assert debt["reported"]["sources"][0]["page"] == 3
    assert debt["reported"]["sources"][0]["document_id"] == document["id"]


def test_calculated_kpis_show_formula_and_inputs(client):
    document = upload(client, make_report_pdf()).json()
    overview = client.get(f"/api/cooperatives/{document['cooperative_id']}").json()
    net_debt = year_value(overview, "net_debt", 2025)
    assert net_debt["display_value"] == 39_000_000
    assert net_debt["display_status"] == "calculated"
    assert net_debt["calculated"]["formula"]
    assert net_debt["calculated"]["inputs"] == {"interest_bearing_debt": 40_000_000, "cash": 1_000_000}


def test_risk_assessment_uses_several_indicators(client):
    document = upload(client, make_report_pdf()).json()
    risk = client.get(f"/api/cooperatives/{document['cooperative_id']}").json()["risk"]
    levels = {i["key"]: i["level"] for i in risk["indicators"]}
    assert levels["savings_per_sqm"] == "high"  # 90 kr/kvm.
    assert levels["interest_sensitivity_pct"] == "high"  # 12 %.
    assert levels["debt_per_sqm_total_area"] == "low"
    assert levels["land_tenure"] == "moderate"
    assert risk["overall_level"] == "high"
    assert risk["disclaimer"]


def test_missing_data_is_listed_not_invented(client):
    document = upload(client, make_report_pdf()).json()
    overview = client.get(f"/api/cooperatives/{document['cooperative_id']}").json()
    assert "total_area" in overview["completeness"]["missing"]
    assert "energy_cost_per_sqm" in overview["completeness"]["missing"]
    assert all(m["key"] != "energy_cost_per_sqm" for m in overview["metrics"])


def test_uploading_the_same_file_twice_reuses_the_document(client):
    content = make_report_pdf()
    first = upload(client, content).json()
    second = upload(client, content, filename="kopia.pdf").json()
    assert first["id"] == second["id"]
    assert len(client.get("/api/cooperatives").json()) == 1


def test_manual_value_overrides_and_enables_calculations(client):
    document = upload(client, make_report_pdf()).json()
    cooperative_id = document["cooperative_id"]
    response = client.post(f"/api/cooperatives/{cooperative_id}/observations",
                           json={"metric_key": "total_area", "fiscal_year": 2025, "value": 10_000})
    assert response.status_code == 201
    overview = response.json()
    area = year_value(overview, "total_area", 2025)
    assert area["display_status"] == "user_entered"
    # Our own debt/kvm (40 000 000 / 10 000) agrees with the reported 4 000 kr/kvm.
    debt_per_sqm = year_value(overview, "debt_per_sqm_total_area", 2025)
    assert debt_per_sqm["calculated"]["value"] == 4_000
    assert debt_per_sqm["display_status"] == "extracted"


def test_calculation_that_disagrees_with_report_is_flagged(client):
    document = upload(client, make_report_pdf()).json()
    overview = client.post(f"/api/cooperatives/{document['cooperative_id']}/observations",
                           json={"metric_key": "total_area", "fiscal_year": 2025, "value": 5_000}).json()
    debt_per_sqm = year_value(overview, "debt_per_sqm_total_area", 2025)
    assert debt_per_sqm["display_status"] == "conflicting"
    assert debt_per_sqm["display_value"] == 4_000  # The reported value stays visible ...
    assert "avviker" in debt_per_sqm["warning"]  # ... with an explanation of the discrepancy.


def test_extracted_values_cannot_be_deleted_but_manual_ones_can(client):
    document = upload(client, make_report_pdf()).json()
    overview = client.get(f"/api/cooperatives/{document['cooperative_id']}").json()
    extracted_id = year_value(overview, "cash", 2025)["reported"]["sources"][0]["observation_id"]
    assert client.delete(f"/api/observations/{extracted_id}").status_code == 409

    overview = client.post(f"/api/cooperatives/{document['cooperative_id']}/observations",
                           json={"metric_key": "cash", "fiscal_year": 2025, "value": 1}).json()
    manual = next(s for s in year_value(overview, "cash", 2025)["reported"]["sources"] if s["method"] == "manual")
    overview = client.delete(f"/api/observations/{manual['observation_id']}").json()
    assert year_value(overview, "cash", 2025)["display_value"] == 1_000_000


def test_verify_marks_value_as_checked(client):
    document = upload(client, make_report_pdf()).json()
    overview = client.get(f"/api/cooperatives/{document['cooperative_id']}").json()
    observation_id = year_value(overview, "cash", 2025)["reported"]["sources"][0]["observation_id"]
    overview = client.post(f"/api/observations/{observation_id}/verify").json()
    assert year_value(overview, "cash", 2025)["display_status"] == "verified"


def test_document_can_be_moved_to_another_cooperative(client):
    document = upload(client, make_report_pdf()).json()
    original_id = document["cooperative_id"]
    other = upload(client, Path(SAMPLES / "friheten_arsredovisning_2024-2025.pdf").read_bytes()).json() \
        if (SAMPLES / "friheten_arsredovisning_2024-2025.pdf").exists() else None
    if other is None:
        pytest.skip("Sample document not downloaded")
    response = client.patch(f"/api/documents/{document['id']}", json={"cooperative_id": other["cooperative_id"]})
    assert response.status_code == 200
    moved = client.get(f"/api/cooperatives/{other['cooperative_id']}").json()
    assert any(d["id"] == document["id"] for d in moved["documents"])
    assert client.get(f"/api/cooperatives/{original_id}").json()["metrics"] == []


def test_rejects_files_that_are_not_pdfs(client):
    response = upload(client, b"<html>not a pdf</html>", "sida.html")
    assert response.status_code == 422
    assert "PDF" in response.json()["detail"]


def test_unreadable_page_text_stores_the_file_but_reports_it(client):
    document = upload_pdf(client, make_report_pdf(), pages="not json").json()
    assert document["extraction_status"] == "failed"
    assert "kunde inte läsas" in document["extraction_messages"][0]


def test_page_text_is_validated(client):
    document = upload_pdf(client, make_report_pdf(), pages='[{"text": "x", "words": [[0, 0, "a", 1, "b"]]}]').json()
    assert document["extraction_status"] == "failed"


def test_document_file_is_served(client):
    content = make_report_pdf()
    document = upload(client, content).json()
    response = client.get(f"/api/documents/{document['id']}/file")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == content


def test_deleting_cooperative_removes_documents_and_files(client, tmp_path):
    document = upload(client, make_report_pdf()).json()
    assert list((tmp_path / "documents").glob("*.pdf"))
    assert client.delete(f"/api/cooperatives/{document['cooperative_id']}").status_code == 204
    assert client.get(f"/api/documents/{document['id']}").status_code == 404
    assert not list((tmp_path / "documents").glob("*.pdf"))
    assert client.get("/api/cooperatives").json() == []


def test_deleting_all_cooperatives_removes_all_documents_and_files(client, tmp_path):
    first = upload(client, make_report_pdf()).json()
    second = upload(client, make_report_pdf(name="Brf Andra", organisation_number="769600-5678"), "andra.pdf").json()
    assert len(list((tmp_path / "documents").glob("*.pdf"))) == 2
    assert client.delete("/api/cooperatives").status_code == 204
    for document in (first, second):
        assert client.get(f"/api/documents/{document['id']}").status_code == 404
    assert not list((tmp_path / "documents").glob("*.pdf"))
    assert client.get("/api/cooperatives").json() == []


def test_real_report_end_to_end(client):
    path = SAMPLES / "soderbysjon_arsredovisning.pdf"
    if not path.exists():
        pytest.skip("Sample document not downloaded")
    document = upload(client, path.read_bytes(), path.name).json()
    assert any("16 månader" in m for m in document["extraction_messages"])
    overview = client.get(f"/api/cooperatives/{document['cooperative_id']}").json()
    # The two different residential areas in the report are shown as a conflict.
    area = year_value(overview, "residential_area", 2025)
    assert area["display_status"] == "conflicting"
    assert {s["value"] for s in area["reported"]["sources"]} == {26_688, 21_311}
    # Debt per m² has a five-year history.
    assert len(series(overview, "debt_per_sqm_total_area")["values"]) == 5


def test_startup_adds_columns_missing_from_an_older_database(tmp_path):
    import sqlite3

    from app.config import Settings
    from app.main import create_app

    database = tmp_path / "boster.db"
    with sqlite3.connect(database) as connection:  # A properties table from before fee_changes existed.
        connection.execute("CREATE TABLE properties (id INTEGER PRIMARY KEY, retrieval_status VARCHAR(20), "
                           "field_sources JSON, created_at DATETIME, updated_at DATETIME)")
    create_app(Settings(data_directory=tmp_path))
    with sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(properties)")}
    assert {"fee_changes", "address", "asking_price"} <= columns


def test_overview_has_score_with_its_explanation(client):
    # Default report: debt 4 000 kr/m² (part 100, weight 25), savings 90 kr/m² (0, 20), interest
    # sensitivity 12 % (0, 20), short-term debt 0 % (100, 10); fee share and interest coverage missing.
    # (100·25 + 0·20 + 0·20 + 100·10) / 75 = 46.7 → 47, with 75 % of the weight.
    cooperative_id = upload(client, make_report_pdf()).json()["cooperative_id"]
    score = client.get(f"/api/cooperatives/{cooperative_id}").json()["score"]
    assert score["score"] == 47
    assert score["weight_share"] == pytest.approx(0.75)
    assert score["key_figures_assessed"] == 4
    assert score["key_figures_total"] == 6
    parts = {p["key"]: p for p in score["parts"]}
    assert parts["debt_per_sqm_total_area"]["part_score"] == 100
    assert parts["debt_per_sqm_total_area"]["value"] == 4_000
    assert parts["debt_per_sqm_total_area"]["weight"] == 25
    assert parts["debt_per_sqm_total_area"]["effective_weight"] == pytest.approx(25 / 75)
    assert parts["debt_per_sqm_total_area"]["fiscal_year"] == 2025
    assert parts["debt_per_sqm_total_area"]["label"] == "Skuldsättning per kvm totalyta"
    assert parts["debt_per_sqm_total_area"]["weight_reason"]
    assert parts["debt_per_sqm_total_area"]["rule"]
    assert parts["savings_per_sqm"]["part_score"] == 0
    assert {m["key"]: m["reason"] for m in score["missing"]} == {
        "fee_share_of_revenue_pct": "Saknas för räkenskapsår 2025.",
        "interest_coverage_ratio": "Saknas för räkenskapsår 2025.",
    }
    assert score["rule"]


def test_conflicting_key_figure_is_a_missing_part_of_the_score(client):
    # Two reports for the same year disagree on the debt per m², so it is left out of the score.
    first = upload(client, make_report_pdf()).json()
    upload(client, make_report_pdf(key_figures=[("Skuldsättning, kr/kvm", "4 600", "4 200"),
                                                ("Sparande, kr/kvm", "90", "120"),
                                                ("Räntekänslighet, %", "12", "11")]), "andra.pdf")
    score = client.get(f"/api/cooperatives/{first['cooperative_id']}").json()["score"]
    assert "debt_per_sqm_total_area" not in {p["key"] for p in score["parts"]}
    assert {m["key"]: m["reason"] for m in score["missing"]}["debt_per_sqm_total_area"] == (
        "Motstridiga uppgifter för räkenskapsår 2025.")


# Expected scores worked out by hand from the printed key figures, the rules and the weights in
# config/risk_rules.toml (weights: debt 25, sensitivity 20, savings 20, coverage 15, fee share 10, short-term 10).
SAMPLE_SCORES = {
    # Debt 1 443 → 100; sensitivity 2 % → 100; savings 151 → (151-100)/(200-100) = 51; interest coverage
    # 1.52 → (1.52-1.2)/(2-1.2) ≈ 40; short-term debt 100 % → 0; fee share missing (weight 90 of 100).
    # (2500 + 2000 + 1020 + 603 + 0) / 90 = 68.0 → 68.
    "702002-3532_arsredovisning.pdf": 68,
    # Savings 122 → 22, everything else 100: (2500 + 2000 + 440 + 1500 + 1000 + 1000) / 100 = 84.4 → 84.
    "byamannen2_arsredovisning_2025.pdf": 84,
    # Short-term debt 33.3 % → (60-33.3)/(60-30) ≈ 89, everything else 100: (9000 + 891) / 100 = 98.9 → 99.
    "segelflygaren_arsredovisning.pdf": 99,
}


@pytest.mark.parametrize(("filename", "expected"), SAMPLE_SCORES.items())
def test_score_of_real_reports(client, filename, expected):
    path = SAMPLES / filename
    if not path.exists():
        pytest.skip("Sample document not downloaded")
    cooperative_id = upload(client, path.read_bytes(), path.name).json()["cooperative_id"]
    assert client.get(f"/api/cooperatives/{cooperative_id}").json()["score"]["score"] == expected


def test_value_that_disagrees_with_our_calculation_is_a_missing_part(client):
    # A manual total area of 5 000 m² gives a calculated debt per m² of 8 000, which disagrees with the
    # printed 4 000: the value stays visible but is "conflicting", so the score leaves it out.
    # Remaining: savings 0 (20), sensitivity 0 (20), short-term debt 100 (10): 1000 / 50 = 20, at 50 % of the weight.
    cooperative_id = upload(client, make_report_pdf()).json()["cooperative_id"]
    client.post(f"/api/cooperatives/{cooperative_id}/observations",
                json={"metric_key": "total_area", "fiscal_year": 2025, "value": 5_000})
    score = client.get(f"/api/cooperatives/{cooperative_id}").json()["score"]
    assert "debt_per_sqm_total_area" not in {p["key"] for p in score["parts"]}
    assert {m["key"]: m["reason"] for m in score["missing"]}["debt_per_sqm_total_area"] == (
        "Motstridiga uppgifter för räkenskapsår 2025.")
    assert score["score"] == 20


def test_score_parts_carry_their_sources(client):
    cooperative_id = upload(client, make_report_pdf()).json()["cooperative_id"]
    parts = {p["key"]: p for p in client.get(f"/api/cooperatives/{cooperative_id}").json()["score"]["parts"]}
    debt = parts["debt_per_sqm_total_area"]  # Printed in the report's key figures.
    assert debt["sources"] and debt["sources"][0]["page"] and debt["sources"][0]["printed_label"]
    assert debt["formula"] is None
    short_term = parts["short_term_debt_share_pct"]  # Calculated by Boster from two balance sheet rows.
    assert short_term["sources"] == []
    assert short_term["formula"]
