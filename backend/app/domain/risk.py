"""Rule-based concern levels for cooperative key figures.

The thresholds live in ``config/risk_rules.toml`` so they can be tuned without
touching code. The result is descriptive ("Låg risk", "Hög risk"), always comes with
the rule that produced it, and is never presented as an objective credit rating.
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
class OverallRule:
    min_assessed_indicators: int
    high_when_high_count_at_least: int
    high_when_one_high_and_moderate_count_at_least: int
    moderate_when_moderate_count_at_least: int

    def assess(self, levels: list[ConcernLevel]) -> ConcernLevel:
        assessed = [level for level in levels if level != ConcernLevel.INSUFFICIENT_INFORMATION]
        if len(assessed) < self.min_assessed_indicators:
            return ConcernLevel.INSUFFICIENT_INFORMATION
        high = assessed.count(ConcernLevel.HIGH)
        moderate = assessed.count(ConcernLevel.MODERATE)
        if high >= self.high_when_high_count_at_least:
            return ConcernLevel.HIGH
        if high == 1 and moderate >= self.high_when_one_high_and_moderate_count_at_least:
            return ConcernLevel.HIGH
        if high == 1 or moderate >= self.moderate_when_moderate_count_at_least:
            return ConcernLevel.MODERATE
        return ConcernLevel.LOW

    def describe(self) -> str:
        return (f"Minst {self.min_assessed_indicators} indikatorer krävs. "
                f"Hög risk om minst {self.high_when_high_count_at_least} indikatorer visar hög risk, "
                f"eller en visar hög och minst {self.high_when_one_high_and_moderate_count_at_least} måttlig. "
                f"Måttlig risk om en indikator visar hög risk eller minst "
                f"{self.moderate_when_moderate_count_at_least} visar måttlig. Annars låg risk.")


@dataclass(frozen=True)
class RiskRules:
    indicators: dict[str, IndicatorRule]
    overall: OverallRule
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
    return RiskRules(indicators=indicators, overall=OverallRule(**raw["overall"]), score=score)


def _parse_direction(metric_key: str, direction: str) -> bool:
    if direction == "higher_is_worse":
        return True
    if direction == "lower_is_worse":
        return False
    raise ValueError(f"Invalid direction {direction!r} for indicator {metric_key}")
