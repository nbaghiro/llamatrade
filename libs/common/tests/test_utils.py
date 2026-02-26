"""Tests for utility functions."""

from datetime import UTC

import pytest
from llamatrade_common.utils import (
    calculate_pnl,
    chunks,
    decrypt_value,
    encrypt_value,
    format_currency,
    format_percent,
    generate_api_key,
    generate_uuid,
    normalize_symbol,
    paginate,
    utc_now,
    validate_symbol,
    verify_api_key,
)


class TestGenerateUUID:
    """Tests for generate_uuid function."""

    def test_generates_valid_uuid(self):
        """Test that generate_uuid returns a valid UUID."""
        uuid = generate_uuid()
        assert uuid is not None
        assert len(str(uuid)) == 36  # UUID string format

    def test_generates_unique_uuids(self):
        """Test that each call generates a unique UUID."""
        uuids = [generate_uuid() for _ in range(100)]
        assert len(set(uuids)) == 100


class TestUtcNow:
    """Tests for utc_now function."""

    def test_returns_datetime(self):
        """Test that utc_now returns a datetime."""
        from datetime import datetime

        now = utc_now()
        assert isinstance(now, datetime)
        assert now.tzinfo == UTC


class TestAPIKeyGeneration:
    """Tests for API key generation and verification."""

    def test_generate_api_key_default_prefix(self):
        """Test generating API key with default prefix."""
        key, key_hash = generate_api_key()
        assert key.startswith("lt_")
        assert len(key_hash) == 64  # SHA256 hex digest

    def test_generate_api_key_custom_prefix(self):
        """Test generating API key with custom prefix."""
        key, key_hash = generate_api_key(prefix="test")
        assert key.startswith("test_")

    def test_verify_api_key_valid(self):
        """Test verifying a valid API key."""
        key, key_hash = generate_api_key()
        assert verify_api_key(key, key_hash) is True

    def test_verify_api_key_invalid(self):
        """Test verifying an invalid API key."""
        key, key_hash = generate_api_key()
        assert verify_api_key("wrong_key", key_hash) is False


class TestEncryption:
    """Tests for encryption/decryption functions."""

    def test_encrypt_decrypt_roundtrip(self):
        """Test that encryption and decryption are reversible."""
        original = "secret_value_123"
        key = "test_encryption_key"

        encrypted = encrypt_value(original, key)
        decrypted = decrypt_value(encrypted, key)

        assert decrypted == original
        assert encrypted != original

    def test_encrypt_different_keys_produce_different_output(self):
        """Test that different keys produce different ciphertext."""
        value = "secret"
        encrypted1 = encrypt_value(value, "key1")
        encrypted2 = encrypt_value(value, "key2")

        assert encrypted1 != encrypted2

    def test_decrypt_with_wrong_key_fails(self):
        """Test that decryption with wrong key fails."""
        encrypted = encrypt_value("secret", "correct_key")

        with pytest.raises(Exception):
            decrypt_value(encrypted, "wrong_key")


class TestPaginate:
    """Tests for pagination function."""

    def test_paginate_first_page(self):
        """Test getting first page."""
        items = list(range(25))
        result = paginate(items, page=1, page_size=10)

        assert result["items"] == list(range(10))
        assert result["total"] == 25
        assert result["page"] == 1
        assert result["page_size"] == 10
        assert result["total_pages"] == 3

    def test_paginate_middle_page(self):
        """Test getting middle page."""
        items = list(range(25))
        result = paginate(items, page=2, page_size=10)

        assert result["items"] == list(range(10, 20))

    def test_paginate_last_page(self):
        """Test getting last page with partial results."""
        items = list(range(25))
        result = paginate(items, page=3, page_size=10)

        assert result["items"] == list(range(20, 25))

    def test_paginate_empty_list(self):
        """Test paginating empty list."""
        result = paginate([], page=1, page_size=10)

        assert result["items"] == []
        assert result["total"] == 0
        assert result["total_pages"] == 0

    def test_paginate_beyond_last_page(self):
        """Test requesting page beyond available data."""
        items = list(range(5))
        result = paginate(items, page=10, page_size=10)

        assert result["items"] == []


class TestFormatCurrency:
    """Tests for currency formatting."""

    def test_format_usd(self):
        """Test formatting USD."""
        assert format_currency(1234.56) == "$1,234.56"
        assert format_currency(1234.56, "USD") == "$1,234.56"

    def test_format_other_currency(self):
        """Test formatting other currencies."""
        assert format_currency(1234.56, "EUR") == "1,234.56 EUR"

    def test_format_large_number(self):
        """Test formatting large numbers."""
        assert format_currency(1234567.89) == "$1,234,567.89"

    def test_format_small_number(self):
        """Test formatting small numbers."""
        assert format_currency(0.01) == "$0.01"


class TestFormatPercent:
    """Tests for percentage formatting."""

    def test_format_percent_default_decimals(self):
        """Test formatting percentage with default decimals."""
        assert format_percent(0.1234) == "12.34%"

    def test_format_percent_custom_decimals(self):
        """Test formatting percentage with custom decimals."""
        assert format_percent(0.12345, decimals=1) == "12.3%"
        assert format_percent(0.12345, decimals=4) == "12.3450%"

    def test_format_percent_negative(self):
        """Test formatting negative percentage."""
        assert format_percent(-0.05) == "-5.00%"


class TestCalculatePnl:
    """Tests for P&L calculation."""

    def test_calculate_profit(self):
        """Test calculating profit."""
        pnl, pnl_pct = calculate_pnl(cost_basis=100, current_value=120)

        assert pnl == 20
        assert pnl_pct == 20.0

    def test_calculate_loss(self):
        """Test calculating loss."""
        pnl, pnl_pct = calculate_pnl(cost_basis=100, current_value=80)

        assert pnl == -20
        assert pnl_pct == -20.0

    def test_calculate_zero_cost_basis(self):
        """Test with zero cost basis."""
        pnl, pnl_pct = calculate_pnl(cost_basis=0, current_value=100)

        assert pnl == 100
        assert pnl_pct == 0  # Avoid division by zero


class TestValidateSymbol:
    """Tests for symbol validation."""

    def test_valid_symbols(self):
        """Test valid stock symbols."""
        assert validate_symbol("AAPL") is True
        assert validate_symbol("A") is True
        assert validate_symbol("GOOGL") is True

    def test_invalid_symbols(self):
        """Test invalid stock symbols."""
        assert validate_symbol("") is False
        assert validate_symbol("aapl") is False  # lowercase
        assert validate_symbol("TOOLONG") is False  # > 5 chars
        assert validate_symbol("AA1") is False  # contains number
        assert validate_symbol("AA-B") is False  # contains hyphen


class TestNormalizeSymbol:
    """Tests for symbol normalization."""

    def test_normalize_lowercase(self):
        """Test normalizing lowercase symbol."""
        assert normalize_symbol("aapl") == "AAPL"

    def test_normalize_mixed_case(self):
        """Test normalizing mixed case symbol."""
        assert normalize_symbol("AaPl") == "AAPL"

    def test_normalize_with_whitespace(self):
        """Test normalizing symbol with whitespace."""
        assert normalize_symbol("  AAPL  ") == "AAPL"


class TestChunks:
    """Tests for chunks generator."""

    def test_chunks_even_split(self):
        """Test chunking list that splits evenly."""
        result = list(chunks([1, 2, 3, 4, 5, 6], 2))

        assert result == [[1, 2], [3, 4], [5, 6]]

    def test_chunks_uneven_split(self):
        """Test chunking list that doesn't split evenly."""
        result = list(chunks([1, 2, 3, 4, 5], 2))

        assert result == [[1, 2], [3, 4], [5]]

    def test_chunks_larger_than_list(self):
        """Test chunk size larger than list."""
        result = list(chunks([1, 2, 3], 10))

        assert result == [[1, 2, 3]]

    def test_chunks_empty_list(self):
        """Test chunking empty list."""
        result = list(chunks([], 5))

        assert result == []
