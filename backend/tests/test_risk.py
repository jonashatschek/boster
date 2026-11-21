from pathlib import Path

import pytest

from app.domain.metrics import METRICS
from app.domain.risk import ConcernLevel, IndicatorRule, load_risk_rules

CONFIG_PATH = Path(__file__).parents[1] / "config" / "risk_rules.toml"

LOW, MODERATE, HIGH, UNKNOWN = (ConcernLevel.LOW, ConcernLevel.MODERATE, ConcernLevel.HIGH,
                                ConcernLevel.INSUFFICIENT_INFORMATION)

DEBT_RULE = IndicatorRule("debt_per_sqm_total_area", True, 5_000, 10_000, "")
SAVINGS_RULE = IndicatorRule("savings_per_sqm", False, 200, 100, "")


@pytest.mark.parametrize(
    ("value", "level"),
    [(1_747, LOW), (4_999, LOW), (5_000, MODERATE), (9_999, MODERATE), (10_000, HIGH), (25_000, HIGH), (None, UNKNOWN)],
)
def test_higher_is_worse_thresholds(value, level):
    assert DEBT_RULE.assess(value) == level


@pytest.mark.parametrize(
    ("value", "level"),
    [(277, LOW), (200, LOW), (199, MODERATE), (100, MODERATE), (99, HIGH), (-300, HIGH), (None, UNKNOWN)],
)
def test_lower_is_worse_thresholds(value, level):
    assert SAVINGS_RULE.assess(value) == level


def test_shipped_configuration_loads_and_only_references_known_metrics():
    rules = load_risk_rules(CONFIG_PATH)
    assert rules.indicators
    assert set(rules.indicators) <= set(METRICS)
    for rule in rules.indicators.values():
        assert rule.rationale
        if rule.higher_is_worse:
            assert rule.low_concern_until <= rule.high_concern_from
        else:
            assert rule.low_concern_until >= rule.high_concern_from


def test_invalid_direction_is_rejected(tmp_path):
    config = tmp_path / "rules.toml"
    config.write_text(
        '[indicators.savings_per_sqm]\ndirection = "sideways"\nlow_concern_until = 1\nhigh_concern_from = 2\n'
        'rationale = "x"\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sideways"):
        load_risk_rules(config)


def test_shipped_configuration_has_no_overall_rule():
    # The 0–100 score (its weights and minimum coverage) replaced the old overall rating.
    assert "[overall]" not in CONFIG_PATH.read_text(encoding="utf-8")
    assert not hasattr(load_risk_rules(CONFIG_PATH), "overall")
