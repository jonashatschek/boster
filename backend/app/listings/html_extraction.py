"""Extracting listing facts from a fetched HTML page.

The page is untrusted. It is parsed as data only: scripts are never run, and only
JSON-LD blocks (schema.org structured data) and meta tags are read from it. The
visible text then goes through the same extractor as pasted text.
"""

import json
import re
from datetime import date
from html.parser import HTMLParser

from app.listings.text_extraction import ListingFacts, extract_from_text

_STRUCTURED = "structured_data"
_SKIPPED_TAGS = {"script", "style", "noscript", "template", "svg", "head"}
_BLOCK_TAGS = {"p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "dt", "dd",
               "td", "th", "span"}


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text_parts: list[str] = []
        self.json_ld: list[str] = []
        self.meta: dict[str, str] = {}
        self.title = ""
        self._skip_depth = 0
        self._in_json_ld = False
        self._in_title = False
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        if tag == "script" and attributes.get("type") == "application/ld+json":
            self._in_json_ld, self._buffer = True, []
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            key = attributes.get("property") or attributes.get("name")
            if key and attributes.get("content"):
                self.meta[key.lower()] = attributes["content"]
        if tag in _SKIPPED_TAGS:
            self._skip_depth += 1
        if tag in _BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_json_ld:
            self.json_ld.append("".join(self._buffer))
            self._in_json_ld = False
        if tag == "title":
            self._in_title = False
        if tag in _SKIPPED_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if tag in _BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._buffer.append(data)
        elif self._in_title:
            self.title += data
        elif not self._skip_depth:
            self.text_parts.append(data)


def extract_from_html(html: str) -> tuple[ListingFacts, str]:
    """Returns the facts and the page's visible text (kept for later re-analysis)."""
    parser = _PageParser()
    parser.feed(html)
    visible_text = re.sub(r"\n\s*\n+", "\n\n", "".join(parser.text_parts)).strip()

    facts = ListingFacts()
    for block in parser.json_ld:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for item in _flatten(data):
            _read_structured(facts, item)
    _read_meta(facts, parser.meta, parser.title)
    facts.merge(extract_from_text(visible_text))
    return facts, visible_text


# Keys that lead from a listing to the apartment and its offer. Keys such as "seller"
# and "employee" are deliberately not followed: they describe the agent, whose office
# address must not be mistaken for the apartment's.
_NESTED_KEYS = ("@graph", "mainEntity", "itemOffered", "offers", "containsPlace", "product", "isRelatedTo", "about")
# Types that describe the apartment itself.
_RESIDENCE_TYPES = {"Residence", "Apartment", "House", "SingleFamilyResidence", "Accommodation", "Place",
                    "ApartmentComplex", "Product", "RealEstateListing"}


def _flatten(data: object) -> list[dict]:
    if isinstance(data, list):
        return [item for element in data for item in _flatten(element)]
    if isinstance(data, dict):
        items = [data]
        for key in _NESTED_KEYS:
            if key in data:
                items += _flatten(data[key])
        return items
    return []


def _read_structured(facts: ListingFacts, item: dict) -> None:
    types = item.get("@type", [])
    types = [types] if isinstance(types, str) else types
    excerpt = f"Strukturerad data ({', '.join(types) or 'okänd typ'})"

    if "Offer" in types and str(item.get("priceCurrency", "SEK")).upper() == "SEK":
        price = _number(item.get("price"))
        facts.set("asking_price", price if price and price >= 100_000 else None, excerpt, _STRUCTURED)
    if not _RESIDENCE_TYPES.intersection(types):
        return

    address = item.get("address")
    if isinstance(address, dict):
        facts.set("address", _text(address.get("streetAddress")), excerpt, _STRUCTURED)
        facts.set("municipality", _text(address.get("addressLocality")), excerpt, _STRUCTURED)
    floor_size = item.get("floorSize")
    if isinstance(floor_size, dict):
        facts.set("living_area", _number(floor_size.get("value")), excerpt, _STRUCTURED)
    rooms = item.get("numberOfRooms")
    facts.set("rooms", _number(rooms.get("value") if isinstance(rooms, dict) else rooms), excerpt, _STRUCTURED)
    year_built = _number(item.get("yearBuilt"))
    facts.set("construction_year", int(year_built) if year_built and 1500 < year_built < 2100 else None,
              excerpt, _STRUCTURED)
    facts.set("description", _text(item.get("description"), limit=8000), excerpt, _STRUCTURED)
    facts.set("title", _text(item.get("name")), excerpt, _STRUCTURED)
    posted = item.get("datePosted")
    if isinstance(posted, str) and re.match(r"\d{4}-\d{2}-\d{2}", posted):
        facts.set("listing_date", date.fromisoformat(posted[:10]), excerpt, _STRUCTURED)


def _read_meta(facts: ListingFacts, meta: dict[str, str], title: str) -> None:
    facts.set("title", _text(meta.get("og:title") or title), "Sidans titel", "meta_tag")
    facts.set("description", _text(meta.get("og:description") or meta.get("description"), limit=8000),
              "Sidans beskrivning (meta)", "meta_tag")


def _text(value: object, limit: int = 300) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned[:limit] or None


def _number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(" ", "").replace(" ", "").replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None
