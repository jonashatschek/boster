"""API request and response models."""

from datetime import date, datetime

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
    overall_level: str
    overall_label: str
    overall_rule: str
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


class CooperativeOverview(BaseModel):
    cooperative: CooperativeInfo
    fiscal_years: list[int]
    latest_fiscal_year: int | None
    metrics: list[MetricSeries]
    risk: RiskAssessment
    completeness: Completeness
    documents: list[DocumentSummary]
    findings: list[Finding]


class CooperativeListItem(BaseModel):
    id: int
    name: str
    organisation_number: str | None
    latest_fiscal_year: int | None
    document_count: int
    overall_level: str
    overall_label: str
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


class DocumentFromUrl(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


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
    overall_level: str
    overall_label: str
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
    overall_level: str
    overall_label: str
    land_tenure: str | None
    indicators: list[RiskIndicator]
    completeness_available: int
    completeness_total: int


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
    cooperative_overall_level: str | None
    cooperative_overall_label: str | None
    retrieval_status: str
    updated_at: datetime


class PropertyFromUrl(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


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
