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


# Land tenure as a part (#44): owned 100, leasehold 0, unknown missing. Its weight counts in the total and the
# weight share, but not toward the minimum number of key figures.
def rules_with_land(weights, land_weight=10, **kwargs):
    from app.domain.score import LandTenureRule

    base = rules(weights, **kwargs)
    return RiskRules(base.indicators, ScoreRules(base.score.weights, base.score.min_key_figures,
                                                 base.score.min_weight_share,
                                                 LandTenureRule(land_weight, "reason", owned=100, leasehold=0)))


KEY_FIGURES = {"debt_per_sqm_total_area": 6_000, "savings_per_sqm": 150, "interest_sensitivity_pct": 3,
               "interest_coverage_ratio": 1.0}  # Part scores 80, 50, 100, 0 with weights 40, 30, 20, 10: 67.


@pytest.mark.parametrize(("tenure", "expected", "land_score"), [
    # (3200 + 1500 + 2000 + 0 + 100·10) / 110 = 70.0 → 70.
    ("owned", 70, 100),
    # (3200 + 1500 + 2000 + 0 + 0·10) / 110 = 60.9 → 61.
    ("leasehold", 61, 0),
])
def test_land_tenure_is_a_part_of_the_score(tenure, expected, land_score):
    result = compute_score(KEY_FIGURES, rules_with_land(WEIGHTS), land_tenure=tenure)
    assert result.score == expected
    land = next(p for p in result.parts if p.metric_key == "land_tenure")
    assert (land.value, land.part_score, land.weight) == (tenure, land_score, 10)
    assert land.effective_weight == pytest.approx(10 / 110)
    assert result.weight_share == 1


def test_unknown_land_tenure_is_a_missing_part():
    result = compute_score(KEY_FIGURES, rules_with_land(WEIGHTS), land_tenure=None)
    assert result.score == 67  # Exactly as without land tenure: missing counts neither as good nor as bad.
    assert result.missing == ["land_tenure"]
    assert result.weight_share == pytest.approx(100 / 110)


def test_land_tenure_does_not_count_as_a_key_figure():
    # Two key figures plus known land tenure: still too few key figures for a score, although 80 % of the weight.
    result = compute_score({"debt_per_sqm_total_area": 6_000, "savings_per_sqm": 150},
                           rules_with_land(WEIGHTS), land_tenure="owned")
    assert result.score is None
    assert result.weight_share == pytest.approx(80 / 110)


def test_shipped_configuration_has_a_land_tenure_part():
    land = load_risk_rules(CONFIG_PATH).score.land_tenure
    assert (land.weight, land.owned, land.leasehold) == (10, 100, 0)
    assert land.reason


# Trends over time (#45): the change per year over the 3 latest years, all 3 needed. Debt per m² in % per year,
# savings per m² in kr/m² per year (savings can be negative, so a percentage would mean nothing).
def test_trend_change_in_percent_per_year():
    from app.domain.score import TrendRule

    debt = TrendRule("debt_per_sqm_total_area", "percent_per_year", best=-5, worst=5, years=3, weight=10, reason="")
    # Toppsockret: 956 → 1 443 over 2 years: (1443 - 956) / 956 / 2 = +25.47 % per year.
    assert debt.change([956, 948, 1_443]) == pytest.approx(25.47, abs=0.01)
    assert debt.change([3_307, 2_501, 1_747]) == pytest.approx(-23.59, abs=0.01)  # Byamännen 2: falling.


def test_trend_change_in_absolute_units_per_year_handles_a_negative_start():
    from app.domain.score import TrendRule

    savings = TrendRule("savings_per_sqm", "change_per_year", best=20, worst=-20, years=3, weight=10, reason="")
    assert savings.change([-300, 160, 122]) == pytest.approx(211)  # Byamännen 2: (122 - (-300)) / 2.
    assert savings.change([257, 215, 201]) == pytest.approx(-28)  # Friheten.


@pytest.mark.parametrize(("change", "expected"), [
    (-23.6, 100), (-5, 100),  # As good as the best limit or better.
    (-1.6, pytest.approx(66)), (0, 50),  # Linear in between.
    (5, 0), (25.5, 0),  # As bad as the worst limit or worse.
])
def test_trend_part_score_for_debt_where_falling_is_better(change, expected):
    from app.domain.score import TrendRule

    debt = TrendRule("debt_per_sqm_total_area", "percent_per_year", best=-5, worst=5, years=3, weight=10, reason="")
    assert debt.part_score(change) == expected


@pytest.mark.parametrize(("change", "expected"), [(211, 100), (20, 100), (0, 50), (-18, pytest.approx(5)), (-28, 0)])
def test_trend_part_score_for_savings_where_rising_is_better(change, expected):
    from app.domain.score import TrendRule

    savings = TrendRule("savings_per_sqm", "change_per_year", best=20, worst=-20, years=3, weight=10, reason="")
    assert savings.part_score(change) == expected


def rules_with_trends(weights, **kwargs):
    from app.domain.score import TrendRule

    base = rules(weights, **kwargs)
    trends = {"trend:debt_per_sqm_total_area": TrendRule("debt_per_sqm_total_area", "percent_per_year", -5, 5, 3, 10, "")}
    return RiskRules(base.indicators, ScoreRules(base.score.weights, base.score.min_key_figures,
                                                 base.score.min_weight_share, None, trends))


def test_trend_is_a_part_that_counts_in_the_weight_but_not_as_a_key_figure():
    # Key figures as before (67 over weight 100) plus a debt trend of 0 %/year → 50 points, weight 10:
    # (3200 + 1500 + 2000 + 0 + 500) / 110 = 7200 / 110 = 65.45 → 65.
    result = compute_score(KEY_FIGURES, rules_with_trends(WEIGHTS), trends={"trend:debt_per_sqm_total_area": 0})
    assert result.score == 65
    trend = next(p for p in result.parts if p.metric_key == "trend:debt_per_sqm_total_area")
    assert (trend.value, trend.part_score, trend.weight) == (0, 50, 10)

    missing = compute_score(KEY_FIGURES, rules_with_trends(WEIGHTS), trends={"trend:debt_per_sqm_total_area": None})
    assert missing.score == 67 and missing.missing == ["trend:debt_per_sqm_total_area"]

    two_figures = compute_score({"debt_per_sqm_total_area": 6_000, "savings_per_sqm": 150}, rules_with_trends(WEIGHTS),
                                trends={"trend:debt_per_sqm_total_area": 0})
    assert two_figures.score is None  # A trend never stands in for a key figure.


def test_shipped_configuration_has_two_trends():
    trends = load_risk_rules(CONFIG_PATH).score.trends
    assert set(trends) == {"trend:debt_per_sqm_total_area", "trend:savings_per_sqm"}
    debt, savings = trends["trend:debt_per_sqm_total_area"], trends["trend:savings_per_sqm"]
    assert (debt.measure, debt.best, debt.worst, debt.years, debt.weight) == ("percent_per_year", -5, 5, 3, 10)
    assert (savings.measure, savings.best, savings.worst, savings.years, savings.weight) == (
        "change_per_year", 20, -20, 3, 10)
    assert debt.reason and savings.reason


def test_minimum_coverage_counts_only_key_figures_and_land_not_trends():
    # Key figures 40 + 30 + 20 of 100 and owned land 10, trends (weight 10 each in this setup: one) missing.
    # Over all weight: 100 of 110 + 10 = 120 → but the minimum looks only at key figures and land: 100 of 110.
    from app.domain.score import LandTenureRule, TrendRule

    base = rules(WEIGHTS)
    trends = {f"trend:{key}": TrendRule(key, "change_per_year", 20, -20, 3, 60, "")
              for key in ("savings_per_sqm",)}
    score_rules = ScoreRules(base.score.weights, 3, 0.5, LandTenureRule(10, "", 100, 0), trends)
    result = compute_score({"debt_per_sqm_total_area": 6_000, "savings_per_sqm": 150, "interest_sensitivity_pct": 3},
                           RiskRules(base.indicators, score_rules), land_tenure="owned", trends={})
    # Present: 40 + 30 + 20 + 10 = 100 of all 170 (59 %), and of the 110 key-figure-and-land weight (91 %).
    assert result.weight_share == pytest.approx(100 / 170)
    assert result.score is not None
    # With a heavy missing trend the overall share drops below 50 %, but the score stays: history is a bonus.
    heavy = ScoreRules(base.score.weights, 3, 0.5, LandTenureRule(10, "", 100, 0),
                       {"trend:savings_per_sqm": TrendRule("savings_per_sqm", "change_per_year", 20, -20, 3, 200, "")})
    result = compute_score({"debt_per_sqm_total_area": 6_000, "savings_per_sqm": 150, "interest_sensitivity_pct": 3},
                           RiskRules(base.indicators, heavy), land_tenure="owned", trends={})
    assert result.weight_share == pytest.approx(100 / 310)
    assert result.score is not None


def test_core_weight_share_is_the_share_the_minimum_uses():
    from app.domain.score import LandTenureRule, TrendRule

    base = rules(WEIGHTS)
    score_rules = ScoreRules(base.score.weights, 3, 0.5, LandTenureRule(10, "", 100, 0),
                             {"trend:savings_per_sqm": TrendRule("savings_per_sqm", "change_per_year", 20, -20, 3, 20, "")})
    result = compute_score({"debt_per_sqm_total_area": 6_000, "savings_per_sqm": 150, "interest_sensitivity_pct": 3},
                           RiskRules(base.indicators, score_rules), land_tenure="owned", trends={})
    assert result.core_weight_share == pytest.approx(100 / 110)  # Key figures 90 + land 10 of 100 + 10.
    assert result.weight_share == pytest.approx(100 / 130)  # All weight, including the missing trend.


# Maintenance confirmed by the user (#46): per topic "coming up within five years?" Ja → 0, Nej → 100,
# Vet inte or no answer → missing. Counts in the score, not in the minimum coverage.
def _stambyte():
    from app.domain.score import MaintenanceRule

    return MaintenanceRule("stambyte", "Stambyte", "Stambyte", "Står föreningen inför stambyte de närmaste fem åren?",
                           yes=0, no=100, weight=5, reason="")


@pytest.mark.parametrize(("answer", "expected"), [("yes", 0), ("no", 100), ("unknown", None), (None, None)])
def test_maintenance_answer_part_score(answer, expected):
    assert _stambyte().part_score(answer) == expected


def test_maintenance_answer_is_a_part_that_does_not_count_toward_the_minimum():
    base = rules(WEIGHTS)
    rule = _stambyte()
    score_rules = ScoreRules(base.score.weights, 3, 0.5, None, {}, {rule.key: rule})
    # Key figures as before (6700 over weight 100) plus Ja (0 points, weight 5): 6700 / 105 = 63.8 → 64.
    result = compute_score(KEY_FIGURES, RiskRules(base.indicators, score_rules), maintenance={rule.key: "yes"})
    assert result.score == 64
    part = next(p for p in result.parts if p.metric_key == "maintenance:stambyte")
    assert (part.value, part.part_score, part.weight) == ("yes", 0, 5)
    unanswered = compute_score(KEY_FIGURES, RiskRules(base.indicators, score_rules), maintenance={})
    assert unanswered.score == 67 and unanswered.missing == ["maintenance:stambyte"]
    assert unanswered.core_weight_share == 1  # The missing answer does not lower the minimum's share.


def test_shipped_configuration_asks_about_stambyte_tak_and_fasad():
    maintenance = load_risk_rules(CONFIG_PATH).score.maintenance
    assert list(maintenance) == ["maintenance:stambyte", "maintenance:tak", "maintenance:fasad"]
    assert all((m.yes, m.no, m.weight) == (0, 100, 5) and m.question.endswith("de närmaste fem åren?") and m.reason
               for m in maintenance.values())
    assert [m.topic for m in maintenance.values()] == ["Stambyte", "Tak", "Fasad"]  # The report passages' topics.
