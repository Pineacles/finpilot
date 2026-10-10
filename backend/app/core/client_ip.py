"""Real client IP for rate limiting.

The API sits behind the Next.js proxy (and, in production, a Cloudflare
tunnel), so the direct TCP peer is always the proxy. Forwarded headers are
honoured only when the direct peer is on a private/loopback network (the
docker network or localhost); otherwise the peer address itself is used, so a
caller that reaches the API directly cannot spoof its own bucket.
"""

import ipaddress

from starlette.requests import Request


def _parse(value: str):
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _is_internal(ip) -> bool:
    return ip.is_private or ip.is_loopback or ip.is_link_local


def get_client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    peer_ip = _parse(peer)
    if peer_ip is None or not _is_internal(peer_ip):
        return peer

    cf = _parse(request.headers.get("cf-connecting-ip", ""))
    if cf is not None:
        return str(cf)

    # X-Forwarded-For: walk from the right, skipping our own internal hops;
    # the first public address is the client as seen by the outermost proxy.
    xff = request.headers.get("x-forwarded-for", "")
    for part in reversed([p for p in xff.split(",") if p.strip()]):
        ip = _parse(part)
        if ip is None:
            break
        if not _is_internal(ip):
            return str(ip)
    return peer
