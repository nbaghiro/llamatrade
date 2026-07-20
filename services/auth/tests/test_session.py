"""Shared session helpers: token mint, user shape, handoff."""

from uuid import uuid4

import jwt

from llamatrade_db.models.auth import User

from src.session import (
    JWT_ALGORITHM,
    JWT_SECRET,
    mint_access_refresh,
    mint_handoff,
    user_to_dict,
    verify_handoff,
)


def _user() -> User:
    return User(
        id=uuid4(),
        tenant_id=uuid4(),
        email="a@b.com",
        password_hash="x",
        role="admin",
        is_active=True,
    )


def test_mint_access_refresh_claims() -> None:
    u = _user()
    ar = mint_access_refresh(u)
    access = jwt.decode(ar.access_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    assert access["sub"] == str(u.id)
    assert access["tenant_id"] == str(u.tenant_id)
    assert access["type"] == "access"
    assert access["email"] == "a@b.com"
    assert access["roles"] == ["admin"]
    refresh = jwt.decode(ar.refresh_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    assert refresh["type"] == "refresh"


def test_user_to_dict_shape() -> None:
    u = _user()
    d = user_to_dict(u)
    assert d["id"] == str(u.id)
    assert d["tenantId"] == str(u.tenant_id)
    assert d["email"] == "a@b.com"
    assert d["roles"] == ["admin"]


def test_handoff_roundtrip() -> None:
    uid = str(uuid4())
    assert verify_handoff(mint_handoff(uid)) == uid


def test_handoff_rejects_garbage() -> None:
    assert verify_handoff("nope") is None


def test_handoff_rejects_wrong_purpose() -> None:
    tok = jwt.encode(
        {"purpose": "other", "sub": "x", "exp": 9999999999}, JWT_SECRET, algorithm=JWT_ALGORITHM
    )
    assert verify_handoff(tok) is None
