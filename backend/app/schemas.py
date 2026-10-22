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
