"""Listing links. Boster runs in the browser and never fetches them; a link is saved for the user to open."""

from urllib.parse import urlparse

_KNOWN_SOURCES = {"hemnet.se": "Hemnet", "booli.se": "Booli"}


class InvalidListingUrl(Exception):
    """The message is shown to the user, in Swedish."""


def source_name(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    for domain, name in _KNOWN_SOURCES.items():
        if host == domain or host.endswith("." + domain):
            return name
    return host or "Okänd källa"


def validate_listing_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise InvalidListingUrl("Ange en fullständig länk som börjar med http:// eller https://.")
