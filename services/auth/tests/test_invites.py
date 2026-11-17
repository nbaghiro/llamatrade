"""Invite code helpers that need no database: format, normalise, generate, link."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from src.services.invites import (
    CODE_ALPHABET,
    CODE_LENGTH,
    format_code,
    generate_code,
    invite_link,
    normalize_code,
)
from src.tools.invites import build_parser


def test_generated_codes_use_only_unambiguous_characters() -> None:
    codes = {generate_code() for _ in range(200)}
    assert len(codes) == 200
    for code in codes:
        assert len(code) == CODE_LENGTH
        assert set(code) <= set(CODE_ALPHABET)
    assert not set("01ILO") & set(CODE_ALPHABET)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ABCD-EFGH", "ABCDEFGH"),
        ("abcd efgh", "ABCDEFGH"),
        ("  abCD-efgh\t", "ABCDEFGH"),
        ("", ""),
        (" - ", ""),
    ],
)
def test_normalize_code(raw: str, expected: str) -> None:
    assert normalize_code(raw) == expected


def test_format_code_round_trips_through_normalize() -> None:
    assert format_code("ABCDEFGH") == "ABCD-EFGH"
    assert normalize_code(format_code("ABCDEFGH")) == "ABCDEFGH"


def test_invite_link_prefills_email_and_code() -> None:
    link = urlparse(invite_link("ABCDEFGH", "person+tag@example.com"))
    assert link.path == "/register"
    assert parse_qs(link.query) == {"email": ["person+tag@example.com"], "code": ["ABCD-EFGH"]}


def test_invite_link_without_email_carries_only_the_code() -> None:
    link = urlparse(invite_link("ABCDEFGH", None))
    assert parse_qs(link.query) == {"code": ["ABCD-EFGH"]}


def test_parser_create_defaults() -> None:
    args = build_parser().parse_args(["create"])
    assert args.email is None
    assert args.days == 30
    assert args.quiet is False
