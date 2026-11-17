"""Waitlist rules that need no database: email checks, sources, IP hashing, CSV output."""

from __future__ import annotations

import io
from datetime import UTC, datetime

import pytest

from llamatrade_db.models.auth import WaitlistEntry

from src.services.waitlist import (
    WaitlistValidationError,
    hash_ip,
    normalize_email,
    resolve_source,
    validate_waitlist_email,
)
from src.tools.waitlist import build_parser, write_csv


async def test_normalize_email_trims_and_lowercases() -> None:
    assert normalize_email("  Person@Example.COM \n") == "person@example.com"


@pytest.mark.parametrize(
    "raw",
    ["you@example.com", " You@Example.com ", "first.last+tag@sub.example.org"],
)
async def test_valid_emails_come_back_normalised(raw: str) -> None:
    assert validate_waitlist_email(raw) == raw.strip().lower()


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "you",
        "you@",
        "@example.com",
        "you@example",
        "a b@c.d",
        "a@b c.d",
        "you@@example.com",
        "you@example..com",
        f"{'a' * 310}@example.com",
    ],
)
async def test_invalid_emails_are_rejected(raw: str) -> None:
    with pytest.raises(WaitlistValidationError, match="valid email"):
        validate_waitlist_email(raw)


async def test_source_defaults_to_landing_and_is_normalised() -> None:
    assert resolve_source("") == "landing"
    assert resolve_source("  ") == "landing"
    assert resolve_source("JOIN") == "join"
    assert resolve_source("landing") == "landing"


async def test_unknown_source_is_rejected() -> None:
    with pytest.raises(WaitlistValidationError, match="source"):
        resolve_source("twitter")


async def test_hash_ip_is_stable_and_never_the_raw_address() -> None:
    digest = hash_ip("203.0.113.7")
    assert digest is not None
    assert len(digest) == 64
    assert "203.0.113.7" not in digest
    assert digest == hash_ip("203.0.113.7")
    assert digest != hash_ip("203.0.113.8")


async def test_hash_ip_without_an_address() -> None:
    assert hash_ip(None) is None
    assert hash_ip("") is None


async def test_write_csv_has_header_and_iso_timestamps() -> None:
    created = datetime(2026, 11, 16, 9, 30, tzinfo=UTC)
    invited = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)
    entries = [
        WaitlistEntry(
            email="a@example.com", source="landing", status="waiting", created_at=created
        ),
        WaitlistEntry(
            email="b@example.com",
            source="join",
            status="invited",
            created_at=created,
            invited_at=invited,
        ),
    ]
    out = io.StringIO()
    write_csv(entries, out)
    assert out.getvalue().splitlines() == [
        "email,source,status,created_at,invited_at",
        "a@example.com,landing,waiting,2026-11-16T09:30:00+00:00,",
        "b@example.com,join,invited,2026-11-16T09:30:00+00:00,2026-11-17T10:00:00+00:00",
    ]


async def test_parser_accepts_list_and_invite() -> None:
    parser = build_parser()
    assert parser.parse_args(["list"]).status is None
    assert parser.parse_args(["list", "--status", "invited"]).status == "invited"
    assert parser.parse_args(["invite", "x@example.com"]).email == "x@example.com"
    with pytest.raises(SystemExit):
        parser.parse_args(["list", "--status", "bogus"])
