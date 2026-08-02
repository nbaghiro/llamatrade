"""Deterministic ledger event ids.

Idempotent ledger appends key their ``event_id`` off a stable string so a
re-delivered fill, a retried fund op, or a re-detected drift dedups at the
writer (``INSERT ... ON CONFLICT (event_id) DO NOTHING``). The derivation is the
first 16 bytes of ``sha256(key)`` cast to a UUID; every producer must agree on
it byte-for-byte, so it lives here once rather than being re-implemented per
call site.
"""

from __future__ import annotations

import hashlib
from uuid import UUID


def deterministic_event_id(key: str) -> UUID:
    """A stable ledger ``event_id`` (UUID) for an idempotency key.

    The same ``key`` always yields the same id, so at-least-once delivery plus
    the writer's ``event_id`` conflict-do-nothing equals effective-once.
    """
    return UUID(bytes=hashlib.sha256(key.encode()).digest()[:16])
