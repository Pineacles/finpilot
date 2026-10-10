"""SSRF guard: reject URLs whose host resolves to a non-public IP address.

Used before making any outbound HTTP request whose target is at least
partially user/agent-controlled (integration source_url, OAuth token_url),
to stop an attacker from pointing the sync worker at loopback, RFC1918,
link-local (including the 169.254.169.254 cloud metadata endpoint), CGNAT,
multicast, reserved, or unspecified addresses, whether IPv4 or IPv6.

Residual risk: this performs a point-in-time DNS resolution check. httpx
re-resolves the hostname itself when it actually opens the connection, so a
DNS-rebinding attacker who changes the A/AAAA record between our check and
httpx's own resolution could still reach a private address (TOCTOU). This
guard raises the bar significantly (blocks static private targets and
one-shot attacks) but is not a complete defense against an adversary who
controls DNS and can rebind mid-request.
"""

from __future__ import annotations

import asyncio
import ipaddress
from urllib.parse import urlsplit

from app.core.config import settings

_ALLOWED_SCHEMES = {"http", "https"}

# IPv4 Carrier-Grade NAT (CGNAT) range: not classified as "private" by the
# stdlib ipaddress module, so it needs an explicit check.
_CGNAT_V4 = ipaddress.ip_network("100.64.0.0/10")


def _allowed_private_hosts() -> set[str]:
    """Hostnames the operator explicitly trusts to resolve to private addresses.

    Set ALLOWED_PRIVATE_HOSTS to a comma-separated list (e.g. a local Ollama or
    SearXNG container name). Matching is on the exact lowercase hostname.
    """
    return {h.strip().lower() for h in settings.ALLOWED_PRIVATE_HOSTS.split(",") if h.strip()}


class UnsafeURLError(ValueError):
    """Raised when a URL is not safe to fetch (SSRF risk)."""


def _is_unsafe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # Unwrap IPv4-mapped IPv6 addresses (::ffff:a.b.c.d) so we evaluate the
    # embedded IPv4 address against the same rules.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped

    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True

    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT_V4:
        return True

    return False


async def assert_public_http_url(url: str, *, field: str) -> None:
    """Raise UnsafeURLError unless *url* is a public http(s) URL.

    Checks:
    - scheme is http or https
    - a host is present
    - ALL resolved IP addresses for the host are public (not loopback,
      RFC1918 private, link-local/cloud-metadata, CGNAT, multicast,
      reserved, unspecified, or their IPv6 equivalents)
    """
    if not url:
        raise UnsafeURLError(f"{field}: URL is required")

    parsed = urlsplit(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeURLError(f"{field}: URL scheme must be http or https")

    host = parsed.hostname
    if not host:
        raise UnsafeURLError(f"{field}: URL must include a host")

    if host.lower() in _allowed_private_hosts():
        return

    loop = asyncio.get_running_loop()
    try:
        addrinfo = await loop.getaddrinfo(host, None)
    except OSError as exc:
        raise UnsafeURLError(f"{field}: could not resolve host '{host}': {exc}") from exc

    if not addrinfo:
        raise UnsafeURLError(f"{field}: host '{host}' did not resolve to any address")

    for _family, _type, _proto, _canonname, sockaddr in addrinfo:
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError as exc:
            raise UnsafeURLError(f"{field}: host '{host}' resolved to an unparseable address ({ip_str!r})") from exc
        if _is_unsafe_ip(ip):
            raise UnsafeURLError(f"{field}: host '{host}' resolves to a non-public address ({ip})")
