"""Shared utilities for LlamaTrade services."""

import base64
import hashlib
import os
import secrets
from datetime import UTC, datetime
from typing import Any
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


def _get_fernet(encryption_key: str) -> Fernet:
    """Get Fernet instance from encryption key."""
    # Derive a proper key from the provided key
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"llamatrade_salt_v1",  # Static salt - in production, use unique per-value
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(encryption_key.encode()))
    return Fernet(key)


def encrypt_value(value: str, encryption_key: str | None = None) -> str:
    """Encrypt a sensitive value.

    Args:
        value: The value to encrypt
        encryption_key: Optional encryption key. If not provided, uses ENCRYPTION_KEY env var.

    Returns:
        Base64-encoded encrypted value
    """
    if not encryption_key:
        encryption_key = os.environ.get("ENCRYPTION_KEY", "default-dev-key-change-me")

    fernet = _get_fernet(encryption_key)
    encrypted = fernet.encrypt(value.encode())
    return base64.urlsafe_b64encode(encrypted).decode()


def decrypt_value(encrypted_value: str, encryption_key: str | None = None) -> str:
    """Decrypt a sensitive value.

    Args:
        encrypted_value: Base64-encoded encrypted value
        encryption_key: Optional encryption key. If not provided, uses ENCRYPTION_KEY env var.

    Returns:
        Decrypted value
    """
    if not encryption_key:
        encryption_key = os.environ.get("ENCRYPTION_KEY", "default-dev-key-change-me")

    fernet = _get_fernet(encryption_key)
    encrypted = base64.urlsafe_b64decode(encrypted_value.encode())
    decrypted: bytes = fernet.decrypt(encrypted)
    return decrypted.decode()


def paginate(
    items: list[Any],
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
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

    return {
        "items": items[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


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


def chunks(lst: list[Any], n: int):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]
