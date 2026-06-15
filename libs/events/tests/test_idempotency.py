"""Idempotency primitives."""

from __future__ import annotations

from llamatrade_events.idempotency import InMemoryDedupStore, derive_event_id


def test_derive_event_id_is_deterministic() -> None:
    assert derive_event_id("client-order-1") == derive_event_id("client-order-1")


def test_derive_event_id_distinguishes_parts() -> None:
    # The reservation seed (client_order_id:event_type) differs from the fill seed.
    assert derive_event_id("co1") != derive_event_id("co1", "order_submitted")
    assert derive_event_id("a", "b") != derive_event_id("b", "a")


def test_derive_event_id_length() -> None:
    assert len(derive_event_id("x")) == 16
    assert len(derive_event_id("x", length=32)) == 32


async def test_in_memory_dedup_store() -> None:
    store = InMemoryDedupStore()
    assert await store.seen("e1") is False
    await store.mark("e1")
    assert await store.seen("e1") is True
    assert await store.seen("e2") is False
