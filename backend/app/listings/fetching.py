"""Fetching listing pages, politely and without working around access restrictions.

Hemnet and Booli block automated requests. When a site refuses, we explain why and
ask the user to paste the listing text instead; we never retry with other headers,
solve CAPTCHAs or log in.
"""

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.net_safety import UnsafeUrlError, check_public_http_url, reject_private_host

_MAX_PAGE_BYTES = 5 * 1024 * 1024
_USER_AGENT = "Boster/0.1 (personal apartment analysis)"
_BLOCK_MARKERS = ("captcha", "cf-chl", "access denied", "are you a robot", "verify you are human")

_KNOWN_SOURCES = {"hemnet.se": "Hemnet", "booli.se": "Booli"}

PASTE_ADVICE = ("Öppna annonsen i webbläsaren, markera allt (Ctrl+A), kopiera (Ctrl+C) och klistra in texten här, "
                "eller fyll i uppgifterna manuellt.")


class ListingFetchError(Exception):
    """The page could not be fetched. The message is shown to the user, in Swedish."""


@dataclass(frozen=True)
class FetchedPage:
    url: str  # After redirects.
    html: str


def source_name(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    for domain, name in _KNOWN_SOURCES.items():
        if host == domain or host.endswith("." + domain):
            return name
    return host or "Okänd källa"


def validate_listing_url(url: str) -> None:
    try:
        check_public_http_url(url)
    except UnsafeUrlError as error:
        raise ListingFetchError(str(error)) from error


def fetch_listing_page(url: str, timeout_seconds: float) -> FetchedPage:
    validate_listing_url(url)
    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            with client.stream("GET", url, headers={"User-Agent": _USER_AGENT, "Accept-Language": "sv-SE,sv"}) as response:
                reject_private_host(response.url.host)
                if response.status_code in (401, 403, 429):
                    raise ListingFetchError(
                        f"{source_name(url)} tillåter inte automatisk hämtning av annonsen (HTTP {response.status_code}). "
                        + PASTE_ADVICE
                    )
                if response.status_code >= 400:
                    raise ListingFetchError(f"Annonsen kunde inte hämtas (HTTP {response.status_code}). " + PASTE_ADVICE)
                if "html" not in response.headers.get("content-type", "html"):
                    raise ListingFetchError("Länken leder inte till en webbsida. " + PASTE_ADVICE)
                content = bytearray()
                for chunk in response.iter_bytes():
                    content += chunk
                    if len(content) > _MAX_PAGE_BYTES:
                        raise ListingFetchError("Sidan är för stor för att läsas. " + PASTE_ADVICE)
                encoding = response.encoding or "utf-8"
                final_url = str(response.url)
    except UnsafeUrlError as error:
        raise ListingFetchError(str(error)) from error
    except httpx.TimeoutException as error:
        raise ListingFetchError("Det tog för lång tid att hämta annonsen. " + PASTE_ADVICE) from error
    except httpx.HTTPError as error:
        raise ListingFetchError("Annonsen kunde inte hämtas. " + PASTE_ADVICE) from error

    html = bytes(content).decode(encoding, errors="replace")
    if any(marker in html[:20_000].lower() for marker in _BLOCK_MARKERS) and len(html) < 200_000:
        raise ListingFetchError(
            f"{source_name(url)} visar en robotkontroll i stället för annonsen. " + PASTE_ADVICE
        )
    return FetchedPage(url=final_url, html=html)
