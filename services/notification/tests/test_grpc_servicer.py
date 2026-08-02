"""Servicer unit tests: validation and error paths that resolve before the DB.

DB-backed behavior is covered by tests/integration/; these tests pin the
argument validation, the UNIMPLEMENTED alert surface, and channel-test gating.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError

from llamatrade_proto.generated import common_pb2, notification_pb2

from src.grpc.servicer import NotificationServicer

TEST_TENANT_ID = "11111111-1111-1111-1111-111111111111"
TEST_USER_ID = "22222222-2222-2222-2222-222222222222"

pytestmark = pytest.mark.asyncio


class MockRequestContext:
    """Placeholder Connect request context; the servicer never calls into it."""


def _ctx() -> common_pb2.TenantContext:
    return common_pb2.TenantContext(tenant_id=TEST_TENANT_ID, user_id=TEST_USER_ID)


def _servicer() -> NotificationServicer:
    return NotificationServicer(session_maker=MagicMock())


async def test_mark_as_read_requires_id_or_all() -> None:
    with pytest.raises(ConnectError) as exc:
        await _servicer().mark_as_read(
            notification_pb2.MarkAsReadRequest(context=_ctx()), MockRequestContext()
        )
    assert exc.value.code == Code.INVALID_ARGUMENT


async def test_missing_identity_rejected() -> None:
    with pytest.raises(ConnectError) as exc:
        await _servicer().list_notifications(
            notification_pb2.ListNotificationsRequest(), MockRequestContext()
        )
    assert exc.value.code in (Code.UNAUTHENTICATED, Code.INVALID_ARGUMENT)


async def test_test_channel_rejects_non_email() -> None:
    response = await _servicer().test_channel(
        notification_pb2.TestChannelRequest(context=_ctx(), type=notification_pb2.CHANNEL_TYPE_SMS),
        MockRequestContext(),
    )
    assert response.success is False
    assert "TestWebhook" in response.message


async def test_create_alert_requires_condition_type() -> None:
    with pytest.raises(ConnectError) as exc:
        await _servicer().create_alert(
            notification_pb2.CreateAlertRequest(context=_ctx(), name="a"),
            MockRequestContext(),
        )
    assert exc.value.code == Code.INVALID_ARGUMENT
