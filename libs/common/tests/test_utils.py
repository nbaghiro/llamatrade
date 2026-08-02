"""Tests for utility functions."""

import hashlib
from collections.abc import Generator
from datetime import UTC

import pytest

from llamatrade_common.utils import (
    decrypt_value,
    encrypt_value,
    generate_uuid,
    paginate,
    pagination_response,
    require_secret,
    resolve_pagination,
    utc_now,
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


class TestVerifyAPIKey:
    """Tests for constant-time API-key verification."""

    @staticmethod
    def _hash(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()

    def test_verify_api_key_valid(self):
        """A key matching its stored hash verifies."""
        key = "lt_some-example-key"
        assert verify_api_key(key, self._hash(key)) is True

    def test_verify_api_key_invalid(self):
        """A key that does not match the stored hash fails."""
        assert verify_api_key("wrong_key", self._hash("lt_some-example-key")) is False


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

    def test_encrypt_same_value_uses_per_value_salt(self):
        """Encrypting the same value twice yields different ciphertext; both decrypt."""
        value, key = "secret_value_123", "test_encryption_key"

        first = encrypt_value(value, key)
        second = encrypt_value(value, key)

        assert first != second
        assert decrypt_value(first, key) == value
        assert decrypt_value(second, key) == value


class TestDerivedKeyCache:
    """PBKDF2 derivations are cached per (key, salt) — hot-path decrypts are cheap."""

    @pytest.fixture
    def kdf_calls(self, monkeypatch: pytest.MonkeyPatch) -> Generator[list[int]]:
        """Count PBKDF2HMAC constructions inside a cleared cache window."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        from llamatrade_common import utils

        calls: list[int] = []

        def counting_kdf(
            *, algorithm: hashes.HashAlgorithm, length: int, salt: bytes, iterations: int
        ) -> PBKDF2HMAC:
            calls.append(1)
            return PBKDF2HMAC(algorithm=algorithm, length=length, salt=salt, iterations=iterations)

        monkeypatch.setattr(utils, "PBKDF2HMAC", counting_kdf)
        utils._derive_fernet_key.cache_clear()
        yield calls
        utils._derive_fernet_key.cache_clear()

    def test_decrypts_of_same_envelope_derive_once(self, kdf_calls: list[int]) -> None:
        encrypted = encrypt_value("v", "k")
        assert decrypt_value(encrypted, "k") == "v"
        assert decrypt_value(encrypted, "k") == "v"
        assert len(kdf_calls) == 1

    def test_distinct_salts_derive_separately(self, kdf_calls: list[int]) -> None:
        first = encrypt_value("v", "k")
        second = encrypt_value("v", "k")
        assert decrypt_value(first, "k") == "v"
        assert decrypt_value(second, "k") == "v"
        assert len(kdf_calls) == 2

    def test_distinct_keys_derive_separately(self, kdf_calls: list[int]) -> None:
        from llamatrade_common import utils

        salt = b"0123456789abcdef"
        utils._derive_fernet_key("key-a", salt)
        utils._derive_fernet_key("key-b", salt)
        utils._derive_fernet_key("key-a", salt)
        assert len(kdf_calls) == 2


class TestCipherSelection:
    """The envelope cipher is a config choice (KMS seam)."""

    def test_default_is_local_fernet(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from llamatrade_common.utils import LocalFernetCipher, get_cipher

        monkeypatch.delenv("CREDENTIAL_CIPHER", raising=False)
        assert isinstance(get_cipher(), LocalFernetCipher)

    def test_explicit_name_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from llamatrade_common.utils import GcpKmsCipher, get_cipher

        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert isinstance(get_cipher("gcp-kms"), GcpKmsCipher)

    def test_env_selects_cipher_for_module_functions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CREDENTIAL_CIPHER", "gcp-kms")
        monkeypatch.delenv("KMS_KEY_NAME", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        with pytest.raises(RuntimeError, match="KMS_KEY_NAME"):
            encrypt_value("v")
        with pytest.raises(RuntimeError, match="KMS_KEY_NAME"):
            decrypt_value("anything")

    def test_unknown_cipher_rejected(self) -> None:
        from llamatrade_common.utils import get_cipher

        with pytest.raises(ValueError, match="unknown credential cipher"):
            get_cipher("vault")

    def test_local_cipher_round_trips(self) -> None:
        from llamatrade_common.utils import LocalFernetCipher

        cipher = LocalFernetCipher()
        assert cipher.decrypt_value(cipher.encrypt_value("s", "k"), "k") == "s"


class TestRequireSecret:
    """Tests for require_secret (fail-closed secret resolution)."""

    def test_returns_env_value_when_set(self, monkeypatch):
        monkeypatch.setenv("MY_SECRET", "from-env")
        assert require_secret("MY_SECRET", "dev-default") == "from-env"

    def test_returns_dev_default_in_development(self, monkeypatch):
        monkeypatch.delenv("MY_SECRET", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "development")
        assert require_secret("MY_SECRET", "dev-default") == "dev-default"

    def test_returns_dev_default_when_environment_unset(self, monkeypatch):
        monkeypatch.delenv("MY_SECRET", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        assert require_secret("MY_SECRET", "dev-default") == "dev-default"

    @pytest.mark.parametrize("environment", ["production", "staging", "PRODUCTION"])
    def test_raises_in_prod_when_unset(self, monkeypatch, environment):
        monkeypatch.delenv("MY_SECRET", raising=False)
        monkeypatch.setenv("ENVIRONMENT", environment)
        with pytest.raises(RuntimeError):
            require_secret("MY_SECRET", "dev-default")


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


class _PageReq:
    """Stand-in for the proto ``PaginationRequest`` (int fields, default 0)."""

    def __init__(self, page: int = 0, page_size: int = 0) -> None:
        self.page = page
        self.page_size = page_size


class TestResolvePagination:
    """Tests for the request-side pagination resolver."""

    def test_none_uses_defaults(self):
        assert resolve_pagination(None) == (1, 20)

    def test_none_honours_custom_default_size(self):
        assert resolve_pagination(None, default_page_size=50) == (1, 50)

    def test_unset_fields_treated_as_unset(self):
        assert resolve_pagination(_PageReq(page=0, page_size=0)) == (1, 20)

    def test_explicit_values_pass_through(self):
        assert resolve_pagination(_PageReq(page=3, page_size=25)) == (3, 25)

    def test_page_floors_at_one(self):
        assert resolve_pagination(_PageReq(page=-5, page_size=10)) == (1, 10)

    def test_page_size_never_zero(self):
        """A client-supplied page_size of 0 must not survive to a divisor."""
        _, page_size = resolve_pagination(_PageReq(page=1, page_size=0))
        assert page_size == 20

    def test_negative_page_size_falls_back_to_default(self):
        assert resolve_pagination(_PageReq(page=1, page_size=-1)) == (1, 20)

    def test_page_size_clamped_to_max(self):
        assert resolve_pagination(_PageReq(page=1, page_size=100_000)) == (1, 100)

    def test_max_page_size_is_configurable(self):
        assert resolve_pagination(_PageReq(page=1, page_size=5000), max_page_size=500) == (1, 500)


class TestPaginationResponse:
    """Tests for the response-side pagination metadata builder."""

    def test_first_page_of_many(self):
        meta = pagination_response(total=25, page=1, page_size=10)
        assert meta == {
            "total_items": 25,
            "total_pages": 3,
            "current_page": 1,
            "page_size": 10,
            "has_next": True,
            "has_previous": False,
        }

    def test_last_page(self):
        meta = pagination_response(total=25, page=3, page_size=10)
        assert meta["has_next"] is False
        assert meta["has_previous"] is True

    def test_empty_result_has_one_page(self):
        meta = pagination_response(total=0, page=1, page_size=10)
        assert meta["total_pages"] == 1
        assert meta["has_next"] is False
        assert meta["has_previous"] is False

    def test_zero_page_size_does_not_divide_by_zero(self):
        meta = pagination_response(total=5, page=1, page_size=0)
        assert meta["page_size"] == 1
        assert meta["total_pages"] == 5
