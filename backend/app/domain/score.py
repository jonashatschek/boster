"""A 0–100 score for a cooperative, always computed together with its explanation.

Each rule-rated key figure gets a part score on a gradual scale between the same two
thresholds that give its "Låg / Måttlig / Hög risk" label: 100 on the good side of the
low-concern limit, 0 at or beyond the high-concern limit, linear in between. The score is
the weighted average of the parts that have a value. A missing part is left out and the
other weights are scaled up proportionally; no value is ever invented for it. Below a
minimum coverage there is no score. The weights live in ``config/risk_rules.toml``.

The score summarises documented rules of thumb. It is not a credit rating.
"""

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # Imported for type hints only; risk.py imports this module.
    from app.domain.risk import IndicatorRule, RiskRules


@dataclass(frozen=True)
class ScoreWeight:
    metric_key: str
    weight: float
    reason: str  # Shown to the user next to the weight.


@dataclass(frozen=True)
class ScoreRules:
    weights: dict[str, ScoreWeight]
    min_key_figures: int  # At least this many parts must have a value.
    min_weight_share: float  # ... and together carry at least this share of the total weight.

    def describe(self) -> str:
        return (f"Viktat medelvärde av delarna som har ett värde. Saknade delar räknas inte, och de övriga "
                f"väger då tyngre. Poäng ges bara om minst {self.min_key_figures} nyckeltal finns och de "
                f"tillsammans väger minst {self.min_weight_share * 100:.0f} % av den totala vikten.")


@dataclass(frozen=True)
class ScoredPart:
    metric_key: str
    value: float
    part_score: float  # 0–100.
    weight: float  # As configured.
    effective_weight: float  # Share of the weight among the parts that have a value; they sum to 1.


@dataclass(frozen=True)
class ScoreResult:
    score: int | None  # None below the minimum coverage.
    parts: list[ScoredPart]  # In the configured order.
    missing: list[str]  # Metric keys without a value, in the configured order.
    weight_share: float  # Share of the total configured weight that the parts with a value carry.


def part_score(rule: "IndicatorRule", value: float) -> float:
    """0–100 on a gradual scale between the rule's low- and high-concern limits."""
    good, bad = rule.low_concern_until, rule.high_concern_from
    # Multiply before dividing, so values on round steps (e.g. 54.5) come out exact.
    return min(100.0, max(0.0, 100 * (bad - value) / (bad - good)))


def compute_score(values: dict[str, float | None], rules: "RiskRules") -> ScoreResult:
    """`values` holds each key figure's value for the compared year; None (or absent) means missing."""
    score_rules = rules.score
    total_weight = sum(w.weight for w in score_rules.weights.values())
    present = {key: values[key] for key in score_rules.weights if values.get(key) is not None}
    present_weight = sum(score_rules.weights[key].weight for key in present)

    parts = [
        ScoredPart(key, value, part_score(rules.indicators[key], value), score_rules.weights[key].weight,
                   score_rules.weights[key].weight / present_weight)
        for key, value in present.items()
    ]
    missing = [key for key in score_rules.weights if key not in present]
    weight_share = present_weight / total_weight if total_weight else 0.0

    enough = len(parts) >= score_rules.min_key_figures and weight_share >= score_rules.min_weight_share - 1e-9
    score = _round_half_up(sum(p.part_score * p.effective_weight for p in parts)) if enough and parts else None
    return ScoreResult(score, parts, missing, weight_share)


def load_score_rules(raw: dict, indicator_keys: set[str]) -> ScoreRules:
    weights = {}
    for key, settings in raw.get("weights", {}).items():
        if key not in indicator_keys:
            raise ValueError(f"Score weight for {key}, which has no indicator rule")
        weight = float(settings["weight"])
        if weight <= 0:
            raise ValueError(f"Score weight for {key} must be positive, got {weight:g}")
        weights[key] = ScoreWeight(key, weight, settings["reason"])
    return ScoreRules(weights, int(raw["min_key_figures"]), float(raw["min_weight_share"]))


def _round_half_up(value: float) -> int:
    # Round off float noise first, so 54.49999999999999 counts as 54.5.
    return math.floor(round(value, 9) + 0.5)
