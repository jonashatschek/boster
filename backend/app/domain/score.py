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


LAND_TENURE_PART = "land_tenure"


@dataclass(frozen=True)
class LandTenureRule:
    """Land tenure as a part of the score: a fixed part score for owned land and for leasehold."""

    weight: float
    reason: str
    owned: float  # Part score for owned land.
    leasehold: float  # Part score for leasehold (tomträtt).

    def part_score(self, tenure: str | None) -> float | None:
        return {"owned": self.owned, "leasehold": self.leasehold}.get(tenure or "")

    def describe(self) -> str:
        return (f"{self.owned:g} poäng med äganderätt till marken, {self.leasehold:g} poäng med tomträtt. "
                f"Okänt räknas inte.")


@dataclass(frozen=True)
class ScoreRules:
    weights: dict[str, ScoreWeight]  # The rule-rated key figures.
    min_key_figures: int  # At least this many key figures must have a value (land tenure does not count).
    min_weight_share: float  # ... and all parts with a value together carry at least this share of the weight.
    land_tenure: LandTenureRule | None = None

    def describe(self) -> str:
        return (f"Viktat medelvärde av delarna som har ett värde. Saknade delar räknas inte, och de övriga "
                f"väger då tyngre. Poäng ges bara om minst {self.min_key_figures} nyckeltal finns och de "
                f"tillsammans väger minst {self.min_weight_share * 100:.0f} % av den totala vikten.")


@dataclass(frozen=True)
class ScoredPart:
    metric_key: str
    value: float | str  # A key figure's value, or the land tenure ("owned", "leasehold").
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


def compute_score(values: dict[str, float | None], rules: "RiskRules", land_tenure: str | None = None) -> ScoreResult:
    """`values` holds each key figure's value for the compared year; None (or absent) means missing.

    `land_tenure` ("owned", "leasehold" or None for unknown) is a part when the rules have a land tenure rule.
    """
    score_rules, land = rules.score, rules.score.land_tenure
    # (key, value, part score, weight) for every configured part; part score None means missing.
    candidates = [
        (key, values.get(key), part_score(rules.indicators[key], values[key]) if values.get(key) is not None else None,
         weight.weight)
        for key, weight in score_rules.weights.items()
    ]
    if land is not None:
        candidates.append((LAND_TENURE_PART, land_tenure, land.part_score(land_tenure), land.weight))

    total_weight = sum(weight for *_, weight in candidates)
    present = [c for c in candidates if c[2] is not None]
    present_weight = sum(weight for *_, weight in present)
    parts = [ScoredPart(key, value, score, weight, weight / present_weight) for key, value, score, weight in present]
    missing = [key for key, _, score, _ in candidates if score is None]
    weight_share = present_weight / total_weight if total_weight else 0.0

    key_figures = sum(1 for part in parts if part.metric_key in score_rules.weights)
    enough = key_figures >= score_rules.min_key_figures and weight_share >= score_rules.min_weight_share - 1e-9
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
    land = None
    if "land_tenure" in raw:
        settings = raw["land_tenure"]
        land = LandTenureRule(float(settings["weight"]), settings["reason"], float(settings["owned"]),
                              float(settings["leasehold"]))
        if land.weight <= 0:
            raise ValueError(f"Score weight for land tenure must be positive, got {land.weight:g}")
    return ScoreRules(weights, int(raw["min_key_figures"]), float(raw["min_weight_share"]), land)


def _round_half_up(value: float) -> int:
    # Round off float noise first, so 54.49999999999999 counts as 54.5.
    return math.floor(round(value, 9) + 0.5)
