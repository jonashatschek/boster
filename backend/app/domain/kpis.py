"""Deterministic calculation of cooperative key figures.

Each formula declares its inputs and a human-readable description. A calculation
never guesses: if an input is missing, or a denominator is zero, the result is
``None`` and the reason is recorded, so the UI can show "saknas" instead of a number.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

# Figures for one fiscal year, keyed by metric key (see ``metrics.py``).
YearFigures = Mapping[str, float]


@dataclass(frozen=True)
class KpiFormula:
    metric_key: str
    formula: str  # Shown to the user, in Swedish.
    inputs: tuple[str, ...]  # Metric keys from the current year.
    previous_year_inputs: tuple[str, ...] = ()  # Metric keys from the year before.
    compute: Callable[..., float] = field(repr=False, default=lambda: 0.0)


@dataclass(frozen=True)
class CalculatedKpi:
    metric_key: str
    value: float | None
    formula: str
    inputs: dict[str, float]  # Input values actually used, keyed "metric" or "previous:metric".
    missing_inputs: list[str]
    note: str | None = None

    @property
    def is_available(self) -> bool:
        return self.value is not None


FORMULAS: tuple[KpiFormula, ...] = (
    KpiFormula(
        metric_key="debt_per_sqm_total_area",
        formula="Räntebärande skulder / totalyta",
        inputs=("interest_bearing_debt", "total_area"),
        compute=lambda debt, area: debt / area,
    ),
    KpiFormula(
        metric_key="debt_per_sqm_tenant_owned_area",
        formula="Räntebärande skulder / yta upplåten med bostadsrätt",
        inputs=("interest_bearing_debt", "tenant_owned_area"),
        compute=lambda debt, area: debt / area,
    ),
    KpiFormula(
        metric_key="net_debt",
        formula="Räntebärande skulder − kassa och bank",
        inputs=("interest_bearing_debt", "cash"),
        compute=lambda debt, cash: debt - cash,
    ),
    KpiFormula(
        metric_key="solidity_pct",
        formula="Eget kapital / summa tillgångar × 100",
        inputs=("equity", "total_assets"),
        compute=lambda equity, assets: equity / assets * 100,
    ),
    KpiFormula(
        metric_key="average_interest_rate_pct",
        formula="Räntekostnader / ((räntebärande skulder vid årets början + vid årets slut) / 2) × 100",
        inputs=("interest_expense", "interest_bearing_debt"),
        previous_year_inputs=("interest_bearing_debt",),
        compute=lambda interest, debt_end, debt_start: interest / ((debt_start + debt_end) / 2) * 100,
    ),
    KpiFormula(
        metric_key="interest_coverage_ratio",
        formula="(Rörelseresultat + avskrivningar) / räntekostnader",
        inputs=("operating_result", "depreciation", "interest_expense"),
        compute=lambda operating_result, depreciation, interest: (operating_result + depreciation) / interest,
    ),
    KpiFormula(
        metric_key="short_term_debt_share_pct",
        formula="Kortfristiga skulder till kreditinstitut / räntebärande skulder × 100",
        inputs=("short_term_interest_bearing_debt", "interest_bearing_debt"),
        compute=lambda short_term, total: short_term / total * 100,
    ),
)


def calculate_kpi(formula: KpiFormula, current: YearFigures, previous: YearFigures | None = None) -> CalculatedKpi:
    previous = previous or {}
    used: dict[str, float] = {}
    missing: list[str] = []

    for key in formula.inputs:
        if key in current and current[key] is not None:
            used[key] = current[key]
        else:
            missing.append(key)
    for key in formula.previous_year_inputs:
        if key in previous and previous[key] is not None:
            used[f"previous:{key}"] = previous[key]
        else:
            missing.append(f"previous:{key}")

    if missing:
        return CalculatedKpi(formula.metric_key, None, formula.formula, used, missing)

    arguments = [used[key] for key in formula.inputs]
    arguments += [used[f"previous:{key}"] for key in formula.previous_year_inputs]
    try:
        value = formula.compute(*arguments)
    except ZeroDivisionError:
        return CalculatedKpi(formula.metric_key, None, formula.formula, used, [],
                             note="Kan inte beräknas eftersom nämnaren är noll.")
    return CalculatedKpi(formula.metric_key, value, formula.formula, used, [])


# Used only when the report does not state the total area itself. Garage area is not
# included, which matches how most reports define "totalyta" for key figures.
TOTAL_AREA_FORMULA = KpiFormula(
    metric_key="total_area",
    formula="Bostadsyta + lokalyta",
    inputs=("residential_area", "commercial_area"),
    compute=lambda residential, commercial: residential + commercial,
)


def calculate_all(current: YearFigures, previous: YearFigures | None = None) -> list[CalculatedKpi]:
    """Calculate every known KPI for one fiscal year. Unavailable KPIs are included with value None.

    If the total area is missing but its parts are known, it is calculated first and
    included in the results, so the per-m² figures can use it.
    """
    results: list[CalculatedKpi] = []
    if current.get("total_area") is None:
        total_area = calculate_kpi(TOTAL_AREA_FORMULA, current)
        if total_area.is_available:
            results.append(total_area)
            current = {**current, "total_area": total_area.value}
    return results + [calculate_kpi(formula, current, previous) for formula in FORMULAS]


def values_agree(reported: float, calculated: float, relative_tolerance: float = 0.05,
                 absolute_tolerance: float = 1.0) -> bool:
    """Whether a reported key figure and our own calculation are consistent.

    Reports round their figures and sometimes use slightly different areas, so a small
    difference is expected. Anything beyond the tolerance is flagged as conflicting.
    """
    difference = abs(reported - calculated)
    return difference <= absolute_tolerance or difference <= relative_tolerance * max(abs(reported), abs(calculated))
