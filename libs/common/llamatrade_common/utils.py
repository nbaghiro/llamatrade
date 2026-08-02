"""Shared utilities for LlamaTrade services."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import secrets
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from functools import lru_cache
from importlib import import_module
from types import ModuleType
from typing import NamedTuple, Protocol, TypedDict, cast
from uuid import UUID, uuid4

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def generate_uuid() -> UUID:
    """Generate a new UUID4."""
    return uuid4()


def utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(UTC)


def verify_api_key(api_key: str, api_key_hash: str) -> bool:
    """Verify an API key against its hash."""
    computed_hash = hashlib.sha256(api_key.encode()).hexdigest()
    return secrets.compare_digest(computed_hash, api_key_hash)


_DEV_ENCRYPTION_KEY = "default-dev-key-change-me"
_SALT_BYTES = 16
_PBKDF2_ITERATIONS = 100_000
_PROD_ENVIRONMENTS = {"production", "staging"}


def is_production_environment() -> bool:
    """True when ``ENVIRONMENT`` is production/staging (secrets must be real)."""
    return os.environ.get("ENVIRONMENT", "development").lower() in _PROD_ENVIRONMENTS


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
    if is_production_environment():
        environment = os.environ.get("ENVIRONMENT", "").lower()
        raise RuntimeError(
            f"{env_var} must be set in the {environment} environment; "
            "refusing to fall back to the insecure development default"
        )
    return dev_default


@lru_cache(maxsize=4096)
def _derive_fernet_key(encryption_key: str, salt: bytes) -> bytes:
    """PBKDF2-derived Fernet key, cached per (key, salt) so hot-path decrypts
    of the same envelope skip the 100k-iteration derivation."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(encryption_key.encode()))


def _get_fernet(encryption_key: str, salt: bytes) -> Fernet:
    """Fernet instance for the key and a per-value salt."""
    return Fernet(_derive_fernet_key(encryption_key, salt))


class EnvelopeCipher(Protocol):
    """Envelope-encryption seam: swapping ``local`` Fernet for a KMS
    implementation is a ``CREDENTIAL_CIPHER`` config change, not a refactor."""

    def encrypt_value(self, value: str, encryption_key: str | None = None) -> str: ...

    def decrypt_value(self, encrypted_value: str, encryption_key: str | None = None) -> str: ...


class LocalFernetCipher:
    """PBKDF2 + Fernet with a random per-value salt (the ``local`` cipher)."""

    def encrypt_value(self, value: str, encryption_key: str | None = None) -> str:
        """Encrypt into a base64 envelope of ``salt || fernet_token``."""
        if not encryption_key:
            encryption_key = require_secret("ENCRYPTION_KEY", _DEV_ENCRYPTION_KEY)
        salt = secrets.token_bytes(_SALT_BYTES)
        token = _get_fernet(encryption_key, salt).encrypt(value.encode())
        return base64.urlsafe_b64encode(salt + token).decode()

    def decrypt_value(self, encrypted_value: str, encryption_key: str | None = None) -> str:
        """Decrypt an envelope produced by :meth:`encrypt_value`."""
        if not encryption_key:
            encryption_key = require_secret("ENCRYPTION_KEY", _DEV_ENCRYPTION_KEY)
        raw = base64.urlsafe_b64decode(encrypted_value.encode())
        salt, token = raw[:_SALT_BYTES], raw[_SALT_BYTES:]
        return _get_fernet(encryption_key, salt).decrypt(token).decode()


_KMS_KEY_NAME_ENV = "KMS_KEY_NAME"
_KMS_PART_ENVS = ("KMS_PROJECT_ID", "KMS_LOCATION", "KMS_KEY_RING", "KMS_KEY")
_KMS_PART_FALLBACK_ENVS = {"KMS_PROJECT_ID": "GCP_PROJECT_ID", "KMS_LOCATION": "GCP_REGION"}
_KMS_MODULE = "google.cloud.kms"
_KMS_ERRORS_MODULE = "google.api_core.exceptions"
_KMS_ENVELOPE_PREFIX = "kms1"
_KMS_ENVELOPE_PARTS = 4
_KMS_VERSION_MARKER = "/cryptoKeyVersions/"
_KMS_TIMEOUT_SECONDS = 10.0


class KmsEncryptResponse(Protocol):
    """The Cloud KMS ``EncryptResponse`` surface this module reads."""

    name: str
    ciphertext: bytes


class KmsDecryptResponse(Protocol):
    """The Cloud KMS ``DecryptResponse`` surface this module reads."""

    plaintext: bytes


class KmsClient(Protocol):
    """The ``KeyManagementServiceClient`` surface this module calls."""

    def encrypt(self, *, name: str, plaintext: bytes, timeout: float) -> KmsEncryptResponse: ...

    def decrypt(self, *, name: str, ciphertext: bytes, timeout: float) -> KmsDecryptResponse: ...


class KmsClientFactory(Protocol):
    """Zero-argument construction of a :class:`KmsClient` from ambient credentials."""

    def __call__(self) -> KmsClient: ...


class _KmsErrors(NamedTuple):
    """Cloud KMS failure classes, grouped by how they map onto the seam's errors."""

    invalid_argument: tuple[type[Exception], ...]
    not_found: tuple[type[Exception], ...]
    denied: tuple[type[Exception], ...]
    unavailable: tuple[type[Exception], ...]
    api_error: tuple[type[Exception], ...]


def _import_kms_dependency(module_name: str) -> ModuleType:
    """Import a Cloud KMS module, translating an absent package into a clear failure."""
    try:
        return import_module(module_name)
    except ImportError as exc:
        raise RuntimeError(
            f"the gcp-kms credential cipher needs {module_name}; install the "
            "google-cloud-kms package (llamatrade-common[gcp-kms]) or set CREDENTIAL_CIPHER=local"
        ) from exc


def _validate_kms_key_name(name: str) -> str:
    """Accept only a Cloud KMS crypto key resource name (never echo the value)."""
    if not name.startswith("projects/") or "/cryptoKeys/" not in name:
        raise ValueError(
            "expected a Cloud KMS crypto key resource name of the form "
            "projects/<project>/locations/<location>/keyRings/<ring>/cryptoKeys/<key>"
        )
    return name


def _compose_kms_key_name() -> str | None:
    """Assemble the key resource name from its component env vars, if all are set."""
    parts: list[str] = []
    for env_var in _KMS_PART_ENVS:
        fallback = _KMS_PART_FALLBACK_ENVS.get(env_var)
        value = os.environ.get(env_var) or (os.environ.get(fallback, "") if fallback else "")
        if not value:
            return None
        parts.append(value)
    project, location, key_ring, key = parts
    return f"projects/{project}/locations/{location}/keyRings/{key_ring}/cryptoKeys/{key}"


def _resolve_kms_key_name() -> str | None:
    """The configured crypto key, refusing to run unconfigured in prod-like environments."""
    name = os.environ.get(_KMS_KEY_NAME_ENV) or _compose_kms_key_name()
    if name:
        return _validate_kms_key_name(name)
    if is_production_environment():
        environment = os.environ.get("ENVIRONMENT", "").lower()
        raise RuntimeError(
            f"{_KMS_KEY_NAME_ENV} (or {'/'.join(_KMS_PART_ENVS)}) must be set in the "
            f"{environment} environment when CREDENTIAL_CIPHER=gcp-kms"
        )
    return None


def _crypto_key_of(version_name: str) -> str:
    """The crypto key of a version resource name; symmetric decrypt addresses the key."""
    return version_name.split(_KMS_VERSION_MARKER, 1)[0]


def _join_kms_envelope(version_name: str, wrapped_key: bytes, token: bytes) -> str:
    """Serialize the envelope as ``kms1.<version>.<wrapped data key>.<token>``."""
    return ".".join(
        (
            _KMS_ENVELOPE_PREFIX,
            base64.urlsafe_b64encode(version_name.encode()).decode(),
            base64.urlsafe_b64encode(wrapped_key).decode(),
            base64.urlsafe_b64encode(token).decode(),
        )
    )


def _split_kms_envelope(envelope: str) -> tuple[str, bytes, bytes]:
    """Parse an envelope into ``(key version name, wrapped data key, token)``."""
    parts = envelope.split(".")
    if len(parts) != _KMS_ENVELOPE_PARTS or parts[0] != _KMS_ENVELOPE_PREFIX:
        raise InvalidToken(f"value is not a {_KMS_ENVELOPE_PREFIX} envelope")
    version_name, wrapped_key, token = (base64.urlsafe_b64decode(p.encode()) for p in parts[1:])
    return version_name.decode(), wrapped_key, token


class GcpKmsCipher:
    """Cloud KMS envelope cipher (the ``gcp-kms`` cipher).

    A random per-credential Fernet data key encrypts the secret and Cloud KMS
    wraps that data key, so a database dump is inert without the caller's KMS
    permission on the configured key.
    """

    def __init__(self) -> None:
        self._key_name = _resolve_kms_key_name()
        self._client_instance: KmsClient | None = None
        self._errors_instance: _KmsErrors | None = None

    def encrypt_value(self, value: str, encryption_key: str | None = None) -> str:
        """Encrypt under a fresh data key wrapped by the key's primary version.

        ``encryption_key`` overrides the configured crypto key resource name.
        """
        key_name = self._key_name_for(encryption_key)
        data_key = Fernet.generate_key()
        token = Fernet(data_key).encrypt(value.encode())
        client = self._client()
        response = self._call(
            "encrypt",
            key_name,
            lambda: client.encrypt(name=key_name, plaintext=data_key, timeout=_KMS_TIMEOUT_SECONDS),
        )
        return _join_kms_envelope(response.name or key_name, response.ciphertext, token)

    def decrypt_value(self, encrypted_value: str, encryption_key: str | None = None) -> str:
        """Decrypt an envelope, unwrapping its data key through Cloud KMS.

        Cloud KMS selects the key version that wrapped the data key, so envelopes
        written before a rotation keep decrypting without a re-encrypt.
        """
        configured = self._key_name_for(encryption_key)
        version_name, wrapped_key, token = _split_kms_envelope(encrypted_value)
        key_name = _crypto_key_of(version_name)
        # Pinning the envelope's key to configuration stops a tampered row from
        # redirecting the unwrap at a key the caller does not control.
        if key_name != configured:
            raise RuntimeError(
                f"envelope names Cloud KMS key {key_name}, which is not the configured key"
            )
        client = self._client()
        response = self._call(
            "decrypt",
            key_name,
            lambda: client.decrypt(
                name=key_name, ciphertext=wrapped_key, timeout=_KMS_TIMEOUT_SECONDS
            ),
            as_invalid_token=True,
        )
        return Fernet(response.plaintext).decrypt(token).decode()

    @staticmethod
    def key_version_name(encrypted_value: str) -> str:
        """The key version that wrapped this envelope; stale versions are re-encrypt work."""
        version_name, _, _ = _split_kms_envelope(encrypted_value)
        return version_name

    def _key_name_for(self, encryption_key: str | None) -> str:
        if encryption_key:
            return _validate_kms_key_name(encryption_key)
        if self._key_name is None:
            raise RuntimeError(
                f"{_KMS_KEY_NAME_ENV} (or {'/'.join(_KMS_PART_ENVS)}) must be set to use "
                "the gcp-kms credential cipher"
            )
        return self._key_name

    def _client(self) -> KmsClient:
        if self._client_instance is None:
            module = _import_kms_dependency(_KMS_MODULE)
            factory = cast(KmsClientFactory, module.KeyManagementServiceClient)
            try:
                self._client_instance = factory()
            except Exception as exc:
                raise RuntimeError(f"could not build a Cloud KMS client: {exc}") from exc
        return self._client_instance

    def _errors(self) -> _KmsErrors:
        if self._errors_instance is None:
            module = _import_kms_dependency(_KMS_ERRORS_MODULE)

            def error(attr: str) -> type[Exception]:
                return cast(type[Exception], getattr(module, attr))

            self._errors_instance = _KmsErrors(
                invalid_argument=(error("InvalidArgument"),),
                not_found=(error("NotFound"),),
                denied=(error("PermissionDenied"), error("Unauthenticated")),
                unavailable=(error("ServiceUnavailable"), error("DeadlineExceeded")),
                api_error=(error("GoogleAPICallError"),),
            )
        return self._errors_instance

    def _call[T](
        self,
        operation: str,
        key_name: str,
        call: Callable[[], T],
        *,
        as_invalid_token: bool = False,
    ) -> T:
        """Run a KMS call, mapping its failures onto the seam's error types."""
        errors = self._errors()
        try:
            return call()
        except errors.invalid_argument as exc:
            if as_invalid_token:
                raise InvalidToken(f"Cloud KMS key {key_name} cannot unwrap this data key") from exc
            raise RuntimeError(
                f"Cloud KMS rejected the {operation} request for {key_name}"
            ) from exc
        except errors.not_found as exc:
            raise RuntimeError(f"Cloud KMS key {key_name} was not found") from exc
        except errors.denied as exc:
            raise RuntimeError(
                f"Cloud KMS denied {operation} on {key_name}; the caller's identity "
                f"lacks permission to use the key for {operation}"
            ) from exc
        except errors.unavailable as exc:
            raise RuntimeError(f"Cloud KMS is unavailable for {operation} on {key_name}") from exc
        except errors.api_error as exc:
            raise RuntimeError(f"Cloud KMS {operation} on {key_name} failed") from exc


_CIPHER_FACTORIES: dict[str, Callable[[], EnvelopeCipher]] = {
    "local": LocalFernetCipher,
    "gcp-kms": GcpKmsCipher,
}
_CIPHERS: dict[str, EnvelopeCipher] = {}


def get_cipher(name: str | None = None) -> EnvelopeCipher:
    """The selected envelope cipher (``CREDENTIAL_CIPHER`` env, default ``local``).

    A cipher is built on first selection and reused for the process, so an
    unconfigured KMS key only fails services that actually select ``gcp-kms``.
    """
    selected = name or os.environ.get("CREDENTIAL_CIPHER", "local")
    cipher = _CIPHERS.get(selected)
    if cipher is not None:
        return cipher
    factory = _CIPHER_FACTORIES.get(selected)
    if factory is None:
        raise ValueError(
            f"unknown credential cipher {selected!r}; expected one of {sorted(_CIPHER_FACTORIES)}"
        )
    cipher = factory()
    _CIPHERS[selected] = cipher
    return cipher


def encrypt_value(value: str, encryption_key: str | None = None) -> str:
    """Encrypt a sensitive value via the configured envelope cipher.

    The ``local`` cipher emits a base64 envelope of ``salt || fernet_token`` so
    each ciphertext carries its own salt. If no key is given, ``ENCRYPTION_KEY``
    is used (required in prod via :func:`require_secret`).
    """
    return get_cipher().encrypt_value(value, encryption_key)


def decrypt_value(encrypted_value: str, encryption_key: str | None = None) -> str:
    """Decrypt a value produced by :func:`encrypt_value`."""
    return get_cipher().decrypt_value(encrypted_value, encryption_key)


def reencrypt_value(encrypted_value: str, encryption_key: str | None = None) -> str:
    """Re-wrap a stored value under the current key material.

    The rotation hook for both ciphers: ``local`` draws a fresh salt, ``gcp-kms``
    re-wraps the data key with the crypto key's primary version. Callers walk the
    stored ciphertexts (for ``gcp-kms``, those whose
    :meth:`GcpKmsCipher.key_version_name` is no longer primary) and write the result back.
    """
    cipher = get_cipher()
    plaintext = cipher.decrypt_value(encrypted_value, encryption_key)
    return cipher.encrypt_value(plaintext, encryption_key)


async def async_encrypt_value(value: str, encryption_key: str | None = None) -> str:
    """:func:`encrypt_value` on a worker thread, for async callers.

    Every cipher blocks the calling thread: ``gcp-kms`` makes a Cloud KMS RPC and
    ``local`` runs a 100k-iteration PBKDF2 that the per-value salt guarantees is a
    cache miss on encrypt. Async request paths must use this; the sync function
    remains the entry point for sync contexts (seed scripts, tests). Errors are the
    sync contract unchanged: ``InvalidToken``, ``ValueError``, ``RuntimeError``.
    """
    return await asyncio.to_thread(encrypt_value, value, encryption_key)


async def async_decrypt_value(encrypted_value: str, encryption_key: str | None = None) -> str:
    """:func:`decrypt_value` on a worker thread, for async callers.

    Under ``gcp-kms`` each call is a network round trip; under ``local`` it is a
    PBKDF2 derivation unless this exact envelope is already in the derivation
    cache. Same error contract as the sync function.
    """
    return await asyncio.to_thread(decrypt_value, encrypted_value, encryption_key)


async def async_reencrypt_value(encrypted_value: str, encryption_key: str | None = None) -> str:
    """:func:`reencrypt_value` on a worker thread, for async callers.

    The decrypt and the re-encrypt share one thread hop rather than two. Same
    error contract as the sync function.
    """
    return await asyncio.to_thread(reencrypt_value, encrypted_value, encryption_key)


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


_DEFAULT_PAGE_SIZE = 20
_MAX_PAGE_SIZE = 100


class PaginationRequestLike(Protocol):
    """Structural type for the proto ``PaginationRequest`` (page + page_size)."""

    page: int
    page_size: int


class PaginationResponseData(TypedDict):
    """Pagination metadata, keyed to match the proto ``PaginationResponse`` fields."""

    total_items: int
    total_pages: int
    current_page: int
    page_size: int
    has_next: bool
    has_previous: bool


def resolve_pagination(
    pagination: PaginationRequestLike | None,
    *,
    default_page_size: int = _DEFAULT_PAGE_SIZE,
    max_page_size: int = _MAX_PAGE_SIZE,
) -> tuple[int, int]:
    """Normalize a proto ``PaginationRequest`` into a ``(page, page_size)`` pair.

    An absent request or a zero/negative field counts as unset: ``page`` floors at
    1 and ``page_size`` falls back to ``default_page_size``, then clamps to
    ``max_page_size``. The floor of 1 guarantees a nonzero divisor for callers that
    compute ``total_pages`` (the open-coded copies raise ``ZeroDivisionError`` on
    a client-supplied ``page_size`` of 0).
    """
    page = pagination.page if pagination is not None else 0
    raw_size = pagination.page_size if pagination is not None else 0
    page = page if page >= 1 else 1
    size = raw_size if raw_size >= 1 else default_page_size
    return page, min(size, max_page_size)


def pagination_response(total: int, page: int, page_size: int) -> PaginationResponseData:
    """Build proto-shaped pagination metadata from a resolved ``page``/``page_size``.

    ``page_size`` is expected to be >= 1 (see :func:`resolve_pagination`); a floor
    of 1 is applied defensively so a mis-passed 0 cannot raise ``ZeroDivisionError``.
    """
    size = page_size if page_size >= 1 else 1
    total_pages = (total + size - 1) // size if total > 0 else 1
    return PaginationResponseData(
        total_items=total,
        total_pages=total_pages,
        current_page=page,
        page_size=size,
        has_next=page < total_pages,
        has_previous=page > 1,
    )
