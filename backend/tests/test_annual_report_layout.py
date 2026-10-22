"""Extraction tests on hand-built page layouts, independent of any real PDF."""

from app.documents.annual_report import extract_from_pages
from app.documents.pdf_layout import Cell, PageLayout, Row

# Year columns, right-aligned at these x positions.
COLUMNS = {2025: 300, 2024: 360, 2023: 420}


def row(page, y, label, values=(), note=None, label_x=60):
    """A table row: label at the left, an optional note number, then values right-aligned under each year."""
    cells = [Cell(label, label_x, min(label_x + 4 * len(label), 200), y, y + 9)] if label else []
    if note:
        cells.append(Cell(note, 215, 222, y, y + 9))
    for year, text in values:
        right = COLUMNS[year]
        cells.append(Cell(text, right - 5 * len(text), right, y, y + 9))
    return Row(page, y, cells)


def header(page, y, labels=("2025", "2024", "2023")):
    return row(page, y, "", list(zip(COLUMNS, labels)))


def page(number, rows, text=""):
    text = text or "\n".join(r.text for r in rows)
    return PageLayout(number, rows, text)


COVER = page(1, [], "Årsredovisning för Brf Testgården 769600-0001\nräkenskapsåret 2025-01-01 - 2025-12-31\n" * 3)

KEY_FIGURES = page(2, [
    row(2, 50, "Flerårsöversikt"),
    header(2, 60),
    row(2, 70, "Nettoomsättning, tkr", [(2025, "12 500"), (2024, "12 000"), (2023, "11 800")]),
    row(2, 80, "Skuldsättning, kr/kvm", [(2025, "4 100"), (2024, "4 300"), (2023, "4 500")]),
    row(2, 90, "Skuldsättning bostadsrättsyta, kr/kvm", [(2025, "4 400"), (2024, "4 600"), (2023, "0")]),
    row(2, 100, "Sparande per kvm", [(2025, "180"), (2024, "-"), (2023, "150")]),
    row(2, 110, "Årsavgifternas andel i %"),
    row(2, 120, "av totala rörelseintäkter", [(2025, "85%"), (2024, "86%"), (2023, "88%")]),
])

INCOME_STATEMENT = page(3, [
    row(3, 50, "Resultaträkning"),
    header(3, 60, ("2025-12-31", "2024-12-31")),
    row(3, 70, "Nettoomsättning", [(2025, "12 512 345"), (2024, "12 001 000")], note="2"),
    row(3, 80, "Av- och nedskrivningar av materiella och"),
    row(3, 90, "immateriella anläggningstillgångar", [(2025, "-1 000 000"), (2024, "-950 000")], note="5"),
    row(3, 100, "Rörelseresultat", [(2025, "2 000 000"), (2024, "1 500 000")]),
    row(3, 110, "Räntekostnader och liknande resultatposter", [(2025, "-800 000"), (2024, "-600 000")], note="6"),
    row(3, 120, "Årets resultat", [(2025, "1 200 000"), (2024, "900 000")]),
])

BALANCE_SHEET = page(4, [
    row(4, 50, "Balansräkning"),
    header(4, 60, ("2025-12-31", "2024-12-31")),
    row(4, 70, "Kassa och bank", [(2025, "3 000 000"), (2024, "2 500 000")]),
    row(4, 80, "Summa tillgångar", [(2025, "200 000 000"), (2024, "201 000 000")]),
    row(4, 90, "Summa eget kapital", [(2025, "100 000 000"), (2024, "98 800 000")]),
    row(4, 100, "Långfristiga skulder"),
    row(4, 110, "Skulder till kreditinstitut", [(2025, "60 000 000"), (2024, "70 000 000")], note="11"),
    row(4, 120, "Kortfristiga skulder"),
    row(4, 130, "Skulder till kreditinstitut", [(2025, "20 000 000"), (2024, "12 000 000")], note="11"),
    row(4, 140, "Leverantörsskulder", [(2025, "500 000"), (2024, "400 000")]),
])

CASH_FLOW = page(5, [
    header(5, 60, ("2025-12-31", "2024-12-31")),
    row(5, 70, "Rörelseresultat", [(2025, "2 000 000"), (2024, "1 500 000")]),
    row(5, 80, "Erlagd ränta", [(2025, "-790 000"), (2024, "-600 000")]),
])

NOTES = page(6, [
    row(6, 50, "Not 11 Skulder till kreditinstitut"),
    header(6, 60, ("2025-12-31", "2024-12-31")),
    row(6, 70, "Skulder till kreditinstitut", [(2025, "99 999 999"), (2024, "99 999 999")]),
])


def extract():
    return extract_from_pages([COVER, KEY_FIGURES, INCOME_STATEMENT, BALANCE_SHEET, CASH_FLOW, NOTES])


def values(extraction, metric_key, method_prefix=""):
    return {f.fiscal_year: f.value for f in extraction.figures
            if f.metric_key == metric_key and f.method.value.startswith(method_prefix)}


def test_identifies_the_cooperative():
    extraction = extract()
    assert extraction.organisation_number == "769600-0001"
    assert extraction.cooperative_name == "Brf Testgården"


def test_key_figures_are_assigned_to_the_right_year():
    extraction = extract()
    assert values(extraction, "debt_per_sqm_total_area") == {2025: 4_100, 2024: 4_300, 2023: 4_500}


def test_key_figure_amounts_in_thousands_are_converted_to_kronor():
    extraction = extract()
    assert values(extraction, "net_revenue", "pdf_key")[2025] == 12_500_000


def test_dash_means_missing_not_zero():
    extraction = extract()
    assert values(extraction, "savings_per_sqm") == {2025: 180, 2023: 150}


def test_implausible_zero_is_treated_as_not_reported_and_warned_about():
    extraction = extract()
    assert values(extraction, "debt_per_sqm_tenant_owned_area") == {2025: 4_400, 2024: 4_600}
    assert any("2023" in warning and "0" in warning for warning in extraction.warnings)


def test_label_wrapped_over_two_lines_is_joined():
    extraction = extract()
    assert values(extraction, "fee_share_of_revenue_pct") == {2025: 85, 2024: 86, 2023: 88}
    assert values(extraction, "depreciation") == {2025: 1_000_000, 2024: 950_000}


def test_note_references_are_not_mistaken_for_amounts():
    extraction = extract()
    assert values(extraction, "net_revenue", "pdf_financial") == {2025: 12_512_345, 2024: 12_001_000}


def test_costs_are_stored_as_positive_amounts():
    extraction = extract()
    assert values(extraction, "interest_expense") == {2025: 800_000, 2024: 600_000}


def test_interest_bearing_debt_sums_long_and_short_term_rows_but_ignores_notes():
    extraction = extract()
    assert values(extraction, "interest_bearing_debt") == {2025: 80_000_000, 2024: 82_000_000}
    assert values(extraction, "short_term_interest_bearing_debt") == {2025: 20_000_000, 2024: 12_000_000}


def test_cash_flow_page_is_not_read_as_income_statement():
    extraction = extract()
    operating_results = [f for f in extraction.figures if f.metric_key == "operating_result"]
    assert {f.page_number for f in operating_results} == {3}


def test_every_figure_records_its_page_and_printed_label():
    for figure in extract().figures:
        assert figure.page_number >= 1
        assert figure.printed_label


def test_fiscal_year_comes_from_the_stated_period():
    extraction = extract()
    assert extraction.fiscal_year == 2025
    assert extraction.warnings == [w for w in extraction.warnings if "månader" not in w]  # 12 months: no warning.
