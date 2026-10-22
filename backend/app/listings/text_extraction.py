"""Extracting apartment facts from the text of a Swedish property listing.

Works on text pasted by the user (select all + copy on Hemnet, Booli or an agent's
site) and on text extracted from a fetched page. Listings present facts as label/value
pairs: on one line ("Boarea: 54 m²") or on two ("Boarea" / "54 m²"). Only explicit
statements are used. A feature such as a balcony is never inferred from its absence
or from what is typical for similar apartments.
"""

import re
from dataclasses import dataclass, field
from datetime import date

from app.documents.number_parsing import parse_swedish_number


@dataclass(frozen=True)
class ExtractedField:
    value: object
    excerpt: str  # The text the value was read from, shown as evidence.
    method: str  # "text_label", "structured_data", ...
    note: str | None = None


@dataclass
class ListingFacts:
    fields: dict[str, ExtractedField] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def set(self, name: str, value: object, excerpt: str, method: str, note: str | None = None) -> None:
        if value is not None and name not in self.fields:
            self.fields[name] = ExtractedField(value, excerpt.strip()[:300], method, note)

    def merge(self, other: "ListingFacts") -> None:
        """Fill fields that are still missing from another extraction."""
        for name, extracted in other.fields.items():
            self.fields.setdefault(name, extracted)
        self.warnings += other.warnings


# Field labels as they appear on Hemnet, Booli and agents' sites. Matched at the start of a
# line, case-insensitively, optionally followed by ":".
_LABELS: dict[str, str] = {
    "asking_price": r"utgångspris|begärt pris|pris",
    "living_area": r"boarea|boyta|bostadsarea|storlek|yta",
    "rooms": r"antal rum|rum",
    "floor": r"våning|våningsplan|plan",
    "elevator": r"hiss",
    "balcony": r"balkong|balkong/uteplats|uteplats/balkong|uteplats|terrass",
    "monthly_fee": r"månadsavgift|avgift/månad|avgift",
    "fee_includes": r"i avgiften ingår|avgiften inkluderar|ingår i avgiften",
    "construction_year": r"byggår|byggnadsår|byggt",
    "energy_class": r"energiklass|energiprestanda",
    "cooperative_name": r"bostadsrättsförening|förening|brf",
    "municipality": r"kommun",
    "neighborhood": r"område|stadsdel",
    "listing_date": r"publicerad|inlagd|upplagd|annonsdatum",
    "address": r"adress",
}
_LABEL_LINE = {
    name: re.compile(rf"^(?:{pattern})(?![\wåäöÅÄÖ])\s*:?\s*(?P<rest>.*)$", re.IGNORECASE)
    for name, pattern in _LABELS.items()
}
# A label must be followed by its value, not by more prose: "Förening" is a label,
# "Föreningen har nyligen renoverat ..." is not.
_MAX_VALUE_LENGTH = 120

# Smallest plausible values; anything below is another number on the same line.
_MIN_PRICE = 100_000
_MIN_MONTHLY_FEE = 100

_SWEDISH_MONTHS = {
    "januari": 1, "februari": 2, "mars": 3, "april": 4, "maj": 5, "juni": 6, "juli": 7, "augusti": 8,
    "september": 9, "oktober": 10, "november": 11, "december": 12,
}
_STREET_SUFFIXES = (r"gatan|vägen|gränd|gränden|backe|backen|torg|torget|plan|allé|allén|stigen|stig|"
                    r"leden|kajen|strand|stranden|esplanaden|promenaden|terrassen|liden|slingan|gången|väg|gata")
_ADDRESS = re.compile(rf"^[A-ZÅÄÖ][\wåäöéü.\- ]*?(?:{_STREET_SUFFIXES})\s+\d+[A-Za-z]?(?:\s*[-,].*)?$")
# "Södermalm, Stockholms kommun". The municipality is kept as printed, with "kommun":
# removing a genitive "s" would break names such as Vännäs.
_MUNICIPALITY_LINE = re.compile(r"^(?P<area>[^,]{2,60}),\s*(?P<municipality>[\wåäöÅÄÖ\- ]+?\s+kommun)$", re.IGNORECASE)


def extract_from_text(text: str) -> ListingFacts:
    facts = ListingFacts()
    lines = [_clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]

    for index, line in enumerate(lines):
        for name, pattern in _LABEL_LINE.items():
            match = pattern.match(line)
            if not match:
                continue
            rest = match["rest"].strip()
            # The value is on the same line, or (Hemnet's layout) on the next one.
            value_text = rest if rest else (lines[index + 1] if index + 1 < len(lines) else "")
            if not value_text or len(value_text) > _MAX_VALUE_LENGTH or _is_label(value_text):
                continue
            excerpt = f"{line} {value_text}" if not rest else line
            _parse_field(facts, name, value_text, excerpt)
            break

    _find_address_and_area(facts, lines)
    _find_unlabelled_price(facts, lines)
    _find_description(facts, text)
    return facts


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.replace(" ", " ")).strip()


def _is_label(text: str) -> bool:
    return any(pattern.match(text) and not pattern.match(text)["rest"] for pattern in _LABEL_LINE.values())


def _parse_field(facts: ListingFacts, name: str, value_text: str, excerpt: str) -> None:
    method = "text_label"
    lowered = value_text.lower()
    if name == "asking_price":
        if re.search(r"kr\s*/\s*(m²|m2|kvm)", lowered):  # "Pris/m²" row, not the price.
            return
        facts.set(name, _parse_amount(value_text, minimum=_MIN_PRICE), excerpt, method)
    elif name == "living_area":
        facts.set(name, _parse_area(value_text), excerpt, method)
    elif name == "rooms":
        match = re.search(r"(\d+(?:[,.]5)?)", value_text)
        if match and ("rum" in lowered or re.fullmatch(r"\d+(?:[,.]5)?", value_text.strip())):
            facts.set(name, float(match.group(1).replace(",", ".")), excerpt, method)
    elif name == "floor":
        facts.set(name, value_text[:40], excerpt, method)
        elevator = _yes_no_phrase(lowered, r"hiss finns|med hiss", r"ingen hiss|hiss saknas|utan hiss")
        facts.set("elevator", elevator, excerpt, method)
    elif name in ("elevator", "balcony"):
        answer = _yes_no(lowered)
        if answer is None and name == "balcony" and not re.search(r"\bnej\b|saknas|finns ej", lowered):
            # "Balkong: Inglasad i söderläge" states that there is one.
            answer = True
        facts.set(name, answer, excerpt, method)
        if name == "balcony" and answer:
            facts.set("balcony_description", value_text[:80], excerpt, method)
    elif name == "monthly_fee":
        if "år" in lowered and "mån" not in lowered:  # "Driftkostnad 4 800 kr/år" style.
            return
        facts.set(name, _parse_amount(value_text, minimum=_MIN_MONTHLY_FEE), excerpt, method)
    elif name == "fee_includes":
        facts.set(name, value_text, excerpt, method)
    elif name == "construction_year":
        match = re.search(r"\b(1[6-9]\d{2}|20\d{2})\b", value_text)
        facts.set(name, int(match.group(1)) if match else None, excerpt, method)
    elif name == "energy_class":
        match = re.match(r"^([A-G])\b", value_text.strip())
        facts.set(name, match.group(1) if match else None, excerpt, method)
    elif name == "cooperative_name":
        facts.set(name, _clean_cooperative_name(value_text), excerpt, method)
    elif name == "listing_date":
        facts.set(name, _parse_date(value_text), excerpt, method)
    elif name in ("municipality", "neighborhood", "address"):
        facts.set(name, value_text[:100], excerpt, method)


def _parse_amount(text: str, minimum: float) -> float | None:
    """The first amount in the text, ignoring numbers too small to be what we look for."""
    match = re.search(r"(\d{1,3}(?:[  ]\d{3})+|\d+)\s*(kr|:-|sek)?", text, re.IGNORECASE)
    if not match:
        return None
    value = parse_swedish_number(match.group(1))
    return value if value is not None and value >= minimum else None


def _parse_area(text: str) -> float | None:
    match = re.search(r"(\d+(?:[,.]\d+)?)\s*(m²|m2|kvm|kvadratmeter)", text, re.IGNORECASE)
    return float(match.group(1).replace(",", ".")) if match else None


def _yes_no(text: str) -> bool | None:
    if re.match(r"^\s*(ja|finns|yes)\b", text):
        return True
    if re.match(r"^\s*(nej|saknas|finns ej|finns inte|no)\b", text):
        return False
    return None


def _yes_no_phrase(text: str, yes_pattern: str, no_pattern: str) -> bool | None:
    if re.search(no_pattern, text):
        return False
    if re.search(yes_pattern, text):
        return True
    return None


def _clean_cooperative_name(text: str) -> str | None:
    name = re.sub(r"\b(visa|läs mer|om) (föreningen|förening).*$", "", text, flags=re.IGNORECASE).strip(" ,.-")
    if len(name) < 3 or not re.search(r"[A-Za-zÅÄÖåäö]", name):
        return None
    return name[:120]


def _parse_date(text: str) -> date | None:
    iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            return None
    swedish = re.search(r"(\d{1,2})\s+([a-zåäö]+)\s+(\d{4})", text.lower())
    if swedish and swedish.group(2) in _SWEDISH_MONTHS:
        try:
            return date(int(swedish.group(3)), _SWEDISH_MONTHS[swedish.group(2)], int(swedish.group(1)))
        except ValueError:
            return None
    return None


def _find_address_and_area(facts: ListingFacts, lines: list[str]) -> None:
    """Listings start with the address, often followed by "Area, X kommun"."""
    for index, line in enumerate(lines[:40]):
        if "address" not in facts.fields and _ADDRESS.match(line) and len(line) < 80:
            facts.set("address", line, line, "text_pattern")
        match = _MUNICIPALITY_LINE.match(line)
        if match:
            facts.set("neighborhood", match["area"].strip(), line, "text_pattern")
            facts.set("municipality", match["municipality"].strip(), line, "text_pattern")


def _find_unlabelled_price(facts: ListingFacts, lines: list[str]) -> None:
    """Hemnet shows the asking price without a label, right below the address."""
    if "asking_price" in facts.fields:
        return
    for line in lines[:25]:
        if re.fullmatch(r"\d{1,3}(?: \d{3}){1,3} kr", line):
            facts.set("asking_price", _parse_amount(line, minimum=_MIN_PRICE), line, "text_pattern",
                      note="Beloppet saknade etikett i annonsen och tolkades som utgångspris. Kontrollera.")
            return


def _find_description(facts: ListingFacts, text: str) -> None:
    """The agent's description: the longest run of prose in the listing."""
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    prose = [p for p in paragraphs if len(p) > 200 and p.count(".") >= 2]
    if not prose:
        lines = [_clean_line(line) for line in text.splitlines()]
        prose = [line for line in lines if len(line) > 200 and line.count(".") >= 2]
    if prose:
        description = max(prose, key=len)
        facts.set("description", description[:8000], description[:200], "text_pattern")
