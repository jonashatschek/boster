"""Rule-based concern levels for cooperative key figures.

The thresholds live in ``config/risk_rules.toml`` so they can be tuned without
touching code. The result is descriptive ("Låg risk", "Hög risk"), always comes with
the rule that produced it, and is never presented as an objective credit rating. The
cooperative's overall summary is the 0–100 score (``score.py``), not a rule here.
"""

import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from app.domain.score import ScoreRules, load_score_rules


class ConcernLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    INSUFFICIENT_INFORMATION = "insufficient_information"


CONCERN_LABELS = {
    ConcernLevel.LOW: "Låg risk",
    ConcernLevel.MODERATE: "Måttlig risk",
    ConcernLevel.HIGH: "Hög risk",
    ConcernLevel.INSUFFICIENT_INFORMATION: "Otillräcklig information",
}


@dataclass(frozen=True)
class IndicatorRule:
    metric_key: str
    higher_is_worse: bool
    low_concern_until: float
    high_concern_from: float
    rationale: str

    def assess(self, value: float | None) -> ConcernLevel:
        if value is None:
            return ConcernLevel.INSUFFICIENT_INFORMATION
        if self.higher_is_worse:
            if value < self.low_concern_until:
                return ConcernLevel.LOW
            return ConcernLevel.HIGH if value >= self.high_concern_from else ConcernLevel.MODERATE
        if value >= self.low_concern_until:
            return ConcernLevel.LOW
        return ConcernLevel.HIGH if value < self.high_concern_from else ConcernLevel.MODERATE

    def describe(self) -> str:
        if self.higher_is_worse:
            return (f"Låg risk under {self.low_concern_until:g}, "
                    f"hög risk från {self.high_concern_from:g}.")
        return (f"Låg risk från {self.low_concern_until:g}, "
                f"hög risk under {self.high_concern_from:g}.")


@dataclass(frozen=True)
class RiskRules:
    indicators: dict[str, IndicatorRule]
    score: ScoreRules | None = None  # The 0–100 score's weights, from the [score] section.


def load_risk_rules(path: Path) -> RiskRules:
    with path.open("rb") as file:
        raw = tomllib.load(file)
    indicators = {
        key: IndicatorRule(
            metric_key=key,
            higher_is_worse=_parse_direction(key, settings["direction"]),
            low_concern_until=float(settings["low_concern_until"]),
            high_concern_from=float(settings["high_concern_from"]),
            rationale=settings["rationale"],
        )
        for key, settings in raw["indicators"].items()
    }
    score = load_score_rules(raw["score"], set(indicators)) if "score" in raw else None
    return RiskRules(indicators=indicators, score=score)


def _parse_direction(metric_key: str, direction: str) -> bool:
    if direction == "higher_is_worse":
        return True
    if direction == "lower_is_worse":
        return False
    raise ValueError(f"Invalid direction {direction!r} for indicator {metric_key}")
