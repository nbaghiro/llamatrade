"""connectrpc adapter for the shared auth mechanism, plus shared error mapping.

Kept out of ``auth.py`` so that module stays free of the ``connectrpc`` import.
Every connectrpc servicer resolves request identity through
``resolve_identity_connect`` — the transport-neutral :func:`resolve_identity`
plus a mapping of :class:`AuthError` to :class:`connectrpc.errors.ConnectError`.
The grpc.aio equivalent lives in each grpc servicer (see trading's
``_identity`` / ``_abort_auth``).

:func:`handle_service_errors` and :func:`parse_uuid` are the single copy of the
servicer error-mapping idiom (database exceptions to user-safe ``ConnectError``,
UUID parsing to ``INVALID_ARGUMENT``); the per-database constraint-name mapping
is an injectable hook so a service supplies only its own messages.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, Protocol, overload
from uuid import UUID

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from llamatrade_common.auth import AuthError, resolve_identity

logger = logging.getLogger(__name__)

_AUTH_CODE_TO_CONNECT = {
    "unauthenticated": Code.UNAUTHENTICATED,
    "permission_denied": Code.PERMISSION_DENIED,
    "invalid_argument": Code.INVALID_ARGUMENT,
}

_DEFAULT_INTEGRITY_MESSAGE = (
    "Data constraint violation. The operation conflicts with existing data."
)

# Given an IntegrityError, return a user-facing message, or None to fall back to
# the generic constraint-violation message.
ConstraintMessageHook = Callable[[IntegrityError], str | None]


class WireContext(Protocol):
    """Structural type for the proto ``TenantContext`` carried on the wire."""

    tenant_id: str
    user_id: str


def resolve_identity_connect(
    wire_context: WireContext,
    *,
    accepted_services: frozenset[str] | None = None,
) -> tuple[UUID, UUID]:
    """Verified ``(tenant_id, user_id)`` for a connectrpc servicer call.

    Derives identity from the authenticated principal (the JWT, via
    ``AuthMiddleware``'s ContextVar) rather than trusting the wire ``context``,
    and rejects a request whose wire tenant doesn't match the token. Maps the
    transport-neutral :class:`AuthError` to the matching ``ConnectError`` code.
    ``accepted_services`` forwards to :func:`resolve_identity` (else the
    ``AUTH_ACCEPTED_SERVICES`` env allowlist applies).
    """
    try:
        return resolve_identity(
            wire_context.tenant_id or None,
            wire_context.user_id or None,
            accepted_services=accepted_services,
        )
    except AuthError as err:
        raise ConnectError(
            _AUTH_CODE_TO_CONNECT.get(err.code, Code.UNAUTHENTICATED), err.message
        ) from err


def parse_uuid(value: str, field_name: str = "id") -> UUID:
    """Parse a UUID string, raising ``ConnectError(INVALID_ARGUMENT)`` on failure.

    An empty value is reported as required; anything unparseable is reported as
    not a valid UUID, so a client sees which field was wrong without leaking
    internal detail.
    """
    if not value:
        raise ConnectError(Code.INVALID_ARGUMENT, f"{field_name} is required")
    try:
        return UUID(value)
    except ValueError, TypeError:
        raise ConnectError(Code.INVALID_ARGUMENT, f"Invalid {field_name}: must be a valid UUID")


@overload
def handle_service_errors[**P, T](
    func: Callable[P, Coroutine[Any, Any, T]],
) -> Callable[P, Coroutine[Any, Any, T]]: ...


@overload
def handle_service_errors[**P, T](
    *,
    on_integrity_error: ConstraintMessageHook | None = None,
) -> Callable[[Callable[P, Coroutine[Any, Any, T]]], Callable[P, Coroutine[Any, Any, T]]]: ...


def handle_service_errors[**P, T](
    func: Callable[P, Coroutine[Any, Any, T]] | None = None,
    *,
    on_integrity_error: ConstraintMessageHook | None = None,
) -> (
    Callable[P, Coroutine[Any, Any, T]]
    | Callable[[Callable[P, Coroutine[Any, Any, T]]], Callable[P, Coroutine[Any, Any, T]]]
):
    """Map database and service exceptions to user-safe ``ConnectError`` responses.

    Usable bare (``@handle_service_errors``) or with a hook
    (``@handle_service_errors(on_integrity_error=...)``). The mapping:

    - ConnectError: re-raised unchanged (already user-facing)
    - IntegrityError: ``on_integrity_error`` message if it returns one, else the
      generic constraint-violation message (FAILED_PRECONDITION)
    - OperationalError: database temporarily unavailable (UNAVAILABLE)
    - SQLAlchemyError: internal database error (INTERNAL)
    - ValueError: its message as INVALID_ARGUMENT. A ``ValueError`` raised from a
      service layer is this codebase's explicit validation channel (e.g.
      "Unknown template parameter"), so its text is surfaced deliberately; never
      raise ``ValueError`` from a service with text unfit for a client.
    - anything else: generic internal error (INTERNAL), logged with a traceback

    Database and unexpected-error text is never returned to the client. Only the
    ConnectError and ValueError channels, both user-facing by construction, pass
    their own message through.
    """

    def decorate(fn: Callable[P, Coroutine[Any, Any, T]]) -> Callable[P, Coroutine[Any, Any, T]]:
        @wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            try:
                return await fn(*args, **kwargs)
            except ConnectError:
                raise
            except IntegrityError as e:
                logger.warning("Integrity error in %s: %s", fn.__name__, e)
                message = on_integrity_error(e) if on_integrity_error is not None else None
                raise ConnectError(Code.FAILED_PRECONDITION, message or _DEFAULT_INTEGRITY_MESSAGE)
            except OperationalError as e:
                logger.error("Database operational error in %s: %s", fn.__name__, e)
                raise ConnectError(
                    Code.UNAVAILABLE, "Database temporarily unavailable. Please try again."
                )
            except SQLAlchemyError as e:
                logger.error("Database error in %s: %s", fn.__name__, e)
                raise ConnectError(
                    Code.INTERNAL, "An internal database error occurred. Please try again."
                )
            except ValueError as e:
                logger.warning("Value error in %s: %s", fn.__name__, e)
                raise ConnectError(Code.INVALID_ARGUMENT, str(e))
            except Exception as e:
                logger.exception("Unexpected error in %s: %s", fn.__name__, e)
                raise ConnectError(Code.INTERNAL, "An unexpected error occurred. Please try again.")

        return wrapper

    return decorate if func is None else decorate(func)
