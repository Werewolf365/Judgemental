"""Unit tests for proxy-aware client IP attribution."""
import os

from app.shared.client_ip import client_ip


def test_untrusted_peer_ignores_spoofed_chain():
    # Direct internet client forging a chain: header ignored, peer used.
    assert client_ip("9.9.9.9", "203.0.113.7") == "203.0.113.7"
    assert client_ip("9.9.9.9, 8.8.8.8", "203.0.113.7") == "203.0.113.7"


def test_trusted_gateway_peer_uses_rightmost():
    # Bundled nginx appends the real client: last entry is the one it saw.
    assert client_ip("9.9.9.9, 10.0.0.9", "172.20.0.4") == "10.0.0.9"
    assert client_ip("203.0.113.7", "127.0.0.1") == "203.0.113.7"


def test_no_header_falls_back_to_peer():
    assert client_ip(None, "203.0.113.7") == "203.0.113.7"
    assert client_ip("", "203.0.113.7") == "203.0.113.7"
    assert client_ip(None, None) == "unknown"


def test_env_override(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "203.0.113.0/24")
    assert client_ip("9.9.9.9", "203.0.113.7") == "9.9.9.9"
    assert client_ip("9.9.9.9", "198.51.100.3") == "198.51.100.3"
    # os import at module top is enough; silence linters about unused import
    assert os.name
