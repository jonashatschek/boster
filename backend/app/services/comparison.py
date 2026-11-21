"""Side-by-side comparison of housing cooperatives.

Each cooperative is compared on its latest fiscal year. The comparison reuses the
single-cooperative analysis and adds what only matters across cooperatives:
warnings when the compared years or period lengths differ, and notes where the
reports may define the same figure differently.
"""

from collections.abc import Set as AbstractSet

from app.domain.kpis import CalculatedKpi
from app.domain.metrics import METRICS, AreaBasis, Unit
from app.domain.risk import CONCERN_LABELS, RiskRules
from app.models import HousingCooperative
from app.schemas import (
    ComparedCooperative, ComparisonCell, ComparisonRow, CooperativeComparison, CooperativeOverview, HistoryPoint,
)
from app.services.cooperatives import (
    CORE_METRICS, YearCalculations, build_overview, calculations_for_year, score_label, score_value,
)

MIN_COOPERATIVES = 2
MAX_COOPERATIVES = 4

# Shown by default: the risk indicators plus the figures buyers usually ask about.
# Further figures are available under "all figures".
DEFAULT_METRICS = [
    "debt_per_sqm_total_area", "debt_per_sqm_tenant_owned_area", "savings_per_sqm", "interest_sensitivity_pct",
    "annual_fee_per_sqm", "energy_cost_per_sqm", "fee_share_of_revenue_pct", "interest_coverage_ratio",
    "short_term_debt_share_pct", "interest_bearing_debt",
]

_AREA_BASIS_NOTES = {
    AreaBasis.TOTAL_AREA: ("Per kvm totalyta. Föreningar räknar ibland in garage eller biytor i totalytan, "
                           "så små skillnader kan bero på definitionen."),
    AreaBasis.TENANT_OWNED_AREA: "Per kvm yta upplåten med bostadsrätt. Jämför inte med värden per kvm totalyta.",
}


def compare_cooperatives(cooperatives: list[HousingCooperative], rules: RiskRules) -> CooperativeComparison:
    overviews = [build_overview(cooperative, rules) for cooperative in cooperatives]
    compared = [_compared_cooperative(overview) for overview in overviews]

    # Core figures always get a row, so one that no cooperative reports shows as "Saknas" instead of vanishing.
    present_keys = {series.key for overview in overviews for series in overview.metrics} | set(CORE_METRICS)
    ordered_keys = [key for key in DEFAULT_METRICS if key in present_keys]
    ordered_keys += [key for key in METRICS if key in present_keys and key not in DEFAULT_METRICS]

    # Calculations for the compared year, also the unavailable ones, so a missing cell can say what is lacking.
    calculations = [calculations_for_year(cooperative, c.fiscal_year) if c.fiscal_year else YearCalculations({}, set())
                    for cooperative, c in zip(cooperatives, compared)]
    rows = [_row(key, overviews, compared, calculations, rules) for key in ordered_keys]
    return CooperativeComparison(cooperatives=compared, rows=rows, warnings=_warnings(compared))


def _compared_cooperative(overview: CooperativeOverview) -> ComparedCooperative:
    year = overview.latest_fiscal_year
    return ComparedCooperative(
        id=overview.cooperative.id, name=overview.cooperative.name,
        organisation_number=overview.cooperative.organisation_number,
        land_tenure=overview.cooperative.land_tenure, fiscal_year=year,
        period_months=_period_months(overview, year),
        score=score_value(overview.score), score_label=score_label(overview.score),
        completeness_available=len(overview.completeness.available), completeness_total=len(CORE_METRICS),
    )


def _period_months(overview: CooperativeOverview, year: int | None) -> int | None:
    for document in overview.documents:
        if document.reporting_year == year and document.fiscal_period_start and document.fiscal_period_end:
            start, end = document.fiscal_period_start, document.fiscal_period_end
            return (end.year - start.year) * 12 + end.month - start.month + 1
    return None


def _row(key: str, overviews: list[CooperativeOverview], compared: list[ComparedCooperative],
         calculations: list[YearCalculations], rules: RiskRules) -> ComparisonRow:
    definition = METRICS[key]
    rule = rules.indicators.get(key)
    cells, history = [], {}

    for overview, cooperative, cooperative_calculations in zip(overviews, compared, calculations):
        series = next((s for s in overview.metrics if s.key == key), None)
        values = series.values if series else []
        history[cooperative.id] = [
            HistoryPoint(fiscal_year=v.fiscal_year, value=v.display_value, status=v.display_status)
            for v in sorted(values, key=lambda v: v.fiscal_year)
        ]
        current = next((v for v in values if v.fiscal_year == cooperative.fiscal_year), None)
        value = current.display_value if current else None
        level = rule.assess(value) if rule else None
        warnings = [current.warning] if current and current.warning else []
        if value is not None and definition.unit == Unit.SEK and cooperative.period_months not in (None, 12):
            warnings.append(f"Räkenskapsåret omfattar {cooperative.period_months} månader, så årsbelopp blir "
                            f"inte jämförbara med ett vanligt år.")
        warning = " ".join(warnings) or None
        status = current.display_status if current else "missing"
        cells.append(ComparisonCell(
            cooperative_id=cooperative.id, fiscal_year=cooperative.fiscal_year, value=value, status=status,
            level=level.value if level else None, level_label=CONCERN_LABELS[level] if level else None,
            warning=warning,
            missing_reason=(_missing_reason(cooperative.fiscal_year, cooperative_calculations.calculations.get(key),
                                            cooperative_calculations.conflicting)
                            if value is None and status == "missing" else None),
        ))

    return ComparisonRow(
        key=key, label=definition.label, unit=definition.unit.value, description=definition.description,
        area_basis=definition.area_basis.value if definition.area_basis else None,
        is_default=key in DEFAULT_METRICS, cells=cells, history=history,
        note=_AREA_BASIS_NOTES.get(definition.area_basis) if definition.area_basis else None,
    )


def _missing_reason(year: int | None, calculation: CalculatedKpi | None,
                    conflicting: AbstractSet[str] = frozenset()) -> str:
    """Why a figure is missing for `year`, stated only from what the data shows.

    An input in `conflicting` exists but its sources disagree, so it is named as such, not as missing.
    """
    if year is None:
        return "Inget räkenskapsår att jämföra."
    not_found = f"Hittades inte i årsredovisningen för {year}"
    if calculation is not None and calculation.missing_inputs:
        absent = [_input_label(key) for key in calculation.missing_inputs if key not in conflicting]
        disputed = [_input_label(key) for key in calculation.missing_inputs if key in conflicting]
        reason = f"{not_found} och kan inte beräknas."
        if absent:
            reason += f" Saknas: {', '.join(absent)}."
        if disputed:
            reason += f" Motstridiga uppgifter om {', '.join(disputed)}."
        return reason
    if calculation is not None and calculation.note:
        return f"{not_found}. {calculation.note}"
    return f"{not_found}."


def _input_label(key: str) -> str:
    """"previous:interest_bearing_debt" → "räntebärande skulder (föregående år)"."""
    label = METRICS[key.removeprefix("previous:")].label.lower()
    return f"{label} (föregående år)" if key.startswith("previous:") else label


def _warnings(compared: list[ComparedCooperative]) -> list[str]:
    warnings = []
    years = {c.fiscal_year for c in compared}
    if len(years) > 1:
        listing = ", ".join(f"{c.name} {c.fiscal_year or 'okänt år'}" for c in compared)
        warnings.append(f"Föreningarna jämförs på olika räkenskapsår: {listing}. "
                        f"Ladda upp nyare årsredovisningar för en rättvisare jämförelse.")
    for cooperative in compared:
        if cooperative.period_months not in (None, 12):
            warnings.append(
                f"{cooperative.name} har ett räkenskapsår på {cooperative.period_months} månader. "
                f"Nyckeltal per kvm och procent går att jämföra, men årsbelopp (t.ex. intäkter och "
                f"räntekostnader) gör det inte."
            )
    # Missing values are not warned about here: the table shows each one as "Saknas".
    return warnings
