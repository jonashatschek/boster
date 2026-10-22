"""Database tables.

Important figures are stored as one row per (cooperative, metric, fiscal year, source)
in ``financial_observations``, so that they stay queryable and every value keeps its
own provenance. JSON is only used for supplementary messages.
"""

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class HousingCooperative(Base):
    __tablename__ = "housing_cooperatives"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The organisation number is the primary identity. Names are not unique enough:
    # "Brf Byamännen" and "Brf Byamännen 2" are different cooperatives.
    organisation_number: Mapped[str | None] = mapped_column(String(11), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    land_tenure: Mapped[str | None] = mapped_column(String(20))  # LandTenure value.
    land_tenure_source: Mapped[str | None] = mapped_column(Text)  # Quoted evidence with page.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    documents: Mapped[list["SourceDocument"]] = relationship(back_populates="cooperative")
    observations: Mapped[list["FinancialObservation"]] = relationship(
        back_populates="cooperative", cascade="all, delete-orphan"
    )


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    cooperative_id: Mapped[int | None] = mapped_column(ForeignKey("housing_cooperatives.id", ondelete="SET NULL"))
    original_filename: Mapped[str] = mapped_column(String(300))
    document_url: Mapped[str | None] = mapped_column(Text)
    # Identical files are stored once and reused.
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    file_name: Mapped[str] = mapped_column(String(100))  # Name inside the document directory.
    document_type: Mapped[str] = mapped_column(String(30))  # DocumentType value.
    reporting_year: Mapped[int | None] = mapped_column(Integer)
    fiscal_period_start: Mapped[date | None] = mapped_column(Date)
    fiscal_period_end: Mapped[date | None] = mapped_column(Date)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    extraction_status: Mapped[str] = mapped_column(String(20))  # ExtractionStatus value.
    extraction_messages: Mapped[list[str]] = mapped_column(JSON, default=list)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    cooperative: Mapped[HousingCooperative | None] = relationship(back_populates="documents")
    observations: Mapped[list["FinancialObservation"]] = relationship(back_populates="source_document")
    findings: Mapped[list["DocumentFinding"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentFinding.id"
    )


class FinancialObservation(Base):
    __tablename__ = "financial_observations"
    __table_args__ = (
        Index("ix_observation_lookup", "cooperative_id", "metric_key", "fiscal_year"),
        UniqueConstraint("source_document_id", "metric_key", "fiscal_year", "value", "extraction_method",
                         name="uq_observation_per_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cooperative_id: Mapped[int] = mapped_column(ForeignKey("housing_cooperatives.id", ondelete="CASCADE"))
    # Null for values entered by the user.
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"))
    metric_key: Mapped[str] = mapped_column(String(60))
    fiscal_year: Mapped[int] = mapped_column(Integer)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(10))
    source_page: Mapped[int | None] = mapped_column(Integer)
    printed_label: Mapped[str | None] = mapped_column(Text)
    extraction_method: Mapped[str] = mapped_column(String(40))  # ExtractionMethod value.
    verification_status: Mapped[str] = mapped_column(String(20))  # VerificationStatus value.
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    cooperative: Mapped[HousingCooperative] = relationship(back_populates="observations")
    source_document: Mapped[SourceDocument | None] = relationship(back_populates="observations")


class DocumentFinding(Base):
    """A quoted passage about a topic (pipe replacement, roof, fee changes ...)."""

    __tablename__ = "document_findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"))
    topic: Mapped[str] = mapped_column(String(60))
    page_number: Mapped[int] = mapped_column(Integer)
    excerpt: Mapped[str] = mapped_column(Text)

    document: Mapped[SourceDocument] = relationship(back_populates="findings")
