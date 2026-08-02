"""Shared session helpers: token mint, user shape, handoff, tenant/user creation."""

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import bcrypt
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from llamatrade_db.models.auth import Tenant, User

import src.session as session
from src.session import (
    SIGNING_ALGORITHM,
    SIGNING_KEY,
    PasswordPolicyError,
    create_tenant_and_user,
    mint_access_refresh,
    mint_handoff,
    user_to_dict,
    validate_password_strength,
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
    access = jwt.decode(ar.access_token, SIGNING_KEY, algorithms=[SIGNING_ALGORITHM])
    assert access["sub"] == str(u.id)
    assert access["tenant_id"] == str(u.tenant_id)
    assert access["type"] == "access"
    assert access["email"] == "a@b.com"
    assert access["roles"] == ["admin"]
    refresh = jwt.decode(ar.refresh_token, SIGNING_KEY, algorithms=[SIGNING_ALGORITHM])
    assert refresh["type"] == "refresh"


def test_mint_access_refresh_tokens_carry_unique_jti() -> None:
    ar = mint_access_refresh(_user())
    access = jwt.decode(ar.access_token, SIGNING_KEY, algorithms=[SIGNING_ALGORITHM])
    refresh = jwt.decode(ar.refresh_token, SIGNING_KEY, algorithms=[SIGNING_ALGORITHM])
    assert access["jti"]
    assert refresh["jti"]
    assert access["jti"] != refresh["jti"]

    second = jwt.decode(
        mint_access_refresh(_user()).access_token, SIGNING_KEY, algorithms=[SIGNING_ALGORITHM]
    )
    assert second["jti"] != access["jti"]


def test_user_to_dict_shape() -> None:
    u = _user()
    d = user_to_dict(u)
    assert d["id"] == str(u.id)
    assert d["tenantId"] == str(u.tenant_id)
    assert d["email"] == "a@b.com"
    assert d["roles"] == ["admin"]


def test_handoff_roundtrip() -> None:
    uid = str(uuid4())
    handoff = verify_handoff(mint_handoff(uid))
    assert handoff is not None
    assert handoff.user_id == uid
    assert handoff.jti


def test_handoff_jti_unique_per_mint() -> None:
    uid = str(uuid4())
    first = verify_handoff(mint_handoff(uid))
    second = verify_handoff(mint_handoff(uid))
    assert first is not None and second is not None
    assert first.jti != second.jti


def test_handoff_rejects_garbage() -> None:
    assert verify_handoff("nope") is None


def test_handoff_rejects_wrong_purpose() -> None:
    tok = jwt.encode(
        {"purpose": "other", "sub": "x", "exp": 9999999999},
        SIGNING_KEY,
        algorithm=SIGNING_ALGORITHM,
    )
    assert verify_handoff(tok) is None


class TestValidatePasswordStrength:
    def test_accepts_strong_password(self) -> None:
        validate_password_strength("SecurePass123")

    def test_rejects_short_password(self) -> None:
        with pytest.raises(PasswordPolicyError):
            validate_password_strength("Ab1")

    def test_rejects_password_without_digit(self) -> None:
        with pytest.raises(PasswordPolicyError):
            validate_password_strength("OnlyLetters")

    def test_rejects_password_without_letter(self) -> None:
        with pytest.raises(PasswordPolicyError):
            validate_password_strength("12345678")


class _FakeSession:
    """Records added ORM objects; answers the duplicate-email lookup."""

    def __init__(self, existing_user: User | None = None) -> None:
        self.existing_user = existing_user
        self.added: list[object] = []

    async def scalar(self, stmt: object) -> User | None:
        return self.existing_user

    async def flush(self) -> None:
        pass

    def add(self, obj: object) -> None:
        self.added.append(obj)


class TestCreateTenantAndUser:
    async def test_creates_admin_user_and_tenant(self) -> None:
        db = _FakeSession()

        user, tenant = await create_tenant_and_user(
            db,
            email="new@example.com",
            password="SecurePass123",
            tenant_name="Acme Trading",
            first_name="New",
            last_name="User",
        )

        assert isinstance(user, User)
        assert isinstance(tenant, Tenant)
        assert user.tenant_id == tenant.id
        assert user.role == "admin"
        assert user.is_active is True
        assert tenant.slug.startswith("acme-trading-")
        assert bcrypt.checkpw(b"SecurePass123", user.password_hash.encode())
        assert db.added == [tenant, user]

    async def test_weak_password_rejected_before_db_access(self) -> None:
        db = MagicMock()
        with pytest.raises(PasswordPolicyError):
            await create_tenant_and_user(db, email="x@y.com", password="short", tenant_name="T")
        db.scalar.assert_not_called()
        db.add.assert_not_called()

    async def test_taken_email_raises_value_error(self) -> None:
        db = _FakeSession(existing_user=_user())
        with pytest.raises(ValueError, match="email_taken"):
            await create_tenant_and_user(
                db, email="a@b.com", password="SecurePass123", tenant_name="T"
            )
        assert db.added == []


def _expired_handoff() -> str:
    now = int(datetime.now(UTC).timestamp())
    return jwt.encode(
        {"purpose": "alpaca_oauth_handoff", "sub": str(uuid4()), "jti": "j", "exp": now - 5},
        SIGNING_KEY,
        algorithm=SIGNING_ALGORITHM,
    )


def test_handoff_rejects_expired() -> None:
    assert verify_handoff(_expired_handoff()) is None


def _rsa_pair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private_pem, public_pem


class TestAsymmetricSigning:
    """Mint paths sign RS256 when the keypair is configured."""

    @pytest.fixture
    def rs256_keys(self, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
        private_pem, public_pem = _rsa_pair()
        monkeypatch.setattr(session, "SIGNING_KEY", private_pem)
        monkeypatch.setattr(session, "SIGNING_ALGORITHM", "RS256")
        monkeypatch.setattr(session, "VERIFY_KEY", public_pem)
        monkeypatch.setattr(session, "VERIFY_ALGORITHM", "RS256")
        return private_pem, public_pem

    def test_access_refresh_signed_rs256(self, rs256_keys: tuple[str, str]) -> None:
        _, public_pem = rs256_keys
        ar = mint_access_refresh(_user())
        assert jwt.get_unverified_header(ar.access_token)["alg"] == "RS256"
        access = jwt.decode(ar.access_token, public_pem, algorithms=["RS256"])
        assert access["type"] == "access"
        refresh = jwt.decode(ar.refresh_token, public_pem, algorithms=["RS256"])
        assert refresh["type"] == "refresh"

    def test_handoff_round_trips_rs256(self, rs256_keys: tuple[str, str]) -> None:
        uid = str(uuid4())
        token = mint_handoff(uid)
        assert jwt.get_unverified_header(token)["alg"] == "RS256"
        handoff = verify_handoff(token)
        assert handoff is not None
        assert handoff.user_id == uid

    def test_hs256_handoff_rejected_when_rs256_pinned(self, rs256_keys: tuple[str, str]) -> None:
        forged = jwt.encode(
            {
                "purpose": "alpaca_oauth_handoff",
                "sub": str(uuid4()),
                "jti": "j",
                "exp": int(datetime.now(UTC).timestamp()) + 60,
            },
            "a-shared-hmac-secret-that-is-32-bytes!!",
            algorithm="HS256",
        )
        assert verify_handoff(forged) is None
