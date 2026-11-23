"""API request and response models."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceRef(BaseModel):
    """One observation of a value, with where it came from."""

    observation_id: int
    value: float
    status: str
    method: str
    document_id: int | None
    document_name: str | None
    page: int | None
    printed_label: str | None
    note: str | None


class ReportedValue(BaseModel):
    value: float | None  # None when the sources conflict.
    status: str
    sources: list[SourceRef]
    note: str | None = None


class CalculatedValue(BaseModel):
    value: float | None
    formula: str
    inputs: dict[str, float]
    missing_inputs: list[str]
    note: str | None = None


class YearValue(BaseModel):
    fiscal_year: int
    reported: ReportedValue | None
    calculated: CalculatedValue | None
    # The value to show by default, and its status. Reported values take precedence;
    # our calculation is used when nothing was reported.
    display_value: float | None
    display_status: str
    display_origin: str | None  # "reported" or "calculated".
    warning: str | None = None


class MetricSeries(BaseModel):
    key: str
    label: str
    unit: str
    category: str
    description: str
    area_basis: str | None
    values: list[YearValue]


class RiskIndicator(BaseModel):
    key: str
    label: str
    value: float | None
    unit: str | None
    fiscal_year: int | None
    level: str
    level_label: str
    rationale: str
    rule: str


class RiskAssessment(BaseModel):
    fiscal_year: int | None
    indicators: list[RiskIndicator]
    disclaimer: str


class Completeness(BaseModel):
    fiscal_year: int | None
    available: list[str]
    missing: list[str]


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cooperative_id: int | None
    original_filename: str
    document_url: str | None
    document_type: str
    reporting_year: int | None
    fiscal_period_start: date | None
    fiscal_period_end: date | None
    page_count: int
    extraction_status: str
    extraction_messages: list[str]
    uploaded_at: datetime


class Finding(BaseModel):
    topic: str
    document_id: int
    document_name: str
    page: int
    excerpt: str


class CooperativeInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    organisation_number: str | None
    land_tenure: str | None
    land_tenure_source: str | None
    created_at: datetime
    updated_at: datetime


class TrendInput(BaseModel):
    """One year of a trend, with where its value comes from."""

    fiscal_year: int
    value: float
    status: str  # extracted, calculated, user_entered or verified.
    sources: list[SourceRef]  # The observations behind the value used (not values it replaced).
    formula: str | None  # Set instead when Boster calculated the value.


class ScorePart(BaseModel):
    """One part's contribution to the score (a key figure, or the land tenure), with what explains it."""

    key: str
    label: str
    value: float | None  # A key figure's value; None for the land tenure, see value_text.
    value_text: str | None  # The land tenure in words ("Tomträtt", "Äganderätt").
    unit: str | None
    fiscal_year: int | None  # None for the land tenure, which is not tied to a fiscal year.
    status: str  # How the value was obtained (extracted, calculated, user_entered, verified).
    sources: list[SourceRef]  # Where a reported value was read (document, page, printed label).
    source_text: str | None  # The land tenure's quoted line with its page, or "Angivet manuellt.".
    formula: str | None  # Set instead when Boster calculated the value.
    inputs: list[TrendInput] = []  # For a trend: the years and values it used, oldest first.
    rule: str  # The gradual scale in words.
    part_score: float  # 0–100.
    weight: float  # As configured.
    weight_reason: str
    effective_weight: float  # Share among the parts that have a value; they sum to 1.


class ScoreMissingPart(BaseModel):
    key: str
    label: str
    reason: str


class CooperativeScore(BaseModel):
    """The 0–100 score, always together with its explanation. Not a credit rating."""

    score: int | None  # None below the minimum coverage ("Otillräcklig information").
    label: str | None  # "Otillräcklig information" when there is no score.
    rule: str
    weight_share: float  # Share of the total weight carried by the parts that have a value.
    key_figures_assessed: int
    key_figures_total: int
    coverage: str  # "Baserat på 4 av 6 nyckeltal (75 % av vikten)."
    parts: list[ScorePart]
    missing: list[ScoreMissingPart]


class MaintenanceQuestion(BaseModel):
    """A maintenance question for the user, with the current answer (None when unanswered)."""

    name: str
    label: str
    topic: str  # The topic of the report passages (overview.findings) shown as evidence.
    question: str
    answer: str | None  # "yes", "no", "unknown" or None.
    answered_at: datetime | None


class MaintenanceAnswerIn(BaseModel):
    answer: str = Field(pattern=r"^(yes|no|unknown)$")


class CooperativeOverview(BaseModel):
    cooperative: CooperativeInfo
    fiscal_years: list[int]
    latest_fiscal_year: int | None
    metrics: list[MetricSeries]
    risk: RiskAssessment
    score: CooperativeScore | None  # None when the rules have no [score] section.
    maintenance: list[MaintenanceQuestion] = []
    completeness: Completeness
    documents: list[DocumentSummary]
    findings: list[Finding]


class CooperativeListItem(BaseModel):
    id: int
    name: str
    organisation_number: str | None
    latest_fiscal_year: int | None
    document_count: int
    score: int | None  # The 0–100 score; None below the minimum coverage.
    score_label: str | None  # "Otillräcklig information" when there is no score.
    updated_at: datetime


class CooperativeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    organisation_number: str | None = Field(default=None, pattern=r"^\d{6}-\d{4}$")
    land_tenure: str | None = Field(default=None, pattern=r"^(owned|leasehold)$")


class ManualObservationCreate(BaseModel):
    metric_key: str
    fiscal_year: int = Field(ge=1900, le=2100)
    value: float
    note: str | None = Field(default=None, max_length=1000)


class DocumentReassign(BaseModel):
    cooperative_id: int


class MetricDefinitionOut(BaseModel):
    key: str
    label: str
    unit: str
    category: str
    description: str
    area_basis: str | None


class ComparedCooperative(BaseModel):
    id: int
    name: str
    organisation_number: str | None
    land_tenure: str | None
    fiscal_year: int | None  # The latest fiscal year, used for the comparison.
    period_months: int | None  # Length of that fiscal year, when known.
    score: int | None  # The 0–100 score; None below the minimum coverage.
    score_label: str | None  # "Otillräcklig information" when there is no score.
    completeness_available: int
    completeness_total: int


class ComparisonCell(BaseModel):
    cooperative_id: int
    fiscal_year: int | None
    value: float | None
    status: str
    level: str | None  # Concern level, for metrics that have a risk rule.
    level_label: str | None
    warning: str | None = None
    missing_reason: str | None = None  # Why the value is missing, from the data; None when there is a value.


class HistoryPoint(BaseModel):
    fiscal_year: int
    value: float | None
    status: str


class ComparisonRow(BaseModel):
    key: str
    label: str
    unit: str
    description: str
    area_basis: str | None
    is_default: bool  # Shown without expanding "all figures".
    cells: list[ComparisonCell]  # One per cooperative, in the same order as `cooperatives`.
    history: dict[int, list[HistoryPoint]]  # Cooperative id → values per year.
    note: str | None = None


class CooperativeComparison(BaseModel):
    cooperatives: list[ComparedCooperative]
    rows: list[ComparisonRow]
    warnings: list[str]


class PropertyField(BaseModel):
    """One fact about the apartment, with where it came from."""

    key: str
    label: str
    value: str | float | int | bool | date | None
    kind: str  # "text", "number", "integer", "boolean", "date", "longtext"
    unit: str | None
    status: str  # VerificationStatus value; "missing" when there is no value.
    method: str | None  # "text_label", "structured_data", "manual", ...
    excerpt: str | None  # The listing text the value was read from.
    note: str | None


class DerivedValue(BaseModel):
    key: str
    label: str
    value: float | None
    unit: str
    formula: str
    inputs: dict[str, str]  # Human-readable input → formatted value.
    missing_inputs: list[str]
    note: str | None = None


class LinkedCooperative(BaseModel):
    id: int
    name: str
    organisation_number: str | None
    fiscal_year: int | None
    score: int | None  # The 0–100 score; None below the minimum coverage.
    score_label: str | None  # "Otillräcklig information" when there is no score.
    land_tenure: str | None
    indicators: list[RiskIndicator]
    completeness_available: int
    completeness_total: int


class TransportStopOut(BaseModel):
    """The nearest stop of one transport type, or why there is none."""

    type: str  # TransportType value.
    label: str  # "Tunnelbana", "Pendeltåg/lokaltåg", "Buss".
    status: str  # "extracted" when found, "missing" otherwise.
    name: str | None
    walking_metres: int | None  # From the routing service, never estimated.
    walking_seconds: int | None
    walk_text: str | None  # "163 m (ca 2 min)", built by format_walk; None without a walking distance.
    straight_metres: int | None  # Trafiklab's distance, shown for context.
    note: str | None


class AddressCandidate(BaseModel):
    label: str  # "Pilotgatan 16, Bagarmossen, Stockholms kommun".
    municipality: str


class TransportInfo(BaseModel):
    # "not_fetched", "pending", "done", "failed", "stale" (the address changed), "choose" (waiting for the
    # user to pick the address), "skipped" (the user continued without transport) or "unavailable" (no address).
    status: str
    message: str | None
    query: str | None  # The address that is (or would be) looked up.
    looked_up_query: str | None  # The address the stored result was looked up with.
    place_label: str | None
    house_level: bool | None
    retrieved_at: datetime | None
    source: str | None
    stops: list[TransportStopOut]
    candidates: list[AddressCandidate] = []  # When status is "choose".
    truncated: bool = False  # There may be more hits than the candidates shown.


class ExternalRequest(BaseModel):
    """An HTTP call for the frontend to make. The backend itself makes no network calls."""

    stage: str  # Send the response back with this stage.
    service: str  # "nominatim", "resrobot", "valhalla".
    method: str
    url: str
    needs_key: bool  # The frontend adds the user's Trafiklab key as `accessId`.


class TransportStep(BaseModel):
    stage: Literal["start", "geocode", "stops", "walking", "choose", "skip"]
    choice: int | None = None  # With "choose": the index of the chosen candidate.
    status: int | None = None  # HTTP status of the response.
    body: Any = None  # The parsed JSON response (or text), untrusted.
    error: Literal["timeout", "network"] | None = None  # The call could not be made.


class TransportStepResult(BaseModel):
    request: ExternalRequest | None  # The next call to make, or None when finished.
    transport: TransportInfo


class PropertyOverview(BaseModel):
    id: int
    title: str | None
    source_url: str | None
    source_name: str | None
    retrieval_status: str
    retrieval_message: str | None
    retrieved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    fields: list[PropertyField]
    description: PropertyField
    derived: list[DerivedValue]
    cooperative: LinkedCooperative | None
    cooperative_suggestions: list[CooperativeListItem]
    missing: list[str]  # Labels of important facts that are missing.
    has_listing_text: bool
    transport: TransportInfo


class PropertyListItem(BaseModel):
    id: int
    title: str | None
    address: str | None
    source_name: str | None
    asking_price: float | None
    living_area: float | None
    rooms: float | None
    monthly_fee: float | None
    cooperative_id: int | None
    cooperative_name: str | None
    cooperative_score: int | None  # The linked cooperative's 0–100 score.
    cooperative_score_label: str | None  # "Otillräcklig information" when it has no score; None when unlinked.
    retrieval_status: str
    updated_at: datetime


class PropertyFromText(BaseModel):
    text: str = Field(min_length=20, max_length=200_000)
    url: str | None = Field(default=None, max_length=2000)


class PropertyText(BaseModel):
    text: str = Field(min_length=20, max_length=200_000)


class PropertyUpdate(BaseModel):
    """Manual corrections. Only the fields present are changed; null clears a value."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=300)
    address: str | None = Field(default=None, max_length=200)
    municipality: str | None = Field(default=None, max_length=100)
    neighborhood: str | None = Field(default=None, max_length=100)
    living_area: float | None = Field(default=None, gt=0, lt=2000)
    rooms: float | None = Field(default=None, gt=0, lt=50)
    floor: str | None = Field(default=None, max_length=40)
    elevator: bool | None = None
    balcony: bool | None = None
    asking_price: float | None = Field(default=None, gt=0)
    monthly_fee: float | None = Field(default=None, ge=0)
    fee_includes: str | None = Field(default=None, max_length=1000)
    fee_changes: str | None = Field(default=None, max_length=1000)
    construction_year: int | None = Field(default=None, ge=1500, le=2100)
    energy_class: str | None = Field(default=None, pattern=r"^[A-G]$")
    listing_date: date | None = None
    cooperative_name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=20_000)


class PropertyCooperativeLink(BaseModel):
    cooperative_id: int | None  # None unlinks.


class PropertyComparisonCell(BaseModel):
    property_id: int
    value: str | float | int | bool | date | None
    status: str  # VerificationStatus value, "calculated", or "missing".
    excerpt: str | None = None  # The listing line, or the formula and its inputs.
    note: str | None = None  # Why a value is missing, or what to keep in mind.
    level: str | None = None  # Concern level, for the cooperative's risk-rated figures.
    level_label: str | None = None
    fiscal_year: int | None = None  # For cooperative figures.


class PropertyComparisonRow(BaseModel):
    key: str
    group: str  # "Bostaden", "Läge", "Egenskaper", "Förening", "Uppskattningar", "Underhåll".
    label: str
    kind: str  # "text", "number", "integer", "boolean", "date", "level".
    unit: str | None
    is_estimate: bool = False  # An approximation, not a verified figure.
    note: str | None = None
    cells: list[PropertyComparisonCell]  # One per apartment, in the same order as `properties`.


class ComparedProperty(BaseModel):
    id: int
    title: str | None
    address: str | None
    source_name: str | None
    cooperative_id: int | None
    cooperative_name: str | None  # The linked cooperative's name, else the name in the listing.
    fiscal_year: int | None  # The linked cooperative's latest fiscal year.
    cooperative_score: int | None  # The linked cooperative's 0–100 score.
    cooperative_score_label: str | None  # "Otillräcklig information" when it has no score; None when unlinked.
    maintenance: list[Finding]  # Quoted report passages on renovations, loans and fees.


class PropertyComparison(BaseModel):
    properties: list[ComparedProperty]
    rows: list[PropertyComparisonRow]
    warnings: list[str]
