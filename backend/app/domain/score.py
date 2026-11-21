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
from dataclasses import dataclass, field
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


TREND_PREFIX = "trend:"
TREND_MEASURES = ("percent_per_year", "change_per_year")


@dataclass(frozen=True)
class TrendRule:
    """A key figure's development over its latest `years` fiscal years, as a part of the score.

    The change per year runs from the first to the last of those years: in percent of the first value
    ("percent_per_year"), or in the figure's own unit ("change_per_year", for figures that can be negative,
    such as savings). It gets 100 points at `best` or better, 0 at `worst` or worse, linear in between.
    """

    metric_key: str
    measure: str
    best: float
    worst: float
    years: int
    weight: float
    reason: str

    @property
    def key(self) -> str:
        return f"{TREND_PREFIX}{self.metric_key}"

    def change(self, values: list[float]) -> float | None:
        """The change per year over `values` (oldest first, one per year, no gaps); None if not defined."""
        first, last, span = values[0], values[-1], len(values) - 1
        if self.measure == "percent_per_year":
            if first <= 0:
                return None  # A percentage of zero or a negative start means nothing.
            return 100 * (last - first) / first / span
        return (last - first) / span

    def part_score(self, change: float) -> float:
        # Multiply before dividing, as for the key figures, so round steps come out exact.
        return min(100.0, max(0.0, 100 * (self.worst - change) / (self.worst - self.best)))

    def describe(self, unit: str) -> str:
        shown = "%" if self.measure == "percent_per_year" else unit
        return (f"Förändring per år över de {self.years} senaste åren: 100 poäng vid {_number(self.best)} {shown} "
                f"per år, 0 poäng vid {_number(self.worst)} {shown} per år, jämnt fördelat däremellan. Alla "
                f"{self.years} år behövs.")


@dataclass(frozen=True)
class ScoreRules:
    weights: dict[str, ScoreWeight]  # The rule-rated key figures.
    min_key_figures: int  # At least this many key figures must have a value (land tenure does not count).
    min_weight_share: float  # ... and with the land tenure carry this share of their weight (trends not counted).
    land_tenure: LandTenureRule | None = None
    trends: dict[str, TrendRule] = field(default_factory=dict)  # By part key, "trend:<metric>".

    def describe(self) -> str:
        return (f"Viktat medelvärde av delarna som har ett värde. Saknade delar räknas inte, och de övriga "
                f"väger då tyngre. Poäng ges bara om minst {self.min_key_figures} nyckeltal finns och nyckeltalen "
                f"och marken som finns tillsammans väger minst {self.min_weight_share * 100:.0f} % av sin vikt. "
                f"Trenderna räknas med när de finns, men avgör inte om poäng ges.")


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
    core_weight_share: float = 0.0  # The same over key figures and land tenure only: what the minimum uses.


def part_score(rule: "IndicatorRule", value: float) -> float:
    """0–100 on a gradual scale between the rule's low- and high-concern limits."""
    good, bad = rule.low_concern_until, rule.high_concern_from
    # Multiply before dividing, so values on round steps (e.g. 54.5) come out exact.
    return min(100.0, max(0.0, 100 * (bad - value) / (bad - good)))


def compute_score(values: dict[str, float | None], rules: "RiskRules", land_tenure: str | None = None,
                  trends: dict[str, float | None] | None = None) -> ScoreResult:
    """`values` holds each key figure's value for the compared year; None (or absent) means missing.

    `trends` holds each trend's change per year by part key (None means missing), and `land_tenure`
    ("owned", "leasehold" or None for unknown) is a part when the rules have a land tenure rule.
    """
    score_rules, land = rules.score, rules.score.land_tenure
    # (key, value, part score, weight) for every configured part; part score None means missing.
    candidates = [
        (key, values.get(key), part_score(rules.indicators[key], values[key]) if values.get(key) is not None else None,
         weight.weight)
        for key, weight in score_rules.weights.items()
    ]
    for key, trend in score_rules.trends.items():
        change = (trends or {}).get(key)
        candidates.append((key, change, trend.part_score(change) if change is not None else None, trend.weight))
    if land is not None:
        candidates.append((LAND_TENURE_PART, land_tenure, land.part_score(land_tenure), land.weight))

    total_weight = sum(weight for *_, weight in candidates)
    present = [c for c in candidates if c[2] is not None]
    present_weight = sum(weight for *_, weight in present)
    parts = [ScoredPart(key, value, score, weight, weight / present_weight) for key, value, score, weight in present]
    missing = [key for key, _, score, _ in candidates if score is None]
    weight_share = present_weight / total_weight if total_weight else 0.0

    key_figures = sum(1 for part in parts if part.metric_key in score_rules.weights)
    # The minimum is about enough current data: it counts the key figures and the land tenure, not the trends, so a
    # missing history (e.g. only one report uploaded) adds nothing but never blocks a score.
    core = [c for c in candidates if not c[0].startswith(TREND_PREFIX)]
    core_total = sum(weight for *_, weight in core)
    core_share = sum(weight for _, _, score, weight in core if score is not None) / core_total if core_total else 0.0
    enough = key_figures >= score_rules.min_key_figures and core_share >= score_rules.min_weight_share - 1e-9
    score = _round_half_up(sum(p.part_score * p.effective_weight for p in parts)) if enough and parts else None
    return ScoreResult(score, parts, missing, weight_share, core_share)


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
    trends = {}
    for metric_key, settings in raw.get("trends", {}).items():
        if metric_key not in indicator_keys:
            raise ValueError(f"Score trend for {metric_key}, which has no indicator rule")
        trend = TrendRule(metric_key, settings["measure"], float(settings["best"]), float(settings["worst"]),
                          int(settings["years"]), float(settings["weight"]), settings["reason"])
        if trend.measure not in TREND_MEASURES or trend.years < 2 or trend.weight <= 0 or trend.best == trend.worst:
            raise ValueError(f"Invalid score trend for {metric_key}")
        trends[trend.key] = trend
    return ScoreRules(weights, int(raw["min_key_figures"]), float(raw["min_weight_share"]), land, trends)


def _number(value: float) -> str:
    """Swedish format for a rule limit: "−5", "20", "1,5"."""
    text = f"{value:g}".replace(".", ",")
    return text.replace("-", "−") if value < 0 else text


def _round_half_up(value: float) -> int:
    # Round off float noise first, so 54.49999999999999 counts as 54.5.
    return math.floor(round(value, 9) + 0.5)
