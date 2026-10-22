"""Guards for fetching untrusted URLs on the user's behalf."""

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeUrlError(Exception):
    """The URL must not be fetched. The message is shown to the user, in Swedish."""


def check_public_http_url(url: str) -> str:
    """Return the hostname of a public http(s) URL, or raise UnsafeUrlError."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise UnsafeUrlError("Ange en fullständig länk som börjar med http:// eller https://.")
    reject_private_host(parsed.hostname)
    return parsed.hostname


def reject_private_host(hostname: str) -> None:
    """Refuse to fetch from this machine or the local network."""
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
    except socket.gaierror as error:
        raise UnsafeUrlError("Adressen kunde inte hittas. Kontrollera länken.") from error
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise UnsafeUrlError("Länkar till lokala nätverksadresser tillåts inte.")
