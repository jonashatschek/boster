"""Comparing cooperatives through the API."""

from pathlib import Path

import pytest

from tests.report_factory import DEFAULT_STATEMENTS, make_report_pdf
from tests.uploads import upload_pdf

SAMPLES = Path(__file__).parents[2] / "sample_documents"

LOW_DEBT_KEY_FIGURES = [
    ("Skuldsättning, kr/kvm", "2 000", "2 100"),
    ("Sparande, kr/kvm", "250", "240"),
    ("Räntekänslighet, %", "3", "3"),
    ("Energikostnad, kr/kvm", "200", "190"),
]


def add_cooperative(client, **report) -> int:
    content = make_report_pdf(**report)
    response = upload_pdf(client, content, "rapport.pdf")
    assert response.status_code == 201, response.text
    return response.json()["cooperative_id"]


def compare(client, *ids):
    return client.get("/api/comparisons/cooperatives", params={"ids": ",".join(map(str, ids))})


def row(comparison, key):
    return next(r for r in comparison["rows"] if r["key"] == key)


@pytest.fixture
def two_cooperatives(client):
    first = add_cooperative(client)  # Brf Provhuset: 4 000 kr/kvm, weak savings.
    second = add_cooperative(client, name="Brf Jämförelsen", organisation_number="769600-5678",
                             key_figures=LOW_DEBT_KEY_FIGURES)
    return first, second


def test_compares_latest_values_side_by_side(client, two_cooperatives):
    first, second = two_cooperatives
    comparison = compare(client, first, second).json()
    assert [c["name"] for c in comparison["cooperatives"]] == ["Brf Provhuset", "Brf Jämförelsen"]
    debt = row(comparison, "debt_per_sqm_total_area")
    assert [cell["value"] for cell in debt["cells"]] == [4_000, 2_000]
    assert all(cell["fiscal_year"] == 2025 for cell in debt["cells"])


def test_cells_carry_concern_levels_without_ranking(client, two_cooperatives):
    comparison = compare(client, *two_cooperatives).json()
    savings = row(comparison, "savings_per_sqm")
    assert [cell["level"] for cell in savings["cells"]] == ["high", "low"]
    assert "rank" not in savings["cells"][0]


def test_missing_value_is_missing_not_zero(client, two_cooperatives):
    comparison = compare(client, *two_cooperatives).json()
    energy = row(comparison, "energy_cost_per_sqm")  # Only the second report has it.
    first_cell, second_cell = energy["cells"]
    assert first_cell["value"] is None
    assert first_cell["status"] == "missing"
    assert second_cell["value"] == 200
    # The table shows "Saknas" for each missing value, so there is no separate banner about it.
    assert not any("saknar" in warning for warning in comparison["warnings"])


def test_core_metric_missing_for_every_cooperative_still_has_a_row(client, two_cooperatives):
    from app.services.cooperatives import CORE_METRICS

    comparison = compare(client, *two_cooperatives).json()
    rows = {r["key"]: r for r in comparison["rows"]}
    assert set(CORE_METRICS) <= rows.keys()
    missing_everywhere = [key for key in CORE_METRICS if all(c["value"] is None for c in rows[key]["cells"])]
    assert missing_everywhere, "the fixture should lack at least one core metric in both reports"
    for key in missing_everywhere:
        assert [c["status"] for c in rows[key]["cells"]] == ["missing", "missing"]


def test_rows_keep_their_denominator(client, two_cooperatives):
    comparison = compare(client, *two_cooperatives).json()
    debt = row(comparison, "debt_per_sqm_total_area")
    assert debt["area_basis"] == "total_area"
    assert "totalyta" in debt["note"]


def test_history_has_one_series_per_cooperative(client, two_cooperatives):
    first, second = two_cooperatives
    history = row(compare(client, first, second).json(), "debt_per_sqm_total_area")["history"]
    assert [p["value"] for p in history[str(first)]] == [4_200, 4_000]
    assert [p["fiscal_year"] for p in history[str(second)]] == [2024, 2025]


def test_default_rows_come_first(client, two_cooperatives):
    rows = compare(client, *two_cooperatives).json()["rows"]
    defaults = [r["is_default"] for r in rows]
    assert defaults == sorted(defaults, reverse=True)
    assert any(not d for d in defaults)  # Other figures remain available.


def test_warns_when_fiscal_years_differ(client):
    current = add_cooperative(client)
    older = add_cooperative(client, name="Brf Gammal", organisation_number="769600-9999",
                            period=("2024-01-01", "2024-12-31"), previous_period_end="2023-12-31")
    comparison = compare(client, current, older).json()
    assert [c["fiscal_year"] for c in comparison["cooperatives"]] == [2025, 2024]
    assert any("olika räkenskapsår" in warning for warning in comparison["warnings"])


def test_long_fiscal_year_flags_annual_amounts_but_not_ratios(client):
    normal = add_cooperative(client)
    extended = add_cooperative(client, name="Brf Lång", organisation_number="769600-4321",
                               period=("2024-09-01", "2025-12-31"), previous_period_end="2024-08-31",
                               statements=DEFAULT_STATEMENTS)
    comparison = compare(client, normal, extended).json()
    assert comparison["cooperatives"][1]["period_months"] == 16
    assert any("16 månader" in warning for warning in comparison["warnings"])
    interest = row(comparison, "interest_expense")["cells"][1]
    assert "16 månader" in interest["warning"]
    debt_per_sqm = row(comparison, "debt_per_sqm_total_area")["cells"][1]
    assert debt_per_sqm["warning"] is None


@pytest.mark.parametrize("ids", ["1", "1,2,3,4,5", "", "a,b"])
def test_rejects_invalid_selection(client, ids):
    assert client.get("/api/comparisons/cooperatives", params={"ids": ids}).status_code == 422


def test_invalid_id_is_reported_not_dropped(client, two_cooperatives):
    # The comparison page passes the ids exactly as written in the URL and shows this message.
    response = client.get("/api/comparisons/cooperatives", params={"ids": f"{two_cooperatives[0]},abc"})
    assert response.status_code == 422
    assert response.json()["detail"] == "Ogiltiga förenings-id."


@pytest.mark.parametrize("invalid_id", ["-1", "0"])
def test_id_of_zero_or_below_is_invalid_not_unknown(client, two_cooperatives, invalid_id):
    # Ids are always positive, so these get the malformed-id answer, not "Föreningen -1 finns inte."
    response = client.get("/api/comparisons/cooperatives", params={"ids": f"{invalid_id},{two_cooperatives[1]}"})
    assert response.status_code == 422
    assert response.json()["detail"] == "Ogiltiga förenings-id."


def test_spaces_around_ids_are_accepted(client, two_cooperatives):
    first, second = two_cooperatives
    response = client.get("/api/comparisons/cooperatives", params={"ids": f" {first} , {second} "})
    assert response.status_code == 200
    assert len(response.json()["cooperatives"]) == 2


def test_unknown_cooperative_is_not_found(client, two_cooperatives):
    assert compare(client, two_cooperatives[0], 999).status_code == 404


def test_duplicate_ids_are_ignored(client, two_cooperatives):
    first, second = two_cooperatives
    comparison = compare(client, first, second, first).json()
    assert len(comparison["cooperatives"]) == 2


def test_real_reports(client):
    paths = [SAMPLES / "soderbysjon_arsredovisning.pdf", SAMPLES / "friheten_arsredovisning_2024-2025.pdf"]
    if not all(path.exists() for path in paths):
        pytest.skip("Sample documents not downloaded")
    ids = [upload_pdf(client, p.read_bytes(), p.name)
           .json()["cooperative_id"] for p in paths]
    comparison = compare(client, *ids).json()
    assert [c["value"] for c in row(comparison, "debt_per_sqm_total_area")["cells"]] == [3_613, 1_906]
    assert any("16 månader" in warning for warning in comparison["warnings"])
