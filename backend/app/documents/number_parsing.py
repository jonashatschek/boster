"""Parsing of numbers and period labels as they are printed in Swedish annual reports."""

import re
from datetime import date

# Minus signs seen in real reports: hyphen, Unicode minus, en dash.
_MINUS_SIGNS = "-−–"
_NUMBER_PATTERN = re.compile(
    rf"^(?P<sign>[{_MINUS_SIGNS}])?\s*(?P<digits>\d{{1,3}}(?:[  ]\d{{3}})*|\d+)(?:,(?P<decimals>\d+))?\s*%?$"
)
# Tokens meaning "no value" in a table cell.
_EMPTY_CELL_TOKENS = {"-", "−", "–", "—", "n/a", "saknas"}


def parse_swedish_number(text: str) -> float | None:
    """Parse a number like ``-3 364 151``, ``74,7%`` or ``−6 322``. Returns None if not a number."""
    cleaned = text.strip().replace(" ", " ")
    match = _NUMBER_PATTERN.match(cleaned)
    if not match:
        return None
    digits = match["digits"].replace(" ", "").replace(" ", "")
    value = float(f"{digits}.{match['decimals']}" if match["decimals"] else digits)
    return -value if match["sign"] else value


def is_empty_cell(text: str) -> bool:
    return text.strip().lower() in _EMPTY_CELL_TOKENS


def is_thousands_group(text: str) -> bool:
    """Whether a token continues a number split at its thousands separator, e.g. ``951`` or ``681,062``."""
    return re.fullmatch(r"\d{3}(?:,\d+)?%?", text.strip()) is not None


# Period labels used as column headers: "2025", "2024/2025", "2024 - 2025", "2024/25",
# "2025-12-31", "2025-08" (year and closing month), or "2024-09-01 - 2025-08-31". The
# fiscal year is identified by the year in which it ends. "2011-12" is ambiguous; it is
# read as the fiscal year 2011/12, since the range pattern is tried first.
_DATE = r"(?P<{name}>\d{{4}}-\d{{2}}-\d{{2}})"
_PERIOD_PATTERNS = [
    re.compile(rf"^{_DATE.format(name='start')}\s*[-–]\s*{_DATE.format(name='end')}$"),
    re.compile(rf"^{_DATE.format(name='end')}$"),
    re.compile(r"^(?P<start_year>(?:19|20)\d{2})\s*[/–-]\s*(?P<end_year>(?:19|20)?\d{2})$"),
    re.compile(r"^(?P<end_year>(?:19|20)\d{2})-(?:0[1-9]|1[0-2])$"),
    re.compile(r"^(?P<end_year>(?:19|20)\d{2})$"),
]


def parse_fiscal_year_label(text: str) -> int | None:
    """Return the year in which the period ends, or None if the text is not a period label."""
    cleaned = text.strip().rstrip("*")
    for pattern in _PERIOD_PATTERNS:
        match = pattern.match(cleaned)
        if not match:
            continue
        groups = match.groupdict()
        if groups.get("end"):
            return date.fromisoformat(groups["end"]).year
        end_year = groups["end_year"]
        if len(end_year) == 2:
            end_year = groups["start_year"][:2] + end_year
        if groups.get("start_year") and int(end_year) != int(groups["start_year"]) + 1:
            continue  # Not a fiscal year range, e.g. "2025-08" is a year and month.
        return int(end_year)
    return None
