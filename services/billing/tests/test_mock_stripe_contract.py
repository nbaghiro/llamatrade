"""MockStripeClient is spec-checked against the real StripeClient surface.

Signature drift between the canonical test double (tests/conftest.py) and
src/stripe/client.py fails here, so the double cannot silently diverge the
way per-file copies did.
"""

from __future__ import annotations

import inspect

import pytest
from stripe import Customer, Event

from tests.conftest import MockStripeClient

from src.stripe.client import StripeClient


def _public_methods(cls: type) -> set[str]:
    return {
        name for name, _ in inspect.getmembers(cls, inspect.isfunction) if not name.startswith("_")
    }


REAL_METHODS = sorted(_public_methods(StripeClient))


def test_mock_implements_every_public_method() -> None:
    assert _public_methods(StripeClient) <= _public_methods(MockStripeClient)


def test_mock_has_no_stray_methods() -> None:
    """The double must not grow methods the real client lacks (drift in reverse)."""
    assert _public_methods(MockStripeClient) <= _public_methods(StripeClient)


@pytest.mark.parametrize("name", REAL_METHODS)
def test_method_matches_real_client(name: str) -> None:
    """Parameter names, kinds, defaults, and asyncness all match the real client."""
    real_fn = inspect.getattr_static(StripeClient, name)
    mock_fn = inspect.getattr_static(MockStripeClient, name)
    real_shape = [
        (p.name, p.kind, p.default) for p in inspect.signature(real_fn).parameters.values()
    ]
    mock_shape = [
        (p.name, p.kind, p.default) for p in inspect.signature(mock_fn).parameters.values()
    ]
    assert mock_shape == real_shape
    assert inspect.iscoroutinefunction(mock_fn) == inspect.iscoroutinefunction(real_fn)


async def test_get_customer_returns_real_customer_shape() -> None:
    """get_customer yields a real stripe.Customer (id, email, tenant metadata)."""
    mock = MockStripeClient()
    customer_id = await mock.get_or_create_customer("tenant-1", "user@example.com", name="User")

    customer = await mock.get_customer(customer_id)

    assert isinstance(customer, Customer)
    assert customer.id == customer_id
    assert customer.email == "user@example.com"
    assert customer.metadata is not None
    assert customer.metadata["tenant_id"] == "tenant-1"
    assert await mock.get_customer("cus_missing") is None


def test_verify_webhook_signature_returns_typed_event() -> None:
    """The webhook double returns a typed stripe.Event like the real client."""
    mock = MockStripeClient()
    event = mock.verify_webhook_signature(
        payload=b'{"id": "evt_1", "object": "event", "type": "invoice.paid", "data": {}}',
        sig_header="t=1,v1=sig",
        webhook_secret="whsec_test",
    )
    assert isinstance(event, Event)
    assert event.type == "invoice.paid"
