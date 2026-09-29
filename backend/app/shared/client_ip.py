"""Client IP attribution with proxy trust.

`X-Forwarded-For` is only meaningful when the TCP peer is our own gateway:
nginx appends the real client, so the RIGHT-most entry is the address nginx
saw. A direct client can write anything into that header (including a fresh
address per request, which would hand rate-limit buckets out for free), so
an untrusted peer's header is ignored outright and the peer is used.

Trusted peers = private ranges (docker/k8s gateways, office NAT) plus
loopback, overridable via TRUSTED_PROXY_CIDRS. Attribution only — never
authentication.
"""
import ipaddress
import os

_DEFAULTS = ("127.0.0.0/8", "::1/128", "10.0.0.0/8", "172.16.0.0/12",
             "192.168.0.0/16")


def _trusted_nets():
    raw = os.getenv("TRUSTED_PROXY_CIDRS", "")
    parts = [p.strip() for p in raw.split(",") if p.strip()] or list(_DEFAULTS)
    nets = []
    for p in parts:
        try:
            nets.append(ipaddress.ip_network(p, strict=False))
        except ValueError:
            continue
    return nets or [ipaddress.ip_network(c) for c in _DEFAULTS]


def client_ip(forwarded_for: str | None, peer: str | None) -> str:
    """Right-most forwarded address from a trusted peer, else the peer."""
    if peer:
        try:
            if any(ipaddress.ip_address(peer) in n for n in _trusted_nets()):
                if forwarded_for:
                    parts = [p.strip() for p in forwarded_for.split(",") if p.strip()]
                    if parts:
                        return parts[-1][:64]
        except ValueError:
            pass
    return (peer or "unknown")[:64]
