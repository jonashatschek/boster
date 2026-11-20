import pytest

from app.domain.kpis import FORMULAS, calculate_all, calculate_kpi, values_agree

FORMULAS_BY_KEY = {formula.metric_key: formula for formula in FORMULAS}


def test_every_formula_input_is_a_known_metric():
    # Missing inputs are shown to the user by their metric label, so each must be registered.
    from app.domain.kpis import TOTAL_AREA_FORMULA
    from app.domain.metrics import METRICS

    for formula in (*FORMULAS, TOTAL_AREA_FORMULA):
        assert set(formula.inputs) | set(formula.previous_year_inputs) <= METRICS.keys(), formula.metric_key

# Brf Friheten Bagarmossen, fiscal year 2024/2025, as printed in its annual report.
FRIHETEN_2025 = {
    "interest_bearing_debt": 32_000_000,
    "short_term_interest_bearing_debt": 7_000_000,
    "cash": 4_665_727,
    "total_area": 16_790,  # 15 575 m² residential + 1 215 m² commercial.
    "equity": 2_218_948,
    "total_assets": 36_271_487,
    "interest_expense": 907_048,
    "operating_result": 798_753,
    "depreciation": 1_291_480,
}
FRIHETEN_2024 = {"interest_bearing_debt": 32_512_276}


def calculate(metric_key, current, previous=None):
    return calculate_kpi(FORMULAS_BY_KEY[metric_key], current, previous)


def test_debt_per_sqm_matches_figure_printed_in_report():
    result = calculate("debt_per_sqm_total_area", FRIHETEN_2025)
    assert result.value == pytest.approx(1_906, abs=1)  # The report prints 1 906 kr/kvm.
    assert result.inputs == {"interest_bearing_debt": 32_000_000, "total_area": 16_790}
    assert result.missing_inputs == []


def test_net_debt():
    assert calculate("net_debt", FRIHETEN_2025).value == 32_000_000 - 4_665_727


def test_solidity_matches_figure_printed_in_report():
    assert calculate("solidity_pct", FRIHETEN_2025).value == pytest.approx(6.1, abs=0.1)  # Printed as 6 %.


def test_average_interest_rate_uses_debt_at_start_and_end_of_year():
    result = calculate("average_interest_rate_pct", FRIHETEN_2025, FRIHETEN_2024)
    assert result.value == pytest.approx(907_048 / ((32_512_276 + 32_000_000) / 2) * 100)
    assert result.inputs["previous:interest_bearing_debt"] == 32_512_276


def test_interest_coverage_ratio():
    result = calculate("interest_coverage_ratio", FRIHETEN_2025)
    assert result.value == pytest.approx((798_753 + 1_291_480) / 907_048)


def test_short_term_debt_share():
    assert calculate("short_term_debt_share_pct", FRIHETEN_2025).value == pytest.approx(21.875)


def test_missing_input_gives_no_value_and_names_the_input():
    result = calculate("debt_per_sqm_total_area", {"interest_bearing_debt": 32_000_000})
    assert result.value is None
    assert not result.is_available
    assert result.missing_inputs == ["total_area"]


def test_missing_previous_year_is_reported_separately():
    result = calculate("average_interest_rate_pct", FRIHETEN_2025, previous=None)
    assert result.value is None
    assert result.missing_inputs == ["previous:interest_bearing_debt"]


def test_zero_denominator_gives_no_value_and_explains_why():
    result = calculate("debt_per_sqm_total_area", {"interest_bearing_debt": 1_000, "total_area": 0})
    assert result.value is None
    assert result.missing_inputs == []
    assert "noll" in result.note


def test_zero_is_a_value_not_a_missing_input():
    # A debt-free cooperative has 0 kr debt per m², which is different from unknown debt.
    result = calculate("debt_per_sqm_total_area", {"interest_bearing_debt": 0, "total_area": 5_000})
    assert result.value == 0
    assert result.is_available


def test_calculate_all_returns_every_formula_even_with_no_data():
    results = calculate_all({})
    assert {r.metric_key for r in results} == set(FORMULAS_BY_KEY)
    assert all(r.value is None for r in results)


def test_total_area_is_derived_from_its_parts_when_not_reported():
    figures = {"interest_bearing_debt": 32_000_000, "residential_area": 15_575, "commercial_area": 1_215}
    results = {r.metric_key: r for r in calculate_all(figures)}
    assert results["total_area"].value == 16_790
    assert results["debt_per_sqm_total_area"].value == pytest.approx(1_906, abs=1)


def test_reported_total_area_is_not_overridden():
    figures = {"total_area": 9_380, "residential_area": 8_948, "commercial_area": 267}
    assert "total_area" not in {r.metric_key for r in calculate_all(figures)}


def test_calculations_are_deterministic():
    assert calculate_all(FRIHETEN_2025, FRIHETEN_2024) == calculate_all(FRIHETEN_2025, FRIHETEN_2024)


@pytest.mark.parametrize(
    ("reported", "calculated", "agree"),
    [
        (1_906, 1_905.9, True),  # Rounding.
        (3_613, 3_613.3, True),
        (-2_802_579, -2_802_580, True),  # Off by one krona.
        (15_407_000, 15_407_391, True),  # Thousands vs exact kronor.
        (1_747, 3_369, False),
        (26_688, 21_311, False),  # Two different areas in one report.
        (0, 0, True),
    ],
)
def test_values_agree_within_rounding_tolerance(reported, calculated, agree):
    assert values_agree(reported, calculated) is agree
