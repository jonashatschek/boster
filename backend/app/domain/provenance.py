"""Vocabulary for describing where a value came from and how far it can be trusted.

Every number the application shows is either read from a source, calculated from
other numbers, estimated, entered by the user, or missing. These enums make that
distinction explicit so that the UI never has to guess.
"""

from enum import StrEnum


class VerificationStatus(StrEnum):
    """How much confidence we have in a single value."""

    VERIFIED = "verified"  # Confirmed by the user against the source.
    EXTRACTED = "extracted"  # Read automatically from a source, not independently checked.
    USER_ENTERED = "user_entered"  # Typed in by the user.
    CALCULATED = "calculated"  # Deterministically computed from other values.
    ESTIMATED = "estimated"  # Approximation with explicit assumptions.
    MISSING = "missing"  # Not available in any source.
    CONFLICTING = "conflicting"  # Sources disagree; all candidates are kept.


class ValueOrigin(StrEnum):
    """Whether a KPI value was printed in a document or derived by this application."""

    REPORTED = "reported"  # Printed by the cooperative, e.g. in the multi-year overview.
    CALCULATED = "calculated"  # Computed by this application from base figures.


class ExtractionMethod(StrEnum):
    """Which mechanism produced an observation."""

    PDF_KEY_FIGURES_TABLE = "pdf_key_figures_table"  # Flerårsöversikt / nyckeltal.
    PDF_FINANCIAL_STATEMENT = "pdf_financial_statement"  # Resultat- och balansräkning.
    PDF_TEXT_PATTERN = "pdf_text_pattern"  # Regular expression over running text.
    MANUAL = "manual"
