"""Tests for the Cloud KMS envelope cipher, against a fake KMS client."""

import ast
import asyncio
import base64
import inspect
import sys
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from types import ModuleType

import pytest
from cryptography.fernet import InvalidToken

from llamatrade_common import utils
from llamatrade_common.utils import (
    GcpKmsCipher,
    LocalFernetCipher,
    async_decrypt_value,
    async_encrypt_value,
    async_reencrypt_value,
    decrypt_value,
    encrypt_value,
    get_cipher,
    reencrypt_value,
)

_KEY_NAME = "projects/proj/locations/us-central1/keyRings/ring/cryptoKeys/creds"
_OTHER_KEY_NAME = "projects/proj/locations/us-central1/keyRings/ring/cryptoKeys/other"
_WRAP_PREFIX = b"wrapped:"

type _AsyncCipherCall = Callable[[str, str | None], Awaitable[str]]


class ApiCallError(Exception):
    """Stand-in for the google.api_core.exceptions base class."""


class InvalidArgumentError(ApiCallError):
    """KMS rejects the request payload (a ciphertext this key cannot open)."""


class NotFoundError(ApiCallError):
    """The key or key version does not exist."""


class PermissionDeniedError(ApiCallError):
    """The caller's identity lacks the KMS permission."""


class UnauthenticatedError(ApiCallError):
    """The caller presented no usable credentials."""


class ServiceUnavailableError(ApiCallError):
    """KMS is unreachable."""


class DeadlineExceededError(ApiCallError):
    """The KMS call did not finish inside its deadline."""


class UnmappedApiError(ApiCallError):
    """An API error with no dedicated mapping."""


_KMS_ERROR_CLASSES: dict[str, type[Exception]] = {
    "GoogleAPICallError": ApiCallError,
    "InvalidArgument": InvalidArgumentError,
    "NotFound": NotFoundError,
    "PermissionDenied": PermissionDeniedError,
    "Unauthenticated": UnauthenticatedError,
    "ServiceUnavailable": ServiceUnavailableError,
    "DeadlineExceeded": DeadlineExceededError,
}


@dataclass
class FakeEncryptResponse:
    name: str
    ciphertext: bytes


@dataclass
class FakeDecryptResponse:
    plaintext: bytes


@dataclass
class FakeKmsClient:
    """In-memory KeyManagementServiceClient: wrapping is reversible bookkeeping.

    Decrypt ignores the key version, as Cloud KMS does for symmetric keys.
    """

    primary_version: str = "1"
    encrypt_calls: list[tuple[str, bytes]] = field(default_factory=list)
    decrypt_calls: list[tuple[str, bytes]] = field(default_factory=list)
    timeouts: list[float] = field(default_factory=list)
    encrypt_error: Exception | None = None
    decrypt_error: Exception | None = None

    def encrypt(self, *, name: str, plaintext: bytes, timeout: float) -> FakeEncryptResponse:
        self.encrypt_calls.append((name, plaintext))
        self.timeouts.append(timeout)
        if self.encrypt_error is not None:
            raise self.encrypt_error
        return FakeEncryptResponse(
            name=f"{name}/cryptoKeyVersions/{self.primary_version}",
            ciphertext=_WRAP_PREFIX + base64.b64encode(plaintext),
        )

    def decrypt(self, *, name: str, ciphertext: bytes, timeout: float) -> FakeDecryptResponse:
        self.decrypt_calls.append((name, ciphertext))
        self.timeouts.append(timeout)
        if self.decrypt_error is not None:
            raise self.decrypt_error
        if not ciphertext.startswith(_WRAP_PREFIX):
            raise InvalidArgumentError("ciphertext was not wrapped by this key")
        return FakeDecryptResponse(plaintext=base64.b64decode(ciphertext[len(_WRAP_PREFIX) :]))


def _install_kms_modules(
    monkeypatch: pytest.MonkeyPatch, factory: Callable[[], FakeKmsClient]
) -> None:
    """Put fake google.cloud.kms / google.api_core.exceptions modules on the import path."""
    kms_module = ModuleType(utils._KMS_MODULE)
    setattr(kms_module, "KeyManagementServiceClient", factory)
    errors_module = ModuleType(utils._KMS_ERRORS_MODULE)
    for attribute, error in _KMS_ERROR_CLASSES.items():
        setattr(errors_module, attribute, error)
    monkeypatch.setitem(sys.modules, utils._KMS_MODULE, kms_module)
    monkeypatch.setitem(sys.modules, utils._KMS_ERRORS_MODULE, errors_module)


@pytest.fixture
def kms(monkeypatch: pytest.MonkeyPatch) -> FakeKmsClient:
    """A fake KMS backend plus the key configuration that points at it."""
    client = FakeKmsClient()
    _install_kms_modules(monkeypatch, lambda: client)
    monkeypatch.setenv("KMS_KEY_NAME", _KEY_NAME)
    for env_var in utils._KMS_PART_ENVS:
        monkeypatch.delenv(env_var, raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    return client


class TestKmsConfiguration:
    """The key resource name comes from configuration and is validated up front."""

    def test_full_resource_name_env_wins(self, kms: FakeKmsClient) -> None:
        GcpKmsCipher().encrypt_value("secret")
        assert kms.encrypt_calls[0][0] == _KEY_NAME

    def test_composed_from_component_envs(
        self, kms: FakeKmsClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("KMS_KEY_NAME", raising=False)
        monkeypatch.setenv("KMS_PROJECT_ID", "proj")
        monkeypatch.setenv("KMS_LOCATION", "us-central1")
        monkeypatch.setenv("KMS_KEY_RING", "ring")
        monkeypatch.setenv("KMS_KEY", "creds")

        GcpKmsCipher().encrypt_value("secret")

        assert kms.encrypt_calls[0][0] == _KEY_NAME

    def test_falls_back_to_shared_gcp_project_and_region(
        self, kms: FakeKmsClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("KMS_KEY_NAME", raising=False)
        monkeypatch.setenv("GCP_PROJECT_ID", "proj")
        monkeypatch.setenv("GCP_REGION", "us-central1")
        monkeypatch.setenv("KMS_KEY_RING", "ring")
        monkeypatch.setenv("KMS_KEY", "creds")

        GcpKmsCipher().encrypt_value("secret")

        assert kms.encrypt_calls[0][0] == _KEY_NAME

    def test_partial_component_config_is_not_a_key_name(
        self, kms: FakeKmsClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("KMS_KEY_NAME", raising=False)
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        monkeypatch.setenv("KMS_PROJECT_ID", "proj")
        monkeypatch.setenv("KMS_LOCATION", "us-central1")

        with pytest.raises(RuntimeError, match="KMS_KEY_NAME"):
            GcpKmsCipher().encrypt_value("secret")

    @pytest.mark.parametrize("environment", ["production", "staging", "PRODUCTION"])
    def test_missing_config_fails_at_construction_in_prod(
        self, monkeypatch: pytest.MonkeyPatch, environment: str
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", environment)
        for env_var in ("KMS_KEY_NAME", "GCP_PROJECT_ID", "GCP_REGION", *utils._KMS_PART_ENVS):
            monkeypatch.delenv(env_var, raising=False)

        with pytest.raises(RuntimeError, match="KMS_KEY_NAME"):
            GcpKmsCipher()
        with pytest.raises(RuntimeError, match="KMS_KEY_NAME"):
            get_cipher("gcp-kms")

    def test_missing_config_outside_prod_fails_only_on_use(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "development")
        for env_var in ("KMS_KEY_NAME", "GCP_PROJECT_ID", "GCP_REGION", *utils._KMS_PART_ENVS):
            monkeypatch.delenv(env_var, raising=False)

        cipher = GcpKmsCipher()

        with pytest.raises(RuntimeError, match="KMS_KEY_NAME"):
            cipher.encrypt_value("secret")

    def test_malformed_key_name_rejected_without_echoing_it(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("KMS_KEY_NAME", "not-a-resource-name")

        with pytest.raises(ValueError, match="crypto key resource name") as caught:
            GcpKmsCipher()
        assert "not-a-resource-name" not in str(caught.value)

    def test_passphrase_override_rejected(self, kms: FakeKmsClient) -> None:
        with pytest.raises(ValueError, match="crypto key resource name"):
            GcpKmsCipher().encrypt_value("secret", "a-fernet-passphrase")

    def test_key_name_override_is_honored(self, kms: FakeKmsClient) -> None:
        GcpKmsCipher().encrypt_value("secret", _OTHER_KEY_NAME)
        assert kms.encrypt_calls[0][0] == _OTHER_KEY_NAME


class TestKmsEnvelope:
    """Wrap/unwrap round-trips and the shape of the stored envelope."""

    def test_wrap_unwrap_round_trip(self, kms: FakeKmsClient) -> None:
        cipher = GcpKmsCipher()

        envelope = cipher.encrypt_value("PKTESTSECRET")

        assert cipher.decrypt_value(envelope) == "PKTESTSECRET"

    def test_envelope_carries_key_version_and_hides_the_secret(self, kms: FakeKmsClient) -> None:
        kms.primary_version = "7"

        envelope = GcpKmsCipher().encrypt_value("PKTESTSECRET")

        assert envelope.startswith("kms1.")
        assert "PKTESTSECRET" not in envelope
        assert GcpKmsCipher.key_version_name(envelope) == f"{_KEY_NAME}/cryptoKeyVersions/7"

    def test_data_key_is_per_value(self, kms: FakeKmsClient) -> None:
        cipher = GcpKmsCipher()

        first = cipher.encrypt_value("secret")
        second = cipher.encrypt_value("secret")

        assert first != second
        assert kms.encrypt_calls[0][1] != kms.encrypt_calls[1][1]
        assert cipher.decrypt_value(first) == "secret"
        assert cipher.decrypt_value(second) == "secret"

    def test_data_key_is_not_recoverable_from_the_envelope(self, kms: FakeKmsClient) -> None:
        envelope = GcpKmsCipher().encrypt_value("secret")
        data_key = kms.encrypt_calls[0][1]
        _, wrapped_key, _ = utils._split_kms_envelope(envelope)

        assert wrapped_key != data_key
        assert data_key.decode() not in envelope

    def test_unwrap_addresses_the_crypto_key_not_the_version(self, kms: FakeKmsClient) -> None:
        cipher = GcpKmsCipher()

        cipher.decrypt_value(cipher.encrypt_value("secret"))

        assert kms.decrypt_calls[0][0] == _KEY_NAME

    def test_unwrap_of_an_older_key_version(self, kms: FakeKmsClient) -> None:
        cipher = GcpKmsCipher()
        kms.primary_version = "1"
        envelope = cipher.encrypt_value("secret")
        kms.primary_version = "4"

        assert cipher.decrypt_value(envelope) == "secret"
        assert kms.decrypt_calls[0][0] == _KEY_NAME

    def test_local_envelope_is_rejected(self, kms: FakeKmsClient) -> None:
        local_envelope = LocalFernetCipher().encrypt_value("secret", "passphrase")

        with pytest.raises(InvalidToken, match="kms1 envelope"):
            GcpKmsCipher().decrypt_value(local_envelope)

    def test_truncated_envelope_is_rejected(self, kms: FakeKmsClient) -> None:
        envelope = GcpKmsCipher().encrypt_value("secret")

        with pytest.raises(InvalidToken, match="kms1 envelope"):
            GcpKmsCipher().decrypt_value(envelope.rsplit(".", 1)[0])

    def test_envelope_naming_another_key_is_rejected(self, kms: FakeKmsClient) -> None:
        envelope = GcpKmsCipher().encrypt_value("secret", _OTHER_KEY_NAME)

        with pytest.raises(RuntimeError, match="not the configured key"):
            GcpKmsCipher().decrypt_value(envelope)
        assert not kms.decrypt_calls

    def test_kms_calls_are_time_bounded(self, kms: FakeKmsClient) -> None:
        cipher = GcpKmsCipher()

        cipher.decrypt_value(cipher.encrypt_value("secret"))

        assert kms.timeouts and all(timeout > 0 for timeout in kms.timeouts)


class TestKmsErrorMapping:
    """KMS failures surface as the seam's error types, never as google exceptions."""

    @pytest.mark.parametrize("error", [PermissionDeniedError("no"), UnauthenticatedError("no")])
    def test_permission_denied_maps_to_runtime_error(
        self, kms: FakeKmsClient, error: Exception
    ) -> None:
        kms.encrypt_error = error

        with pytest.raises(RuntimeError, match="denied") as caught:
            GcpKmsCipher().encrypt_value("secret")
        assert not isinstance(caught.value, ApiCallError)
        assert caught.value.__cause__ is error

    @pytest.mark.parametrize(
        "error", [ServiceUnavailableError("down"), DeadlineExceededError("slow")]
    )
    def test_unavailable_maps_to_runtime_error(self, kms: FakeKmsClient, error: Exception) -> None:
        cipher = GcpKmsCipher()
        envelope = cipher.encrypt_value("secret")
        kms.decrypt_error = error

        with pytest.raises(RuntimeError, match="unavailable") as caught:
            cipher.decrypt_value(envelope)
        assert not isinstance(caught.value, ApiCallError)

    def test_key_not_found_maps_to_runtime_error(self, kms: FakeKmsClient) -> None:
        kms.encrypt_error = NotFoundError("missing")

        with pytest.raises(RuntimeError, match="was not found") as caught:
            GcpKmsCipher().encrypt_value("secret")
        assert not isinstance(caught.value, ApiCallError)

    def test_key_not_found_on_unwrap_maps_to_runtime_error(self, kms: FakeKmsClient) -> None:
        cipher = GcpKmsCipher()
        envelope = cipher.encrypt_value("secret")
        kms.decrypt_error = NotFoundError("missing")

        with pytest.raises(RuntimeError, match="was not found"):
            cipher.decrypt_value(envelope)

    def test_undecryptable_data_key_maps_to_invalid_token(self, kms: FakeKmsClient) -> None:
        cipher = GcpKmsCipher()
        envelope = cipher.encrypt_value("secret")
        kms.decrypt_error = InvalidArgumentError("ciphertext is not valid for this key")

        with pytest.raises(InvalidToken, match="cannot unwrap") as caught:
            cipher.decrypt_value(envelope)
        assert not isinstance(caught.value, ApiCallError)

    def test_invalid_argument_on_wrap_stays_a_runtime_error(self, kms: FakeKmsClient) -> None:
        kms.encrypt_error = InvalidArgumentError("plaintext too large")

        with pytest.raises(RuntimeError, match="rejected the encrypt request"):
            GcpKmsCipher().encrypt_value("secret")

    def test_unmapped_api_error_maps_to_runtime_error(self, kms: FakeKmsClient) -> None:
        kms.encrypt_error = UnmappedApiError("gave up")

        with pytest.raises(RuntimeError, match="failed") as caught:
            GcpKmsCipher().encrypt_value("secret")
        assert not isinstance(caught.value, ApiCallError)

    def test_client_construction_failure_maps_to_runtime_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def explode() -> FakeKmsClient:
            raise OSError("no application default credentials")

        _install_kms_modules(monkeypatch, explode)
        monkeypatch.setenv("KMS_KEY_NAME", _KEY_NAME)

        with pytest.raises(RuntimeError, match="could not build a Cloud KMS client"):
            GcpKmsCipher().encrypt_value("secret")


class TestKmsLazyImport:
    """The KMS package is imported only on the KMS path."""

    def test_module_has_no_top_level_google_import(self) -> None:
        source = ast.parse(inspect.getsource(utils))
        imported: list[str] = []
        for node in source.body:
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)

        assert not [name for name in imported if name.startswith("google")]

    def test_local_cipher_path_imports_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        imported: list[str] = []

        def spy(name: str) -> ModuleType:
            imported.append(name)
            raise AssertionError(f"the local cipher path imported {name}")

        monkeypatch.setattr(utils, "import_module", spy)
        monkeypatch.delitem(sys.modules, utils._KMS_MODULE, raising=False)
        monkeypatch.setenv("CREDENTIAL_CIPHER", "local")

        assert decrypt_value(encrypt_value("secret", "passphrase"), "passphrase") == "secret"
        assert not imported
        assert utils._KMS_MODULE not in sys.modules

    def test_missing_package_reports_the_install_hint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def missing(name: str) -> ModuleType:
            raise ImportError(f"No module named {name!r}")

        monkeypatch.setattr(utils, "import_module", missing)
        monkeypatch.setenv("KMS_KEY_NAME", _KEY_NAME)

        with pytest.raises(RuntimeError, match="google-cloud-kms"):
            GcpKmsCipher().encrypt_value("secret")


class TestKmsCipherSelection:
    """The config seam picks the KMS cipher when configured, the local one otherwise."""

    def test_env_selects_the_kms_cipher(
        self, kms: FakeKmsClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CREDENTIAL_CIPHER", "gcp-kms")
        assert isinstance(get_cipher(), GcpKmsCipher)

    def test_default_stays_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CREDENTIAL_CIPHER", raising=False)
        assert isinstance(get_cipher(), LocalFernetCipher)

    def test_module_functions_route_through_kms(
        self, kms: FakeKmsClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CREDENTIAL_CIPHER", "gcp-kms")

        envelope = encrypt_value("PKTESTSECRET")

        assert envelope.startswith("kms1.")
        assert decrypt_value(envelope) == "PKTESTSECRET"
        assert kms.encrypt_calls[0][0] == _KEY_NAME

    def test_selected_cipher_is_reused(
        self, kms: FakeKmsClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CREDENTIAL_CIPHER", "gcp-kms")
        assert get_cipher() is get_cipher()


class TestRotation:
    """Re-encrypting moves a stored value onto the current key material."""

    def test_reencrypt_moves_to_the_primary_key_version(
        self, kms: FakeKmsClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CREDENTIAL_CIPHER", "gcp-kms")
        kms.primary_version = "1"
        stale = encrypt_value("PKTESTSECRET")
        kms.primary_version = "2"

        rotated = reencrypt_value(stale)

        assert GcpKmsCipher.key_version_name(stale).endswith("/cryptoKeyVersions/1")
        assert GcpKmsCipher.key_version_name(rotated).endswith("/cryptoKeyVersions/2")
        assert decrypt_value(rotated) == "PKTESTSECRET"

    def test_reencrypt_local_draws_a_new_salt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CREDENTIAL_CIPHER", "local")
        original = encrypt_value("secret", "passphrase")

        rotated = reencrypt_value(original, "passphrase")

        assert rotated != original
        assert decrypt_value(rotated, "passphrase") == "secret"


class TestAsyncSeam:
    """The async wrappers behave like the sync functions, off the event loop."""

    async def test_local_round_trip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CREDENTIAL_CIPHER", "local")

        envelope = await async_encrypt_value("PKTESTSECRET", "passphrase")

        assert "PKTESTSECRET" not in envelope
        assert await async_decrypt_value(envelope, "passphrase") == "PKTESTSECRET"

    async def test_kms_round_trip(
        self, kms: FakeKmsClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CREDENTIAL_CIPHER", "gcp-kms")

        envelope = await async_encrypt_value("PKTESTSECRET")

        assert envelope.startswith("kms1.")
        assert await async_decrypt_value(envelope) == "PKTESTSECRET"
        assert kms.encrypt_calls[0][0] == _KEY_NAME
        assert kms.decrypt_calls[0][0] == _KEY_NAME

    async def test_async_decrypts_a_sync_written_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The two entry points share one format; the sync path stays usable."""
        monkeypatch.setenv("CREDENTIAL_CIPHER", "local")

        assert await async_decrypt_value(encrypt_value("secret", "k"), "k") == "secret"
        assert decrypt_value(await async_encrypt_value("secret", "k"), "k") == "secret"

    async def test_reencrypt_rotates_under_kms(
        self, kms: FakeKmsClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CREDENTIAL_CIPHER", "gcp-kms")
        kms.primary_version = "1"
        stale = await async_encrypt_value("PKTESTSECRET")
        kms.primary_version = "2"

        rotated = await async_reencrypt_value(stale)

        assert GcpKmsCipher.key_version_name(rotated).endswith("/cryptoKeyVersions/2")
        assert await async_decrypt_value(rotated) == "PKTESTSECRET"

    async def test_reencrypt_local_draws_a_new_salt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CREDENTIAL_CIPHER", "local")
        original = await async_encrypt_value("secret", "passphrase")

        rotated = await async_reencrypt_value(original, "passphrase")

        assert rotated != original
        assert await async_decrypt_value(rotated, "passphrase") == "secret"

    @pytest.mark.parametrize(
        ("wrapper", "delegate"),
        [
            (async_encrypt_value, "encrypt_value"),
            (async_decrypt_value, "decrypt_value"),
            (async_reencrypt_value, "reencrypt_value"),
        ],
    )
    async def test_work_leaves_the_event_loop_thread(
        self,
        monkeypatch: pytest.MonkeyPatch,
        wrapper: _AsyncCipherCall,
        delegate: str,
    ) -> None:
        """Blocking cipher work runs on a worker thread, never inline on the loop."""
        threads: list[int] = []

        def record(value: str, encryption_key: str | None = None) -> str:
            threads.append(threading.get_ident())
            return value

        monkeypatch.setattr(utils, delegate, record)

        assert await wrapper("envelope", "k") == "envelope"
        assert threads and threading.get_ident() not in threads


class TestAsyncSeamErrors:
    """Failures cross the thread boundary as the sync contract's own error types."""

    async def test_wrong_key_still_raises_invalid_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CREDENTIAL_CIPHER", "local")
        envelope = await async_encrypt_value("secret", "correct_key")

        with pytest.raises(InvalidToken):
            await async_decrypt_value(envelope, "wrong_key")

    async def test_foreign_envelope_still_raises_invalid_token(
        self, kms: FakeKmsClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CREDENTIAL_CIPHER", "gcp-kms")
        local_envelope = LocalFernetCipher().encrypt_value("secret", "passphrase")

        with pytest.raises(InvalidToken, match="kms1 envelope"):
            await async_decrypt_value(local_envelope)

    async def test_kms_denial_still_raises_runtime_error_with_its_cause(
        self, kms: FakeKmsClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CREDENTIAL_CIPHER", "gcp-kms")
        error = PermissionDeniedError("no")
        kms.encrypt_error = error

        with pytest.raises(RuntimeError, match="denied") as caught:
            await async_encrypt_value("secret")
        assert not isinstance(caught.value, ApiCallError)
        assert caught.value.__cause__ is error

    async def test_unconfigured_kms_still_raises_runtime_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CREDENTIAL_CIPHER", "gcp-kms")
        monkeypatch.setenv("ENVIRONMENT", "development")
        for env_var in ("KMS_KEY_NAME", "GCP_PROJECT_ID", "GCP_REGION", *utils._KMS_PART_ENVS):
            monkeypatch.delenv(env_var, raising=False)

        with pytest.raises(RuntimeError, match="KMS_KEY_NAME"):
            await async_decrypt_value("anything")

    async def test_reencrypt_failure_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CREDENTIAL_CIPHER", "local")

        with pytest.raises(InvalidToken):
            await async_reencrypt_value(await async_encrypt_value("s", "k"), "other_key")


class TestAsyncSeamConcurrency:
    """Concurrent calls are independent: no shared buffer, no crossed plaintexts."""

    async def test_concurrent_local_decrypts_keep_their_own_plaintext(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CREDENTIAL_CIPHER", "local")
        secrets_by_index = [f"secret-{i}" for i in range(8)]
        envelopes = [await async_encrypt_value(s, "passphrase") for s in secrets_by_index]

        decrypted = await asyncio.gather(*(async_decrypt_value(e, "passphrase") for e in envelopes))

        assert list(decrypted) == secrets_by_index

    async def test_concurrent_kms_decrypts_keep_their_own_plaintext(
        self, kms: FakeKmsClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CREDENTIAL_CIPHER", "gcp-kms")
        secrets_by_index = [f"secret-{i}" for i in range(8)]
        envelopes = await asyncio.gather(*(async_encrypt_value(s) for s in secrets_by_index))

        decrypted = await asyncio.gather(*(async_decrypt_value(e) for e in envelopes))

        assert list(decrypted) == secrets_by_index
        assert len(kms.decrypt_calls) == len(envelopes)

    async def test_a_failing_call_does_not_poison_its_neighbours(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CREDENTIAL_CIPHER", "local")
        good = await async_encrypt_value("secret", "passphrase")

        results = await asyncio.gather(
            async_decrypt_value(good, "passphrase"),
            async_decrypt_value(good, "wrong_key"),
            async_decrypt_value(good, "passphrase"),
            return_exceptions=True,
        )

        assert results[0] == "secret"
        assert isinstance(results[1], InvalidToken)
        assert results[2] == "secret"
