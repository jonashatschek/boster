"""Database tables.

Important figures are stored as one row per (cooperative, metric, fiscal year, source)
in ``financial_observations``, so that they stay queryable and every value keeps its
own provenance. JSON is only used for supplementary messages.
"""

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
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
    properties: Mapped[list["Property"]] = relationship(back_populates="cooperative")
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


class Property(Base):
    """An apartment for sale, from a listing URL, pasted listing text, or manual entry.

    Field values are plain columns so they stay queryable. Where each value came from
    (listing text, structured data, the user) is kept per field in ``field_sources``.
    """

    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_url: Mapped[str | None] = mapped_column(Text, index=True)
    source_name: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(String(300))
    address: Mapped[str | None] = mapped_column(String(200))
    municipality: Mapped[str | None] = mapped_column(String(100))
    neighborhood: Mapped[str | None] = mapped_column(String(100))
    living_area: Mapped[float | None] = mapped_column(Float)
    rooms: Mapped[float | None] = mapped_column(Float)
    floor: Mapped[str | None] = mapped_column(String(40))
    elevator: Mapped[bool | None] = mapped_column(Boolean)
    balcony: Mapped[bool | None] = mapped_column(Boolean)
    balcony_description: Mapped[str | None] = mapped_column(String(100))
    asking_price: Mapped[float | None] = mapped_column(Float)
    monthly_fee: Mapped[float | None] = mapped_column(Float)
    fee_includes: Mapped[str | None] = mapped_column(Text)
    fee_changes: Mapped[str | None] = mapped_column(Text)  # Announced fee increases, as stated.
    construction_year: Mapped[int | None] = mapped_column(Integer)
    energy_class: Mapped[str | None] = mapped_column(String(2))
    description: Mapped[str | None] = mapped_column(Text)
    listing_date: Mapped[date | None] = mapped_column(Date)
    cooperative_name: Mapped[str | None] = mapped_column(String(200))  # As printed in the listing.
    housing_cooperative_id: Mapped[int | None] = mapped_column(
        ForeignKey("housing_cooperatives.id", ondelete="SET NULL"), index=True
    )
    # The listing text the facts were read from, kept so the analysis can be re-run.
    listing_text: Mapped[str | None] = mapped_column(Text)
    retrieval_status: Mapped[str] = mapped_column(String(20))  # RetrievalStatus value.
    retrieval_message: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Field name → {"status", "method", "excerpt", "note", "updated_at"}.
    field_sources: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    cooperative: Mapped[HousingCooperative | None] = relationship(back_populates="properties")
    transport: Mapped["TransportLookup | None"] = relationship(
        back_populates="property", cascade="all, delete-orphan", uselist=False
    )


class TransportLookup(Base):
    """The latest public transport lookup for an apartment, with what was asked and what was found.

    The query is kept so that a result can be recognised as stale when the address changes.
    """

    __tablename__ = "transport_lookups"

    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id", ondelete="CASCADE"), unique=True)
    query: Mapped[str] = mapped_column(String(300))  # The address as looked up: "Ringvägen 12, Stockholms kommun".
    stage: Mapped[str] = mapped_column(String(20))  # Next expected response, or "done" / "failed".
    message: Mapped[str | None] = mapped_column(Text)  # Why the lookup failed.
    place_label: Mapped[str | None] = mapped_column(Text)  # The match found by Nominatim.
    place_lat: Mapped[float | None] = mapped_column(Float)
    place_lon: Mapped[float | None] = mapped_column(Float)
    house_level: Mapped[bool | None] = mapped_column(Boolean)  # False: only the street was found.
    # Addresses offered to the user while the lookup waits at the "choose" stage (Nominatim's hits).
    candidates: Mapped[list | None] = mapped_column(JSON)
    truncated: Mapped[bool | None] = mapped_column(Boolean)  # The search returned as many hits as asked for.
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    property: Mapped[Property] = relationship(back_populates="transport")
    stops: Mapped[list["TransportStop"]] = relationship(
        back_populates="lookup", cascade="all, delete-orphan", order_by="TransportStop.id"
    )


class TransportStop(Base):
    """The nearest stop of one transport type (by straight line), and the walk there if routed."""

    __tablename__ = "transport_stops"

    id: Mapped[int] = mapped_column(primary_key=True)
    lookup_id: Mapped[int] = mapped_column(ForeignKey("transport_lookups.id", ondelete="CASCADE"), index=True)
    transport_type: Mapped[str] = mapped_column(String(20))  # TransportType value.
    name: Mapped[str] = mapped_column(String(200))  # As given by Trafiklab.
    ext_id: Mapped[str] = mapped_column(String(40))  # Trafiklab's stop id.
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    straight_metres: Mapped[int] = mapped_column(Integer)  # Trafiklab's distance from the address.
    walking_metres: Mapped[int | None] = mapped_column(Integer)  # From the routing service; None if no route.
    walking_seconds: Mapped[int | None] = mapped_column(Integer)

    lookup: Mapped[TransportLookup] = relationship(back_populates="stops")
