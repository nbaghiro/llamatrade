"""Shared utilities for LlamaTrade services."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from collections.abc import Generator, Sequence
from datetime import UTC, datetime
from typing import TypedDict
from uuid import UUID, uuid4

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def generate_uuid() -> UUID:
    """Generate a new UUID4."""
    return uuid4()


def utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(UTC)


def generate_api_key(prefix: str = "lt") -> tuple[str, str]:
    """Generate an API key and its hash.

    Returns:
        Tuple of (api_key, api_key_hash)
    """
    key = f"{prefix}_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    return key, key_hash


def verify_api_key(api_key: str, api_key_hash: str) -> bool:
    """Verify an API key against its hash."""
    computed_hash = hashlib.sha256(api_key.encode()).hexdigest()
    return secrets.compare_digest(computed_hash, api_key_hash)


_DEV_ENCRYPTION_KEY = "default-dev-key-change-me"
_SALT_BYTES = 16
_PBKDF2_ITERATIONS = 100_000
_PROD_ENVIRONMENTS = {"production", "staging"}


def require_secret(env_var: str, dev_default: str) -> str:
    """Return a secret from the environment, refusing the dev default in prod.

    In ``production``/``staging`` (per the ``ENVIRONMENT`` var) a missing secret
    raises rather than silently using a well-known default that would permit
    forged tokens or trivially decryptable data. Local dev and tests keep the
    zero-config default.
    """
    value = os.environ.get(env_var)
    if value:
        return value
    environment = os.environ.get("ENVIRONMENT", "development").lower()
    if environment in _PROD_ENVIRONMENTS:
        raise RuntimeError(
            f"{env_var} must be set in the {environment} environment; "
            "refusing to fall back to the insecure development default"
        )
    return dev_default


def _get_fernet(encryption_key: str, salt: bytes) -> Fernet:
    """Derive a Fernet instance from the key and a per-value salt."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(encryption_key.encode()))
    return Fernet(key)


def encrypt_value(value: str, encryption_key: str | None = None) -> str:
    """Encrypt a sensitive value with a random per-value salt.

    The output is a base64 envelope of ``salt || fernet_token`` so each
    ciphertext carries its own salt. If no key is given, ``ENCRYPTION_KEY`` is
    used (required in prod via :func:`require_secret`).
    """
    if not encryption_key:
        encryption_key = require_secret("ENCRYPTION_KEY", _DEV_ENCRYPTION_KEY)

    salt = secrets.token_bytes(_SALT_BYTES)
    token = _get_fernet(encryption_key, salt).encrypt(value.encode())
    return base64.urlsafe_b64encode(salt + token).decode()


def decrypt_value(encrypted_value: str, encryption_key: str | None = None) -> str:
    """Decrypt a value produced by :func:`encrypt_value`."""
    if not encryption_key:
        encryption_key = require_secret("ENCRYPTION_KEY", _DEV_ENCRYPTION_KEY)

    raw = base64.urlsafe_b64decode(encrypted_value.encode())
    salt, token = raw[:_SALT_BYTES], raw[_SALT_BYTES:]
    return _get_fernet(encryption_key, salt).decrypt(token).decode()


class PaginatedResult[T](TypedDict):
    """Result of paginating a list."""

    items: Sequence[T]
    total: int
    page: int
    page_size: int
    total_pages: int


def paginate[T](
    items: Sequence[T],
    page: int = 1,
    page_size: int = 20,
) -> PaginatedResult[T]:
    """Paginate a list of items.

    Args:
        items: List of items to paginate
        page: Page number (1-indexed)
        page_size: Number of items per page

    Returns:
        Dict with paginated items and metadata
    """
    total = len(items)
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0

    start = (page - 1) * page_size
    end = start + page_size

    return PaginatedResult(
        items=items[start:end],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


def format_currency(value: float, currency: str = "USD") -> str:
    """Format a value as currency."""
    if currency == "USD":
        return f"${value:,.2f}"
    return f"{value:,.2f} {currency}"


def format_percent(value: float, decimals: int = 2) -> str:
    """Format a value as percentage."""
    return f"{value * 100:.{decimals}f}%"


def calculate_pnl(
    cost_basis: float,
    current_value: float,
) -> tuple[float, float]:
    """Calculate P&L and P&L percentage.

    Returns:
        Tuple of (pnl, pnl_percent)
    """
    pnl = current_value - cost_basis
    pnl_percent = (pnl / cost_basis * 100) if cost_basis != 0 else 0
    return pnl, pnl_percent


def validate_symbol(symbol: str) -> bool:
    """Validate a stock symbol format."""
    if not symbol:
        return False
    # Basic validation: 1-5 uppercase letters
    return 1 <= len(symbol) <= 5 and symbol.isalpha() and symbol.isupper()


def normalize_symbol(symbol: str) -> str:
    """Normalize a stock symbol to uppercase."""
    return symbol.strip().upper()


def chunks[T](lst: list[T], n: int) -> Generator[list[T]]:
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]
