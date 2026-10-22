"""End-to-end tests through the HTTP API: upload a report, read the analysis, correct values."""

from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

SAMPLES = Path(__file__).parents[2] / "sample_documents"


@pytest.fixture
def client(tmp_path):
    settings = Settings(data_directory=tmp_path, trafiklab_api_key=None, anthropic_api_key=None)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def make_report_pdf() -> bytes:
    """A small but real PDF laid out like an annual report."""
    document = pymupdf.open()
    cover = document.new_page()
    cover.insert_text((60, 80), "Årsredovisning för Brf Provhuset", fontsize=12)
    cover.insert_text((60, 100), "769600-1234", fontsize=10)
    cover.insert_text((60, 120), "Räkenskapsåret 2025-01-01 - 2025-12-31", fontsize=10)
    cover.insert_text((60, 140), "Fastigheten innehas med tomträtt.", fontsize=10)

    def table(page, y, rows):
        for label, *values in rows:
            page.insert_text((60, y), label, fontsize=9)
            for x_right, value in zip((360, 430), values):
                page.insert_text((x_right - len(value) * 4.6, y), value, fontsize=9)
            y += 14

    key_figures = document.new_page()
    key_figures.insert_text((60, 60), "Flerårsöversikt", fontsize=11)
    table(key_figures, 80, [
        ("", "2025", "2024"),
        ("Skuldsättning, kr/kvm", "4 000", "4 200"),
        ("Sparande, kr/kvm", "90", "120"),
        ("Räntekänslighet, %", "12", "11"),
    ])
    statements = document.new_page()
    statements.insert_text((60, 60), "Resultaträkning och balansräkning", fontsize=11)
    table(statements, 80, [
        ("", "2025-12-31", "2024-12-31"),
        ("Nettoomsättning", "5 000 000", "4 800 000"),
        ("Rörelseresultat", "900 000", "800 000"),
        ("Räntekostnader och liknande resultatposter", "-700 000", "-600 000"),
        ("Årets resultat", "200 000", "200 000"),
        ("Kassa och bank", "1 000 000", "900 000"),
        ("Summa tillgångar", "90 000 000", "91 000 000"),
        ("Summa eget kapital", "50 000 000", "49 800 000"),
        ("Långfristiga skulder", "", ""),
        ("Skulder till kreditinstitut", "40 000 000", "41 000 000"),
    ])
    content = document.tobytes()
    document.close()
    return content


def upload(client, content, filename="arsredovisning.pdf"):
    return client.post("/api/documents/upload", files={"file": (filename, content, "application/pdf")})


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


def test_rejects_urls_to_local_network(client):
    response = client.post("/api/documents/from-url", json={"url": "http://127.0.0.1:8000/secret.pdf"})
    assert response.status_code == 422
    assert "lokala" in response.json()["detail"]


def test_document_file_is_served_inline(client):
    document = upload(client, make_report_pdf()).json()
    response = client.get(f"/api/documents/{document['id']}/file")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline")


def test_deleting_cooperative_removes_documents_and_files(client, tmp_path):
    document = upload(client, make_report_pdf()).json()
    assert list((tmp_path / "documents").glob("*.pdf"))
    assert client.delete(f"/api/cooperatives/{document['cooperative_id']}").status_code == 204
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
