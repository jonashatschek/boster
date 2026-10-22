import pytest

from app.documents.number_parsing import is_empty_cell, parse_fiscal_year_label, parse_swedish_number


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3 364 151", 3_364_151),
        ("-3 364 151", -3_364_151),
        ("−6 322", -6_322),  # Unicode minus sign.
        ("–797", -797),  # En dash used as minus.
        ("74,7%", 74.7),
        ("2,3", 2.3),
        ("18 681,062", 18_681.062),
        ("0", 0),
        ("1 906", 1_906),  # Non-breaking space as thousands separator.
    ],
)
def test_parses_swedish_numbers(text, expected):
    assert parse_swedish_number(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["", "-", "Not", "12 34", "1,2,3", "kr/kvm", "2024-08-31"])
def test_rejects_non_numbers(text):
    assert parse_swedish_number(text) is None


@pytest.mark.parametrize("text", ["-", "−", "–", "saknas"])
def test_recognises_empty_cell_markers(text):
    assert is_empty_cell(text)


@pytest.mark.parametrize(
    ("label", "fiscal_year"),
    [
        ("2025", 2025),
        ("2024/2025", 2025),
        ("2024 - 2025", 2025),
        ("2024/25", 2025),
        ("2025-08-31", 2025),
        ("2024-09-01 - 2025-08-31", 2025),
        ("2025-12-31", 2025),
    ],
)
def test_parses_fiscal_year_labels(label, fiscal_year):
    assert parse_fiscal_year_label(label) == fiscal_year


@pytest.mark.parametrize("label", ["Not", "1 906", "12", "kr/kvm", "202"])
def test_rejects_non_period_labels(label):
    assert parse_fiscal_year_label(label) is None
