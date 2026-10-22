"""Combining several observations of the same figure into one displayed value.

The same figure is often printed in more than one place: a 2024 report and a 2025
report both contain the 2024 debt, for example. This module decides which value to
show, and refuses to pick one when the sources disagree.
"""

from dataclasses import dataclass, field

from app.domain.kpis import values_agree
from app.domain.provenance import VerificationStatus


@dataclass(frozen=True)
class Observation:
    """One value for one metric and fiscal year, from one source."""

    metric_key: str
    fiscal_year: int
    value: float
    status: VerificationStatus
    observation_id: int | None = None
    source_description: str = ""


@dataclass(frozen=True)
class ResolvedValue:
    metric_key: str
    fiscal_year: int
    value: float | None
    status: VerificationStatus
    chosen: Observation | None
    candidates: list[Observation] = field(default_factory=list)
    note: str | None = None


_USER_STATUSES = (VerificationStatus.VERIFIED, VerificationStatus.USER_ENTERED)


def resolve(observations: list[Observation]) -> ResolvedValue:
    """Resolve observations of a single (metric, fiscal year) pair.

    ``observations`` must be ordered by preference among automatic sources, normally
    newest document first, since newer reports may restate earlier years.

    Rules:
    1. A value entered or verified by the user wins over automatic extraction.
       The most recent user value is used.
    2. Automatic observations that agree (within rounding tolerance) are combined,
       and the first one is shown.
    3. Automatic observations that disagree are marked as conflicting, and no value
       is chosen. All candidates are returned so the user can decide.
    """
    if not observations:
        raise ValueError("resolve() needs at least one observation")
    metric_key, fiscal_year = observations[0].metric_key, observations[0].fiscal_year
    if any(o.metric_key != metric_key or o.fiscal_year != fiscal_year for o in observations):
        raise ValueError("All observations must refer to the same metric and fiscal year")

    user_values = [o for o in observations if o.status in _USER_STATUSES]
    if user_values:
        chosen = max(user_values, key=lambda o: o.observation_id or 0)
        others_disagree = any(not values_agree(o.value, chosen.value) for o in observations if o is not chosen)
        note = "Manuellt värde ersätter avvikande uppgift från källa." if others_disagree else None
        return ResolvedValue(metric_key, fiscal_year, chosen.value, chosen.status, chosen, observations, note)

    first = observations[0]
    if all(values_agree(o.value, first.value) for o in observations[1:]):
        return ResolvedValue(metric_key, fiscal_year, first.value, first.status, first, observations)

    return ResolvedValue(
        metric_key, fiscal_year, None, VerificationStatus.CONFLICTING, None, observations,
        note="Källorna anger olika värden. Kontrollera dokumenten och ange rätt värde manuellt.",
    )
