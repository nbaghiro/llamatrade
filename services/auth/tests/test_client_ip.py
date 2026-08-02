"""Trusted-position client-IP derivation from X-Forwarded-For."""

from src.client_ip import trusted_client_ip


def test_gcp_topology_selects_second_to_last() -> None:
    """Default (1 trusted hop): the LB appends <client>, <lb>; read <client>."""
    assert trusted_client_ip("1.2.3.4, 10.0.0.1") == "1.2.3.4"


def test_spoofed_leftmost_hops_are_ignored() -> None:
    """Client-supplied leftmost hops cannot rotate the derived IP."""
    assert trusted_client_ip("9.9.9.9, 8.8.8.8, 1.2.3.4, 10.0.0.1") == "1.2.3.4"


def test_empty_header_returns_none() -> None:
    assert trusted_client_ip("") is None


def test_only_infrastructure_hop_returns_none() -> None:
    """Fewer entries than the trusted-hop count implies: nothing to trust."""
    assert trusted_client_ip("10.0.0.1") is None


def test_whitespace_and_blank_entries_are_trimmed() -> None:
    assert trusted_client_ip("  1.2.3.4 ,  10.0.0.1 ") == "1.2.3.4"


def test_configurable_trusted_hop_count() -> None:
    """With two trusted hops the client IP moves one entry further left."""
    assert trusted_client_ip("1.2.3.4, 172.16.0.1, 10.0.0.1", trusted_hops=2) == "1.2.3.4"
    assert trusted_client_ip("1.2.3.4, 10.0.0.1", trusted_hops=2) is None
