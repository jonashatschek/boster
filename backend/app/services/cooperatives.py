"""Building the analysis of a housing cooperative from its stored observations.

Steps: resolve the observations of each (metric, year), calculate KPIs from the
resolved base figures, compare reported key figures with our own calculations,
and assess the latest year against the configured risk rules.
"""

import math
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain.kpis import TOTAL_AREA_FORMULA, CalculatedKpi, calculate_all, calculate_kpi, values_agree
from app.domain.metrics import METRICS
from app.domain.provenance import ExtractionMethod, ValueOrigin, VerificationStatus
from app.domain.resolution import Observation, ResolvedValue, resolve
from app.domain.risk import CONCERN_LABELS, ConcernLevel, RiskRules
from app.domain.score import LAND_TENURE_PART, MaintenanceRule, TrendRule, compute_score
from app.models import FinancialObservation, HousingCooperative, MaintenanceAnswer, SourceDocument
from app.schemas import (
    CalculatedValue, Completeness, CooperativeInfo, CooperativeListItem, CooperativeOverview, CooperativeScore,
    DocumentSummary, Finding, MaintenanceQuestion, MetricSeries, ReportedValue, RiskAssessment, RiskIndicator, ScoreMissingPart,
    ScorePart, SourceRef, TrendInput, YearValue,
)

# The figures a buyer most needs. Used for the completeness indicator.
CORE_METRICS = [
    "interest_bearing_debt", "cash", "interest_expense", "annual_result", "net_revenue", "total_area",
    "debt_per_sqm_total_area", "savings_per_sqm", "interest_sensitivity_pct", "annual_fee_per_sqm",
    "energy_cost_per_sqm", "fee_share_of_revenue_pct",
]

# Among automatic sources for the same document, prefer the most precise one.
_METHOD_PRIORITY = {
    ExtractionMethod.PDF_FINANCIAL_STATEMENT.value: 0,
    ExtractionMethod.PDF_TEXT_PATTERN.value: 1,
    ExtractionMethod.PDF_KEY_FIGURES_TABLE.value: 2,
    ExtractionMethod.MANUAL.value: 3,
}

LAND_TENURE_KEY = "land_tenure"
DISCLAIMER = ("Bedömningen bygger på tumregler och de uppgifter som finns i dokumenten. Den är inget kreditbetyg "
              "och ersätter inte en egen genomgång av årsredovisningen eller professionell rådgivning.")


def load_cooperative(session: Session, cooperative_id: int) -> HousingCooperative | None:
    return session.scalar(
        select(HousingCooperative)
        .where(HousingCooperative.id == cooperative_id)
        .options(
            selectinload(HousingCooperative.observations).selectinload(FinancialObservation.source_document),
            selectinload(HousingCooperative.documents).selectinload(SourceDocument.findings),
        )
    )


def list_cooperatives(session: Session, rules: RiskRules) -> list[CooperativeListItem]:
    cooperatives = session.scalars(
        select(HousingCooperative)
        .order_by(HousingCooperative.updated_at.desc())
        .options(selectinload(HousingCooperative.observations).selectinload(FinancialObservation.source_document),
                 selectinload(HousingCooperative.documents))
    ).all()
    items = []
    for cooperative in cooperatives:
        overview = build_overview(cooperative, rules)
        items.append(CooperativeListItem(
            id=cooperative.id, name=cooperative.name, organisation_number=cooperative.organisation_number,
            latest_fiscal_year=overview.latest_fiscal_year, document_count=len(cooperative.documents),
            score=score_value(overview.score), score_label=score_label(overview.score),
            updated_at=cooperative.updated_at,
        ))
    return items


def score_value(score: CooperativeScore | None) -> int | None:
    return score.score if score else None


def score_label(score: CooperativeScore | None) -> str | None:
    return score.label if score else None


def coverage_text(assessed: int, total: int, core_weight_share: float, land_tenure_known: bool = False,
                  trends: tuple[int, int] = (0, 0), maintenance: tuple[int, int] = (0, 0)) -> str:
    """"Baserat på 4 av 6 nyckeltal och marken (77 % av vikten), 2 av 2 trender och 1 av 3 underhållssvar."

    Built here only. The percentage is the share the minimum coverage uses (key figures and land tenure), so a
    score shown next to it never seems to contradict the rule; trends and maintenance answers are listed after it,
    as they never decide whether there is a score.
    """
    share = math.floor(core_weight_share * 100 + 0.5)
    core = f"{assessed} av {total} nyckeltal" + (" och marken" if land_tenure_known else "")
    extras = [f"{trends[0]} av {trends[1]} trender"] if trends[1] else []
    extras += [f"{maintenance[0]} av {maintenance[1]} underhållssvar"] if maintenance[1] else []
    extra_text = ""
    if len(extras) == 1:
        extra_text = f" och {extras[0]}"
    elif extras:
        extra_text = ", " + ", ".join(extras[:-1]) + f" och {extras[-1]}"
    return f"Baserat på {core} ({share} % av vikten){extra_text}."


def build_overview(cooperative: HousingCooperative, rules: RiskRules) -> CooperativeOverview:
    resolved = _resolve_all(cooperative.observations)
    observations_by_id = {o.id: o for o in cooperative.observations}
    years = sorted({year for _, year in resolved}, reverse=True)
    figures_by_year = _figures_by_year(resolved)

    calculated: dict[tuple[str, int], CalculatedKpi] = {}
    for year in years:
        for kpi in calculate_all(figures_by_year[year], figures_by_year.get(year - 1)):
            if kpi.is_available or (kpi.metric_key, year) in resolved:
                calculated[(kpi.metric_key, year)] = kpi

    metrics = _metric_series(resolved, calculated, years, observations_by_id)
    latest_year = _latest_fiscal_year(cooperative, years)
    return CooperativeOverview(
        cooperative=CooperativeInfo.model_validate(cooperative),
        fiscal_years=years,
        latest_fiscal_year=latest_year,
        metrics=metrics,
        risk=_assess_risk(cooperative, metrics, latest_year, rules),
        score=_score(cooperative, metrics, latest_year, rules),
        maintenance=maintenance_questions(cooperative, rules),
        completeness=_completeness(metrics, latest_year),
        documents=[DocumentSummary.model_validate(d) for d in
                   sorted(cooperative.documents, key=lambda d: (d.reporting_year or 0, d.id), reverse=True)],
        findings=[
            Finding(topic=f.topic, document_id=d.id, document_name=d.original_filename, page=f.page_number,
                    excerpt=f.excerpt)
            for d in cooperative.documents for f in d.findings
        ],
    )


@dataclass
class YearCalculations:
    """Every KPI calculation for one fiscal year, including unavailable ones with their missing inputs."""

    calculations: dict[str, CalculatedKpi]
    # Inputs that exist but whose sources disagree, named like `missing_inputs` ("key" or "previous:key").
    # The calculation lists them as missing because a conflicting value is never used.
    conflicting: set[str]


def calculations_for_year(cooperative: HousingCooperative, year: int) -> YearCalculations:
    resolved = _resolve_all(cooperative.observations)
    figures_by_year = _figures_by_year(resolved)
    current, previous = figures_by_year.get(year, {}), figures_by_year.get(year - 1)
    calculations = {kpi.metric_key: kpi for kpi in calculate_all(current, previous)}
    if "total_area" not in calculations and current.get("total_area") is None:
        calculations["total_area"] = calculate_kpi(TOTAL_AREA_FORMULA, current)  # Unavailable: keep its missing parts.
    conflicting = {key for (key, resolved_year), result in resolved.items() if result.value is None and resolved_year == year}
    conflicting |= {f"previous:{key}" for (key, resolved_year), result in resolved.items()
                    if result.value is None and resolved_year == year - 1}
    return YearCalculations(calculations, conflicting)


def _figures_by_year(resolved: dict[tuple[str, int], ResolvedValue]) -> dict[int, dict[str, float]]:
    """The agreed values per year; conflicting figures (value None) are left out."""
    figures_by_year: dict[int, dict[str, float]] = defaultdict(dict)
    for (metric_key, year), result in resolved.items():
        if result.value is not None:
            figures_by_year[year][metric_key] = result.value
    return figures_by_year


def _resolve_all(observations: list[FinancialObservation]) -> dict[tuple[str, int], ResolvedValue]:
    def preference(o: FinancialObservation):
        document = o.source_document
        return (-(document.reporting_year or 0) if document else 0,
                _METHOD_PRIORITY.get(o.extraction_method, 9), -(o.source_document_id or 0), o.id)

    grouped: dict[tuple[str, int], list[FinancialObservation]] = defaultdict(list)
    for observation in sorted(observations, key=preference):
        if observation.metric_key in METRICS:
            grouped[(observation.metric_key, observation.fiscal_year)].append(observation)

    resolved = {}
    for key, group in grouped.items():
        result = resolve([
            Observation(o.metric_key, o.fiscal_year, o.value, VerificationStatus(o.verification_status), o.id)
            for o in group
        ])
        resolved[key] = result
    return resolved


def _source_ref(o: FinancialObservation) -> SourceRef:
    return SourceRef(
        observation_id=o.id, value=o.value, status=o.verification_status, method=o.extraction_method,
        document_id=o.source_document_id, document_name=o.source_document.original_filename if o.source_document else None,
        page=o.source_page, printed_label=o.printed_label, note=o.note,
    )


def _metric_series(resolved: dict[tuple[str, int], ResolvedValue], calculated: dict[tuple[str, int], CalculatedKpi],
                   years: list[int], observations_by_id: dict[int, FinancialObservation]) -> list[MetricSeries]:
    series = []
    for definition in METRICS.values():
        values = []
        for year in years:
            reported_result = resolved.get((definition.key, year))
            calculation = calculated.get((definition.key, year))
            if reported_result is None and (calculation is None or not calculation.is_available):
                continue
            values.append(_year_value(year, reported_result, calculation, observations_by_id))
        if values:
            series.append(MetricSeries(
                key=definition.key, label=definition.label, unit=definition.unit.value,
                category=definition.category.value, description=definition.description,
                area_basis=definition.area_basis.value if definition.area_basis else None, values=values,
            ))
    return series


def _year_value(year: int, reported_result: ResolvedValue | None, calculation: CalculatedKpi | None,
                observations_by_id: dict[int, FinancialObservation]) -> YearValue:
    reported = None
    if reported_result is not None:
        reported = ReportedValue(
            value=reported_result.value, status=reported_result.status.value,
            sources=[_source_ref(observations_by_id[c.observation_id]) for c in reported_result.candidates],
            note=reported_result.note,
        )
    calculated = None
    if calculation is not None:
        calculated = CalculatedValue(
            value=calculation.value, formula=calculation.formula, inputs=calculation.inputs,
            missing_inputs=calculation.missing_inputs, note=calculation.note,
        )

    if reported is not None and reported.value is not None:
        warning = None
        status = reported.status
        if calculated is not None and calculated.value is not None and not values_agree(reported.value, calculated.value):
            status = VerificationStatus.CONFLICTING.value
            warning = (f"Egen beräkning ger {calculated.value:,.1f}".replace(",", " ")
                       + ", vilket avviker från det rapporterade värdet. Det kan bero på att föreningen använder en "
                         "annan yta eller definition. Kontrollera källorna.")
        return YearValue(fiscal_year=year, reported=reported, calculated=calculated, display_value=reported.value,
                         display_status=status, display_origin=ValueOrigin.REPORTED.value, warning=warning)
    if reported is not None:  # Conflicting sources.
        return YearValue(fiscal_year=year, reported=reported, calculated=calculated, display_value=None,
                         display_status=VerificationStatus.CONFLICTING.value, display_origin=None,
                         warning=reported.note)
    return YearValue(fiscal_year=year, reported=None, calculated=calculated, display_value=calculated.value,
                     display_status=VerificationStatus.CALCULATED.value, display_origin=ValueOrigin.CALCULATED.value)


def _latest_fiscal_year(cooperative: HousingCooperative, years: list[int]) -> int | None:
    """The year of the newest annual report, not just the newest year mentioned anywhere."""
    report_years = [d.reporting_year for d in cooperative.documents if d.reporting_year]
    if report_years:
        return max(report_years)
    return years[0] if years else None


def _score(cooperative: HousingCooperative, metrics: list[MetricSeries], year: int | None,
           rules: RiskRules) -> CooperativeScore | None:
    """The 0–100 score from the same latest-year values the risk indicators use, and the land tenure."""
    if rules.score is None:
        return None
    year_values = {key: _year_value_of(metrics, key, year) for key in rules.score.weights}
    # A conflicting value is never scored, also when it is still displayed (reported vs. calculated).
    usable = {key: v.display_value if v and v.display_status != VerificationStatus.CONFLICTING.value else None
              for key, v in year_values.items()}
    trends = {key: _trend_years(metrics, trend, year) for key, trend in rules.score.trends.items()}
    answers = {f"maintenance:{a.name}": a for a in cooperative.maintenance_answers}
    result = compute_score(usable, rules, land_tenure=cooperative.land_tenure,
                           trends={key: info.change for key, info in trends.items()},
                           maintenance={key: a.answer for key, a in answers.items()})
    parts = []
    for part in result.parts:
        if part.metric_key == LAND_TENURE_PART:
            parts.append(_land_tenure_part(cooperative, part, rules))
        elif part.metric_key in trends:
            parts.append(_trend_part(rules.score.trends[part.metric_key], trends[part.metric_key], part, year))
        elif part.metric_key in rules.score.maintenance:
            parts.append(_maintenance_part(rules.score.maintenance[part.metric_key], answers[part.metric_key], part))
        else:
            parts.append(ScorePart(
                key=part.metric_key, label=METRICS[part.metric_key].label, value=part.value, value_text=None,
                unit=METRICS[part.metric_key].unit.value, fiscal_year=year, source_text=None,
                status=year_values[part.metric_key].display_status, rule=_scale_rule(rules, part.metric_key),
                part_score=part.part_score, weight=part.weight,
                weight_reason=rules.score.weights[part.metric_key].reason, effective_weight=part.effective_weight,
                **_part_provenance(year_values[part.metric_key]),
            ))
    missing = []
    for key in result.missing:
        if key == LAND_TENURE_PART:
            missing.append(ScoreMissingPart(key=key, label="Mark",
                                            reason="Okänt om föreningen äger marken eller har tomträtt."))
        elif key in trends:
            missing.append(ScoreMissingPart(key=key, label=_trend_label(rules.score.trends[key]),
                                            reason=trends[key].reason))
        elif key in rules.score.maintenance:
            given = answers.get(key)
            missing.append(ScoreMissingPart(
                key=key, label=_maintenance_label(rules.score.maintenance[key]),
                reason="Besvarat med Vet inte." if given and given.answer == "unknown" else "Inte besvarat."))
        else:
            missing.append(ScoreMissingPart(key=key, label=METRICS[key].label,
                                            reason=_missing_part_reason(year_values[key], year)))
    key_figures = sum(1 for part in parts if part.key in rules.score.weights)
    trends_present = sum(1 for part in parts if part.key in trends)
    answered = sum(1 for part in parts if part.key in rules.score.maintenance)
    insufficient = CONCERN_LABELS[ConcernLevel.INSUFFICIENT_INFORMATION]
    return CooperativeScore(
        score=result.score, label=None if result.score is not None else insufficient,
        rule=rules.score.describe(), weight_share=result.weight_share, key_figures_assessed=key_figures,
        key_figures_total=len(rules.score.weights),
        coverage=coverage_text(key_figures, len(rules.score.weights), result.core_weight_share,
                               land_tenure_known=LAND_TENURE_PART not in result.missing
                               and rules.score.land_tenure is not None,
                               trends=(trends_present, len(trends)),
                               maintenance=(answered, len(rules.score.maintenance))),
        parts=parts, missing=missing,
    )


@dataclass
class _TrendYears:
    """The years a trend uses and its change per year; or, when it cannot be computed, why not."""

    change: float | None
    values: list[tuple[int, YearValue]]
    reason: str | None


def _trend_years(metrics: list[MetricSeries], trend: TrendRule, year: int | None) -> _TrendYears:
    """The trend's latest `years` fiscal years, each of which needs an agreed value; never interpolated."""
    if year is None:
        return _TrendYears(None, [], "Inget räkenskapsår att bedöma.")
    values = []
    for fiscal_year in range(year - trend.years + 1, year + 1):
        year_value = _year_value_of(metrics, trend.metric_key, fiscal_year)
        if year_value is not None and year_value.display_status == VerificationStatus.CONFLICTING.value:
            return _TrendYears(None, [], f"Motstridiga uppgifter för räkenskapsår {fiscal_year}.")
        if year_value is None or year_value.display_value is None:
            return _TrendYears(None, [], f"Saknas för räkenskapsår {fiscal_year}.")
        values.append((fiscal_year, year_value))
    change = trend.change([v.display_value for _, v in values])
    if change is None:
        first_year = values[0][0]
        return _TrendYears(None, [], f"Kan inte räknas i procent eftersom värdet för {first_year} är noll eller "
                                     f"negativt.")
    return _TrendYears(change, values, None)


def _trend_input(fiscal_year: int, year_value: YearValue) -> TrendInput:
    """One trend year with its own provenance: only the sources of the value used, or our formula."""
    provenance = _part_provenance(year_value)
    used = [source for source in provenance["sources"] if math.isclose(source.value, year_value.display_value)]
    return TrendInput(fiscal_year=fiscal_year, value=year_value.display_value, status=year_value.display_status,
                      sources=used, formula=provenance["formula"])


def _trend_label(trend: TrendRule) -> str:
    return f"{METRICS[trend.metric_key].label}, förändring"


def _trend_part(trend: TrendRule, info: _TrendYears, part, year: int) -> ScorePart:
    """A trend part with the years and values it used, and each year's sources."""
    figure_unit = METRICS[trend.metric_key].unit.value
    shown_unit = _SHOWN_UNITS.get(figure_unit, figure_unit)
    unit = "% per år" if trend.measure == "percent_per_year" else f"{shown_unit} per år"
    return ScorePart(
        key=trend.key, label=_trend_label(trend), value=part.value, value_text=None, unit=unit, fiscal_year=year,
        status=VerificationStatus.CALCULATED.value, sources=[], source_text=None, formula=None,
        inputs=[_trend_input(fiscal_year, v) for fiscal_year, v in info.values],
        rule=trend.describe(shown_unit), part_score=part.part_score, weight=part.weight,
        weight_reason=trend.reason, effective_weight=part.effective_weight,
    )


def _maintenance_label(question: MaintenanceRule) -> str:
    return f"{question.label}, kommande"


def _maintenance_part(question: MaintenanceRule, given: MaintenanceAnswer, part) -> ScorePart:
    """A maintenance answer as a part: the user's own answer is the only source."""
    return ScorePart(
        key=question.key, label=_maintenance_label(question), value=None,
        value_text={"yes": "Ja", "no": "Nej"}[given.answer], unit=None, fiscal_year=None,
        status=VerificationStatus.USER_ENTERED.value, sources=[],
        source_text=f"Angivet av dig ({given.answered_at:%Y-%m-%d}).", formula=None, rule=question.describe(),
        part_score=part.part_score, weight=part.weight, weight_reason=question.reason,
        effective_weight=part.effective_weight,
    )


def maintenance_questions(cooperative: HousingCooperative, rules: RiskRules) -> list[MaintenanceQuestion]:
    if rules.score is None:
        return []
    answers = {a.name: a for a in cooperative.maintenance_answers}
    return [
        MaintenanceQuestion(name=q.name, label=q.label, topic=q.topic, question=q.question,
                            answer=answers[q.name].answer if q.name in answers else None,
                            answered_at=answers[q.name].answered_at if q.name in answers else None)
        for q in rules.score.maintenance.values()
    ]


def answer_maintenance(session: Session, cooperative: HousingCooperative, name: str, answer: str) -> None:
    """Save the user's answer; an existing answer is replaced."""
    existing = next((a for a in cooperative.maintenance_answers if a.name == name), None)
    if existing:
        existing.answer = answer
    else:
        cooperative.maintenance_answers.append(MaintenanceAnswer(name=name, answer=answer))
    session.commit()


LAND_TENURE_TEXT = {"owned": "Äganderätt", "leasehold": "Tomträtt"}
MANUAL_LAND_TENURE = "Angivet manuellt."


def _land_tenure_part(cooperative: HousingCooperative, part, rules: RiskRules) -> ScorePart:
    """The land tenure part, sourced from the report's statement or marked as entered by the user."""
    land = rules.score.land_tenure
    by_user = cooperative.land_tenure_source == MANUAL_LAND_TENURE
    return ScorePart(
        key=LAND_TENURE_PART, label="Mark", value=None, value_text=LAND_TENURE_TEXT[cooperative.land_tenure],
        unit=None, fiscal_year=None,
        status=VerificationStatus.USER_ENTERED.value if by_user else VerificationStatus.EXTRACTED.value,
        sources=[], source_text=cooperative.land_tenure_source, formula=None, rule=land.describe(),
        part_score=part.part_score, weight=part.weight, weight_reason=land.reason,
        effective_weight=part.effective_weight,
    )


def _part_provenance(year_value: YearValue) -> dict:
    """Where a scored value comes from: the report's observations, or our formula when we calculated it."""
    if year_value.display_origin == ValueOrigin.CALCULATED.value and year_value.calculated is not None:
        return {"sources": [], "formula": year_value.calculated.formula}
    return {"sources": year_value.reported.sources if year_value.reported else [], "formula": None}


def _scale_rule(rules: RiskRules, metric_key: str) -> str:
    rule = rules.indicators[metric_key]
    unit = METRICS[metric_key].unit.value
    good, bad = _limit_text(rule.low_concern_until, unit), _limit_text(rule.high_concern_from, unit)
    if rule.higher_is_worse:
        return f"100 poäng vid {good} eller lägre, 0 poäng vid {bad} eller högre, jämnt fördelat däremellan."
    return f"100 poäng vid {good} eller högre, 0 poäng vid {bad} eller lägre, jämnt fördelat däremellan."


# Units as the page shows values (frontend formatValue), so a threshold reads like the value next to it.
_SHOWN_UNITS = {"kr/kvm": "kr/m²", "kvm": "m²"}


def _limit_text(value: float, unit: str) -> str:
    """A threshold in Swedish format: "5 000 kr/m²", "1,2 ggr", "5 %"."""
    number = f"{value:,.0f}".replace(",", " ") if value == int(value) else f"{value:g}".replace(".", ",")
    return f"{number} {_SHOWN_UNITS.get(unit, unit)}"


def _missing_part_reason(year_value: YearValue | None, year: int | None) -> str:
    if year is None:
        return "Inget räkenskapsår att bedöma."
    if year_value is not None and year_value.display_status == VerificationStatus.CONFLICTING.value:
        return f"Motstridiga uppgifter för räkenskapsår {year}."
    return f"Saknas för räkenskapsår {year}."


def _year_value_of(metrics: list[MetricSeries], metric_key: str, year: int | None) -> YearValue | None:
    series = next((s for s in metrics if s.key == metric_key), None)
    return next((v for v in series.values if v.fiscal_year == year), None) if series else None


def _display_value(metrics: list[MetricSeries], metric_key: str, year: int | None) -> float | None:
    year_value = _year_value_of(metrics, metric_key, year)
    return year_value.display_value if year_value else None


def _assess_risk(cooperative: HousingCooperative, metrics: list[MetricSeries], year: int | None,
                 rules: RiskRules) -> RiskAssessment:
    indicators = []
    for metric_key, rule in rules.indicators.items():
        value = _display_value(metrics, metric_key, year)
        level = rule.assess(value)
        indicators.append(RiskIndicator(
            key=metric_key, label=METRICS[metric_key].label, value=value, unit=METRICS[metric_key].unit.value,
            fiscal_year=year, level=level.value, level_label=CONCERN_LABELS[level], rationale=rule.rationale,
            rule=rule.describe(),
        ))
    indicators.append(_land_tenure_indicator(cooperative))
    return RiskAssessment(fiscal_year=year, indicators=indicators, disclaimer=DISCLAIMER)


def _land_tenure_indicator(cooperative: HousingCooperative) -> RiskIndicator:
    level = {
        "leasehold": ConcernLevel.MODERATE, "owned": ConcernLevel.LOW,
    }.get(cooperative.land_tenure or "", ConcernLevel.INSUFFICIENT_INFORMATION)
    return RiskIndicator(
        key=LAND_TENURE_KEY, label="Mark", value=None, unit=None, fiscal_year=None, level=level.value,
        level_label=CONCERN_LABELS[level],
        rationale=("Med tomträtt betalar föreningen en årlig avgäld till kommunen. Avgälden omförhandlas med "
                   "jämna mellanrum och kan då höjas kraftigt, vilket påverkar månadsavgiften. "
                   "Egen mark ger ingen sådan risk."),
        rule="Tomträtt ger måttlig risk, ägd mark låg risk.",
    )


def _completeness(metrics: list[MetricSeries], year: int | None) -> Completeness:
    available = [key for key in CORE_METRICS if _display_value(metrics, key, year) is not None]
    return Completeness(fiscal_year=year, available=available,
                        missing=[key for key in CORE_METRICS if key not in available])

