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
    "asking_price": r"utgångspris|utropspris|begärt pris|pris",
    "living_area": r"boarea|boyta|bostadsarea|storlek|yta",
    "rooms": r"antal rum|rum",
    "floor": r"våning|våningsplan|plan",
    "elevator": r"hiss",
    "balcony": r"balkong|balkong/uteplats|uteplats/balkong|uteplats|terrass",
    "monthly_fee": r"månadsavgift|avgift/månad|avgift",
    "fee_includes": r"i avgiften ingår|i månadsavgiften ingår|avgiften inkluderar|ingår i avgiften",
    "fee_changes": r"kommande avgiftsförändringar|avgiftsförändringar|avgiftsförändring|planerade avgiftshöjningar",
    "construction_year": r"byggår|byggnadsår|byggt",
    "energy_class": r"energiklass|energiprestanda",
    # "Brf X" lines are handled by the name pattern below, which keeps the "Brf" prefix.
    "cooperative_name": r"bostadsrättsförening|förening",
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
_MAX_VALUE_LENGTH_BY_FIELD = {"fee_changes": 400, "fee_includes": 250}
# "Mobil:" or "E-post:" on the line after "Adress:" is the next label, not a value.
_LOOKS_LIKE_LABEL = re.compile(r"^[\wåäöÅÄÖ /()-]{1,30}:$")

# Sentences used instead of labels, e.g. on Booli: "Den ligger på våning 3 av 3".
_SENTENCES: list[tuple[str, re.Pattern]] = [
    ("floor", re.compile(r"^den ligger på våning (?P<value>.{1,40})$", re.IGNORECASE)),
    ("cooperative_name", re.compile(r"^föreningen heter (?P<value>.{3,120})$", re.IGNORECASE)),
]
# "Lägenhet · Bagarmossen · Stockholm" under the address on Booli.
_BOOLI_LOCATION = re.compile(r"^(?:lägenhet|bostadsrätt|radhus|villa|parhus|kedjehus)\s*·\s*(?P<area>[^·]{2,60})\s*·\s*"
                             r"(?P<municipality>[^·]{2,60})$", re.IGNORECASE)
# A cooperative name anywhere in the text: "Brf Gästfriheten", "HSB Brf Toppsockret".
_COOPERATIVE_NAME = re.compile(
    r"(?<![\wåäö])((?:HSB |Riksbyggens )?(?:Brf|BRF|Bostadsrättsföreningen|Bostadsrättsförening)\s+"
    r"[A-ZÅÄÖ][\wåäöÅÄÖé-]*(?:\s+(?:i\s+[A-ZÅÄÖ][\wåäö]+|\d{1,3}(?![\d-])|[A-ZÅÄÖ][\wåäöÅÄÖé-]*))?)"
)

# Smallest plausible values; anything below is another number on the same line.
_MIN_PRICE = 100_000
_MIN_MONTHLY_FEE = 100

_SWEDISH_MONTHS = {
    "januari": 1, "februari": 2, "mars": 3, "april": 4, "maj": 5, "juni": 6, "juli": 7, "augusti": 8,
    "september": 9, "oktober": 10, "november": 11, "december": 12,
}
_STREET_SUFFIXES = (r"gatan|vägen|gränd|gränden|backe|backen|torg|torget|plan|allé|allén|stigen|stig|"
                    r"leden|kajen|strand|stranden|esplanaden|promenaden|terrassen|liden|slingan|gången|väg|gata|"
                    r"lunden|platsen|parken|höjden|ringen")
# What may follow the house number: anything after a comma or dash ("12, 3 tr"), or, without one,
# only a flat number, a floor or a floor abbreviation ("151 lgh 1102", "12 3 tr", "8 nb").
_ADDRESS_TAIL = r"(?:\s*[-,].*|\s+(?:lgh\.?\s*\d+|\d+\s*(?:tr|trappor|vån|våning)\.?|nb|bv|ög)\b.*)?"
# The street word may be capitalised ("Kungsholms Strand 5", "RINGVÄGEN 12"); the name must start
# with a capital letter. A house letter may follow the number, with or without a space ("3A", "3 A").
_ADDRESS = re.compile(
    rf"^[A-ZÅÄÖ][\wåäöéü.\- ]*?(?i:{_STREET_SUFFIXES})\s+\d+(?:\s?[A-Za-z])?{_ADDRESS_TAIL}$"
)
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
            value_text = value_text.lstrip(": ").strip()  # "Månadsavgift" / ": 3 348 kr/månad".
            max_length = _MAX_VALUE_LENGTH_BY_FIELD.get(name, _MAX_VALUE_LENGTH)
            if (not value_text or len(value_text) > max_length or _is_label(value_text)
                    or _LOOKS_LIKE_LABEL.match(value_text)):
                continue
            excerpt = f"{line} {value_text}" if not rest else line
            _parse_field(facts, name, value_text, excerpt)
            break

    for line in lines:
        for name, pattern in _SENTENCES:
            match = pattern.match(line)
            if match:
                _parse_field(facts, name, match["value"], line)
    _find_address_and_area(facts, lines)
    _find_cooperative_name(facts, lines)
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
        # The negative phrases are checked first: "hiss finns ej" contains "hiss finns".
        elevator = _yes_no_phrase(lowered, r"hiss finns|med hiss",
                                  r"hiss finns ej|hiss finns inte|ingen hiss|hiss saknas|utan hiss")
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
    elif name in ("fee_includes", "fee_changes"):
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
    name = re.sub(r"\b(visa|läs mer|om) (föreningen|förening).*$", "", text, flags=re.IGNORECASE)
    name = re.split(r"\s+[-–]\s+", name)[0].strip(" ,.-")  # "Brf X - Årsredovisning 2024".
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


# Where the listing itself ends and other listings or the site footer begin. Addresses after
# this point belong to other apartments or to the agency's office.
_END_OF_LISTING = re.compile(r"^(andra har också tittat på|footer)$", re.IGNORECASE)


def _find_address_and_area(facts: ListingFacts, lines: list[str]) -> None:
    """The address, then "Area, X kommun" or "Lägenhet · Area · City", come early in the listing.

    Some sites put a long menu and image captions first, so the whole listing is searched,
    but never past the start of other listings or the footer.
    """
    for line in lines:
        if _END_OF_LISTING.match(line):
            break
        if "address" not in facts.fields and _ADDRESS.match(line) and len(line) < 80:
            facts.set("address", line, line, "text_pattern")
        match = _MUNICIPALITY_LINE.match(line) or _BOOLI_LOCATION.match(line)
        if match:
            facts.set("neighborhood", match["area"].strip(), line, "text_pattern")
            facts.set("municipality", match["municipality"].strip(), line, "text_pattern")


def _find_cooperative_name(facts: ListingFacts, lines: list[str]) -> None:
    """When no label names the cooperative, use the first "Brf X" in the text."""
    if "cooperative_name" in facts.fields:
        return
    for line in lines:
        match = _COOPERATIVE_NAME.search(line)
        if match:
            facts.set("cooperative_name", _clean_cooperative_name(match.group(1)), line, "text_pattern",
                      note="Föreningens namn hittades i löptexten, inte vid en etikett. Kontrollera.")
            return


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
    """The agent's description: the longest run of consecutive prose paragraphs."""
    paragraphs = [_clean_line(_drop_leading_fragments(p)) for p in re.split(r"\n\s*\n", text)]
    runs: list[list[str]] = [[]]
    for paragraph in paragraphs:
        # A short sentence such as "Varmt välkommen på visning!" only counts inside a description.
        if _is_prose(paragraph) or (runs[-1] and _is_short_sentence(paragraph)):
            runs[-1].append(paragraph)
        elif runs[-1]:
            runs.append([])
    best = max(runs, key=lambda run: sum(len(p) for p in run))
    if sum(len(p) for p in best) > 200:
        description = "\n\n".join(best)
        facts.set("description", description[:8000], best[0][:200], "text_pattern")


def _drop_leading_fragments(paragraph: str) -> str:
    """Remove labels and buttons ("Pris/m²", "Premium") directly above the first sentence."""
    lines = paragraph.strip().splitlines()
    while len(lines) > 1 and not (len(lines[0]) > 40 and lines[0].count(" ") >= 6):
        lines.pop(0)
    return "\n".join(lines)


def _is_short_sentence(paragraph: str) -> bool:
    return 10 <= len(paragraph) <= 60 and paragraph[:1].isupper() and paragraph.endswith((".", "!"))


def _is_prose(paragraph: str) -> bool:
    """Running text, as opposed to labels, values and buttons."""
    return len(paragraph) > 60 and paragraph.count(" ") >= 8 and paragraph.endswith((".", "!", "?", ")"))
