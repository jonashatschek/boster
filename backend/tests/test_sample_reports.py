"""Regression tests against real annual reports.

Expected values were checked by hand against the printed reports. The PDFs are not
committed; run `python -m scripts.download_samples` to fetch them. Tests are skipped
when a file is missing.
"""

from functools import cache
from pathlib import Path

import pytest

from app.documents.annual_report import DocumentType, LandTenure, extract_annual_report
from app.domain.kpis import values_agree

SAMPLES = Path(__file__).parents[2] / "sample_documents"


@cache
def extraction_of(filename):
    path = SAMPLES / filename
    if not path.exists():
        pytest.skip(f"Sample document {filename} not downloaded")
    return extract_annual_report(path.read_bytes())


def figure(extraction, metric_key, fiscal_year, method_prefix="pdf_"):
    matches = [f.value for f in extraction.figures
               if f.metric_key == metric_key and f.fiscal_year == fiscal_year and f.method.value.startswith(method_prefix)]
    assert matches, f"{metric_key} {fiscal_year} not extracted"
    return matches[0]


EXPECTED = {
    "byamannen2_arsredovisning_2025.pdf": {
        "organisation_number": "769616-5187",
        "name": "Brf Byamännen 2",
        "fiscal_year": 2025,
        "land_tenure": LandTenure.LEASEHOLD,
        "figures": {
            ("interest_bearing_debt", 2025): 16_383_682,
            ("cash", 2025): 1_926_860,
            ("interest_expense", 2025): 462_843,
            ("debt_per_sqm_total_area", 2025): 1_747,
            ("debt_per_sqm_tenant_owned_area", 2025): 1_896,
            ("savings_per_sqm", 2023): -300,
            ("interest_sensitivity_pct", 2024): 3.21,
            ("total_area", 2025): 9_380,
        },
    },
    "friheten_arsredovisning_2024-2025.pdf": {
        "organisation_number": "702002-1692",
        "name": "Bostadsrättsförening Friheten Bagarmossen",
        "fiscal_year": 2025,
        "land_tenure": LandTenure.LEASEHOLD,
        "figures": {
            ("interest_bearing_debt", 2025): 32_000_000,
            ("short_term_interest_bearing_debt", 2025): 7_000_000,
            ("depreciation", 2025): 1_291_480,
            ("net_revenue", 2021): 13_485_000,  # Printed in tkr.
            ("result_after_financial_items", 2024): -6_322_000,  # Unicode minus, tkr.
            ("debt_per_sqm_total_area", 2025): 1_906,
            ("residential_area", 2025): 15_575,
            ("commercial_area", 2025): 1_215,
        },
    },
    "sannadalsplatan_arsredovisning.pdf": {
        "organisation_number": "702001-8839",
        "name": "HSB Bostadsrättföreningen Sannadalsplatån",
        "fiscal_year": 2025,
        "land_tenure": None,
        "figures": {
            ("interest_bearing_debt", 2025): 42_582_232 + 46_249_603,
            ("short_term_interest_bearing_debt", 2025): 46_249_603,
            ("debt_per_sqm_total_area", 2021): 3_233,
            ("savings_per_sqm", 2025): 271,
        },
    },
    "segelflygaren_arsredovisning.pdf": {
        "organisation_number": "716416-7939",
        "name": "HSB Bostadsrättsförening Segelflygaren i Stockholm",
        "fiscal_year": 2025,
        "land_tenure": LandTenure.LEASEHOLD,
        "figures": {
            ("interest_bearing_debt", 2025): 145_537_760,
            ("cash", 2025): 1_199,  # HSB cooperatives hold most liquidity in an HSB account, not "kassa och bank".
            ("debt_per_sqm_total_area", 2025): 3_824,
            ("result_after_financial_items", 2021): -12_544_000,
        },
    },
    "soderbysjon_arsredovisning.pdf": {
        "organisation_number": "769608-3158",
        "name": "Brf Söderbysjön",
        "fiscal_year": 2025,
        "land_tenure": LandTenure.LEASEHOLD,
        "figures": {
            ("interest_bearing_debt", 2025): 73_908_750 + 9_568_750,
            ("short_term_interest_bearing_debt", 2025): 9_568_750,
            ("interest_expense", 2025): 4_069_846,
            ("debt_per_sqm_total_area", 2025): 3_613,
            ("savings_per_sqm", 2023): 284,
            ("solidity_pct", 2025): 74.7,
            ("commercial_area", 2025): 1_792,
        },
    },
}


@pytest.mark.parametrize("filename", EXPECTED)
def test_identifies_cooperative_and_period(filename):
    extraction, expected = extraction_of(filename), EXPECTED[filename]
    assert extraction.document_type == DocumentType.ANNUAL_REPORT
    assert extraction.organisation_number == expected["organisation_number"]
    assert extraction.cooperative_name == expected["name"]
    assert extraction.fiscal_year == expected["fiscal_year"]
    assert extraction.land_tenure == expected["land_tenure"]


@pytest.mark.parametrize(
    ("filename", "metric_key", "fiscal_year"),
    [(name, metric, year) for name, expected in EXPECTED.items() for metric, year in expected["figures"]],
)
def test_extracts_figure(filename, metric_key, fiscal_year):
    expected = EXPECTED[filename]["figures"][(metric_key, fiscal_year)]
    assert figure(extraction_of(filename), metric_key, fiscal_year) == pytest.approx(expected)


@pytest.mark.parametrize("filename", EXPECTED)
def test_extracted_debt_is_consistent_with_reported_debt_per_sqm(filename):
    """Cross-check: statement debt / area implied by the printed key figure must be plausible."""
    extraction = extraction_of(filename)
    debt = figure(extraction, "interest_bearing_debt", 2025)
    debt_per_sqm = figure(extraction, "debt_per_sqm_total_area", 2025)
    implied_area = debt / debt_per_sqm
    assert 1_000 < implied_area < 100_000


def test_statement_and_key_figure_table_agree_on_result():
    extraction = extraction_of("byamannen2_arsredovisning_2025.pdf")
    from_statement = figure(extraction, "result_after_financial_items", 2025, "pdf_financial")
    from_key_figures = figure(extraction, "result_after_financial_items", 2025, "pdf_key")
    assert values_agree(from_statement, from_key_figures)


def test_conflicting_areas_in_one_report_are_both_kept():
    extraction = extraction_of("soderbysjon_arsredovisning.pdf")
    areas = {f.value for f in extraction.figures if f.metric_key == "residential_area"}
    assert areas == {26_688, 21_311}


def test_extended_fiscal_year_is_warned_about():
    extraction = extraction_of("soderbysjon_arsredovisning.pdf")
    assert any("16 månader" in warning for warning in extraction.warnings)


def test_scanned_economic_plan_is_recognised_and_not_guessed_from():
    extraction = extraction_of("byamannen_ekonomisk_plan_2025.pdf")
    assert extraction.looks_scanned
    assert extraction.figures == []
    assert any("OCR" in warning for warning in extraction.warnings)
