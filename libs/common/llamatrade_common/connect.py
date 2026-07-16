"""connectrpc adapter for the shared auth mechanism.

Kept out of ``auth.py`` so that module stays free of the ``connectrpc`` import.
Every connectrpc servicer resolves request identity through
``resolve_identity_connect`` — the transport-neutral :func:`resolve_identity`
plus a mapping of :class:`AuthError` to :class:`connectrpc.errors.ConnectError`.
The grpc.aio equivalent lives in each grpc servicer (see trading's
``_identity`` / ``_abort_auth``).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from connectrpc.code import Code
from connectrpc.errors import ConnectError

from llamatrade_common.auth import AuthError, resolve_identity

_AUTH_CODE_TO_CONNECT = {
    "unauthenticated": Code.UNAUTHENTICATED,
    "permission_denied": Code.PERMISSION_DENIED,
    "invalid_argument": Code.INVALID_ARGUMENT,
}


class WireContext(Protocol):
    """Structural type for the proto ``TenantContext`` carried on the wire."""

    tenant_id: str
    user_id: str


def resolve_identity_connect(wire_context: WireContext) -> tuple[UUID, UUID]:
    """Verified ``(tenant_id, user_id)`` for a connectrpc servicer call.

    Derives identity from the authenticated principal (the JWT, via
    ``AuthMiddleware``'s ContextVar) rather than trusting the wire ``context``,
    and rejects a request whose wire tenant doesn't match the token. Maps the
    transport-neutral :class:`AuthError` to the matching ``ConnectError`` code.
    """
    try:
        return resolve_identity(
            wire_context.tenant_id or None,
            wire_context.user_id or None,
        )
    except AuthError as err:
        raise ConnectError(
            _AUTH_CODE_TO_CONNECT.get(err.code, Code.UNAUTHENTICATED), err.message
        ) from err
