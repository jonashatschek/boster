"""The 0–100 cooperative score: gradual part scores, weights, re-weighting and minimum coverage."""

from pathlib import Path

import pytest

from app.domain.risk import IndicatorRule, RiskRules, load_risk_rules
from app.domain.score import ScoreRules, ScoreWeight, compute_score, part_score

CONFIG_PATH = Path(__file__).parents[1] / "config" / "risk_rules.toml"

DEBT = IndicatorRule("debt_per_sqm_total_area", True, 5_000, 10_000, "")
SAVINGS = IndicatorRule("savings_per_sqm", False, 200, 100, "")
SENSITIVITY = IndicatorRule("interest_sensitivity_pct", True, 5, 10, "")
COVERAGE = IndicatorRule("interest_coverage_ratio", False, 2, 1.2, "")


def rules(weights, min_key_figures=3, min_weight_share=0.5):
    indicators = {rule.metric_key: rule for rule in (DEBT, SAVINGS, SENSITIVITY, COVERAGE)}
    return RiskRules(indicators, ScoreRules(
        {key: ScoreWeight(key, weight, "") for key, weight in weights.items()}, min_key_figures, min_weight_share))


WEIGHTS = {"debt_per_sqm_total_area": 40, "savings_per_sqm": 30, "interest_sensitivity_pct": 20,
           "interest_coverage_ratio": 10}


@pytest.mark.parametrize(("value", "expected"), [
    (1_747, 100), (5_000, 100),  # On the good side of the low-concern limit.
    (6_000, 80), (7_500, 50), (9_999, pytest.approx(0.02)),  # Linear in between.
    (10_000, 0), (25_000, 0),  # At or beyond the high-concern limit.
])
def test_part_score_when_higher_is_worse(value, expected):
    assert part_score(DEBT, value) == expected


@pytest.mark.parametrize(("value", "expected"), [
    (300, 100), (200, 100), (150, 50), (120, 20), (100, 0), (-300, 0),
])
def test_part_score_when_lower_is_worse(value, expected):
    assert part_score(SAVINGS, value) == expected


def test_score_is_the_weighted_average_of_the_parts():
    # Part scores 80, 50, 100 and 0 with weights 40, 30, 20, 10: (3200 + 1500 + 2000 + 0) / 100 = 67.
    result = compute_score({"debt_per_sqm_total_area": 6_000, "savings_per_sqm": 150,
                            "interest_sensitivity_pct": 3, "interest_coverage_ratio": 1.0}, rules(WEIGHTS))
    assert result.score == 67
    assert result.weight_share == 1
    assert result.missing == []
    assert {p.metric_key: (p.part_score, p.effective_weight) for p in result.parts} == {
        "debt_per_sqm_total_area": (80, 0.4), "savings_per_sqm": (50, 0.3),
        "interest_sensitivity_pct": (100, 0.2), "interest_coverage_ratio": (0, pytest.approx(0.1)),
    }


def test_missing_part_is_left_out_and_the_others_weigh_more():
    # Coverage missing: weights 40, 30, 20 scale to 4/9, 3/9, 2/9; (80*40 + 50*30 + 100*20) / 90 = 74.4 → 74.
    result = compute_score({"debt_per_sqm_total_area": 6_000, "savings_per_sqm": 150,
                            "interest_sensitivity_pct": 3, "interest_coverage_ratio": None}, rules(WEIGHTS))
    assert result.score == 74
    assert result.missing == ["interest_coverage_ratio"]
    assert result.weight_share == pytest.approx(0.9)
    assert sum(p.effective_weight for p in result.parts) == pytest.approx(1)
    assert [p.metric_key for p in result.parts] == ["debt_per_sqm_total_area", "savings_per_sqm",
                                                     "interest_sensitivity_pct"]


def test_missing_counts_neither_as_good_nor_as_bad():
    # Adding a missing part changes nothing; filling it with its best or worst value does.
    base = {"debt_per_sqm_total_area": 6_000, "savings_per_sqm": 150, "interest_sensitivity_pct": 3}
    without = compute_score(base, rules(WEIGHTS)).score
    assert compute_score({**base, "interest_coverage_ratio": None}, rules(WEIGHTS)).score == without
    assert compute_score({**base, "interest_coverage_ratio": 5}, rules(WEIGHTS)).score > without
    assert compute_score({**base, "interest_coverage_ratio": 0.5}, rules(WEIGHTS)).score < without


def test_too_few_key_figures_gives_no_score():
    # Two key figures carry 70 % of the weight, but at least three are required.
    result = compute_score({"debt_per_sqm_total_area": 6_000, "savings_per_sqm": 150}, rules(WEIGHTS))
    assert result.score is None
    assert result.missing == ["interest_sensitivity_pct", "interest_coverage_ratio"]


def test_too_little_weight_gives_no_score():
    # Three key figures, but only 40 % of the weight (10 + 20 + 10 of 100 with these weights).
    weights = {"debt_per_sqm_total_area": 60, "savings_per_sqm": 10, "interest_sensitivity_pct": 20,
               "interest_coverage_ratio": 10}
    result = compute_score({"savings_per_sqm": 150, "interest_sensitivity_pct": 3, "interest_coverage_ratio": 1.0},
                           rules(weights))
    assert result.score is None
    assert result.weight_share == pytest.approx(0.4)


def test_exactly_the_minimum_coverage_gives_a_score():
    weights = {"debt_per_sqm_total_area": 50, "savings_per_sqm": 20, "interest_sensitivity_pct": 20,
               "interest_coverage_ratio": 10}
    result = compute_score({"savings_per_sqm": 150, "interest_sensitivity_pct": 3, "interest_coverage_ratio": 1.0},
                           rules(weights))
    assert result.weight_share == pytest.approx(0.5)
    assert result.score is not None


def test_score_rounds_half_up():
    # One part: 7 250 kr/m² gives exactly 55.0; 7 275 gives 54.5, which rounds up to 55.
    weights = {"debt_per_sqm_total_area": 1}
    assert compute_score({"debt_per_sqm_total_area": 7_275}, rules(weights, min_key_figures=1)).score == 55


def test_shipped_configuration_has_score_weights_for_rule_rated_indicators():
    loaded = load_risk_rules(CONFIG_PATH)
    assert loaded.score is not None
    assert set(loaded.score.weights) <= set(loaded.indicators)
    assert all(weight.weight > 0 and weight.reason for weight in loaded.score.weights.values())
    assert loaded.score.min_key_figures == 3
    assert loaded.score.min_weight_share == 0.5


def _config_with_score(tmp_path, score_section):
    text = CONFIG_PATH.read_text(encoding="utf-8").split("[score]")[0] + score_section
    path = tmp_path / "rules.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_weight_for_an_unknown_indicator_is_rejected(tmp_path):
    path = _config_with_score(tmp_path, "[score]\nmin_key_figures = 3\nmin_weight_share = 0.5\n"
                                        "[score.weights.not_an_indicator]\nweight = 10\nreason = \"x\"\n")
    with pytest.raises(ValueError, match="not_an_indicator"):
        load_risk_rules(path)


def test_negative_weight_is_rejected(tmp_path):
    path = _config_with_score(tmp_path, "[score]\nmin_key_figures = 3\nmin_weight_share = 0.5\n"
                                        "[score.weights.savings_per_sqm]\nweight = -1\nreason = \"x\"\n")
    with pytest.raises(ValueError, match="savings_per_sqm"):
        load_risk_rules(path)


def test_scale_rule_uses_swedish_numbers_and_units():
    from app.services.cooperatives import _scale_rule

    loaded = load_risk_rules(CONFIG_PATH)
    assert _scale_rule(loaded, "interest_coverage_ratio") == (
        "100 poäng vid 2 ggr eller högre, 0 poäng vid 1,2 ggr eller lägre, jämnt fördelat däremellan.")
    assert _scale_rule(loaded, "interest_sensitivity_pct") == (
        "100 poäng vid 5 % eller lägre, 0 poäng vid 10 % eller högre, jämnt fördelat däremellan.")
