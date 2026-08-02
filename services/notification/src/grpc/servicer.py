"""Notification Connect servicer implementation."""

from __future__ import annotations

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from connectrpc.request import RequestContext
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_common.connect import handle_service_errors, resolve_identity_connect
from llamatrade_db import get_session_maker, tenant_session
from llamatrade_db.models.notification import Alert, Notification, Webhook
from llamatrade_proto.generated import common_pb2, events_pb2, notification_pb2
from llamatrade_proto.timestamps import to_proto_timestamp

from src.channels.email import EmailChannel
from src.channels.webhook import WebhookChannel
from src.email_render import build_html
from src.pipeline import email_recipients
from src.services.notification_service import (
    ChannelPrefState,
    NotFoundError,
    NotificationService,
    WebhookValidationError,
)
from src.templates import Rendered


class NotificationServicer:
    """Connect servicer for the Notification service.

    Serves the persisted notification tables; the durable consumer in
    src/tasks/consumer.py is the only writer of notification rows. Alert RPCs
    are served by the price-alert engine (src/alerts/).
    """

    def __init__(
        self,
        session_maker: async_sessionmaker[AsyncSession] | None = None,
        *,
        email: EmailChannel | None = None,
        webhook: WebhookChannel | None = None,
    ) -> None:
        self._maker = session_maker or get_session_maker()
        self._email = email or EmailChannel()
        self._webhook = webhook or WebhookChannel()

    # --- notifications ---

    @handle_service_errors
    async def list_notifications(
        self,
        request: notification_pb2.ListNotificationsRequest,
        ctx: RequestContext[object, object],
    ) -> notification_pb2.ListNotificationsResponse:
        tenant_id, _ = resolve_identity_connect(request.context)
        page = request.pagination.page if request.HasField("pagination") else 1
        page_size = request.pagination.page_size if request.HasField("pagination") else 20
        page, page_size = max(page, 1), min(max(page_size, 1), 100)

        async with tenant_session(tenant_id, self._maker) as db:
            result = await NotificationService(db).list_notifications(
                tenant_id, unread_only=request.unread_only, page=page, page_size=page_size
            )

        total_pages = (result.total + page_size - 1) // page_size if result.total else 0
        return notification_pb2.ListNotificationsResponse(
            notifications=[_to_proto_notification(n) for n in result.items],
            pagination=common_pb2.PaginationResponse(
                total_items=result.total,
                total_pages=total_pages,
                current_page=page,
                page_size=page_size,
                has_next=page < total_pages,
                has_previous=page > 1,
            ),
            unread_count=result.unread_count,
        )

    @handle_service_errors
    async def mark_as_read(
        self,
        request: notification_pb2.MarkAsReadRequest,
        ctx: RequestContext[object, object],
    ) -> notification_pb2.MarkAsReadResponse:
        tenant_id, _ = resolve_identity_connect(request.context)
        if not request.mark_all and not request.notification_id:
            raise ConnectError(Code.INVALID_ARGUMENT, "notification_id or mark_all is required")
        try:
            async with tenant_session(tenant_id, self._maker) as db:
                marked = await NotificationService(db).mark_as_read(
                    tenant_id,
                    notification_id=request.notification_id,
                    mark_all=request.mark_all,
                )
                await db.commit()
        except ValueError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, "notification_id must be a UUID") from e
        return notification_pb2.MarkAsReadResponse(marked_count=marked)

    # --- webhooks ---

    @handle_service_errors
    async def list_webhooks(
        self,
        request: notification_pb2.ListWebhooksRequest,
        ctx: RequestContext[object, object],
    ) -> notification_pb2.ListWebhooksResponse:
        tenant_id, _ = resolve_identity_connect(request.context)
        async with tenant_session(tenant_id, self._maker) as db:
            webhooks = await NotificationService(db).list_webhooks(tenant_id)
            protos = [_to_proto_webhook(w) for w in webhooks]
        return notification_pb2.ListWebhooksResponse(webhooks=protos)

    @handle_service_errors
    async def create_webhook(
        self,
        request: notification_pb2.CreateWebhookRequest,
        ctx: RequestContext[object, object],
    ) -> notification_pb2.CreateWebhookResponse:
        tenant_id, user_id = resolve_identity_connect(request.context)
        try:
            async with tenant_session(tenant_id, self._maker) as db:
                webhook, secret = await NotificationService(db).create_webhook(
                    tenant_id,
                    user_id,
                    name=request.name,
                    url=request.url,
                    events=list(request.events),
                )
                await db.commit()
                await db.refresh(webhook)
                proto = _to_proto_webhook(webhook)
        except WebhookValidationError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e)) from e
        return notification_pb2.CreateWebhookResponse(webhook=proto, secret=secret)

    @handle_service_errors
    async def update_webhook(
        self,
        request: notification_pb2.UpdateWebhookRequest,
        ctx: RequestContext[object, object],
    ) -> notification_pb2.UpdateWebhookResponse:
        tenant_id, _ = resolve_identity_connect(request.context)
        try:
            async with tenant_session(tenant_id, self._maker) as db:
                webhook = await NotificationService(db).update_webhook(
                    tenant_id,
                    webhook_id=request.webhook_id,
                    name=request.name,
                    url=request.url,
                    events=list(request.events),
                    is_active=request.is_active,
                )
                await db.commit()
                await db.refresh(webhook)
                proto = _to_proto_webhook(webhook)
        except WebhookValidationError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e)) from e
        except NotFoundError as e:
            raise ConnectError(Code.NOT_FOUND, str(e)) from e
        return notification_pb2.UpdateWebhookResponse(webhook=proto)

    @handle_service_errors
    async def delete_webhook(
        self,
        request: notification_pb2.DeleteWebhookRequest,
        ctx: RequestContext[object, object],
    ) -> notification_pb2.DeleteWebhookResponse:
        tenant_id, _ = resolve_identity_connect(request.context)
        try:
            async with tenant_session(tenant_id, self._maker) as db:
                await NotificationService(db).delete_webhook(
                    tenant_id, webhook_id=request.webhook_id
                )
                await db.commit()
        except WebhookValidationError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e)) from e
        except NotFoundError as e:
            raise ConnectError(Code.NOT_FOUND, str(e)) from e
        return notification_pb2.DeleteWebhookResponse(success=True)

    @handle_service_errors
    async def test_webhook(
        self,
        request: notification_pb2.TestWebhookRequest,
        ctx: RequestContext[object, object],
    ) -> notification_pb2.TestWebhookResponse:
        tenant_id, _ = resolve_identity_connect(request.context)
        try:
            async with tenant_session(tenant_id, self._maker) as db:
                webhook = await NotificationService(db).get_webhook(tenant_id, request.webhook_id)
                url, secret = webhook.url, webhook.secret
                headers = dict(webhook.headers) if webhook.headers else None
        except WebhookValidationError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e)) from e
        except NotFoundError as e:
            raise ConnectError(Code.NOT_FOUND, str(e)) from e
        result = await self._webhook.send(
            url,
            {"category": 0, "title": "Test notification", "message": "LlamaTrade webhook test."},
            secret=secret,
            headers=headers,
        )
        return notification_pb2.TestWebhookResponse(
            success=result.ok,
            status_code=result.status_code or 0,
            message="delivered" if result.ok else (result.error or f"http_{result.status_code}"),
        )

    # --- preferences and channels ---

    @handle_service_errors
    async def get_preferences(
        self,
        request: notification_pb2.GetPreferencesRequest,
        ctx: RequestContext[object, object],
    ) -> notification_pb2.GetPreferencesResponse:
        tenant_id, _ = resolve_identity_connect(request.context)
        async with tenant_session(tenant_id, self._maker) as db:
            states = await NotificationService(db).get_preferences(tenant_id)
        return notification_pb2.GetPreferencesResponse(
            preferences=[_to_proto_pref(s) for s in states]
        )

    @handle_service_errors
    async def update_preferences(
        self,
        request: notification_pb2.UpdatePreferencesRequest,
        ctx: RequestContext[object, object],
    ) -> notification_pb2.UpdatePreferencesResponse:
        tenant_id, user_id = resolve_identity_connect(request.context)
        states = [
            ChannelPrefState(channel=p.channel, enabled=p.enabled, categories=list(p.categories))
            for p in request.preferences
        ]
        async with tenant_session(tenant_id, self._maker) as db:
            updated = await NotificationService(db).update_preferences(tenant_id, user_id, states)
            await db.commit()
        return notification_pb2.UpdatePreferencesResponse(
            preferences=[_to_proto_pref(s) for s in updated]
        )

    @handle_service_errors
    async def list_channels(
        self,
        request: notification_pb2.ListChannelsRequest,
        ctx: RequestContext[object, object],
    ) -> notification_pb2.ListChannelsResponse:
        tenant_id, _ = resolve_identity_connect(request.context)
        async with tenant_session(tenant_id, self._maker) as db:
            states = await NotificationService(db).get_preferences(tenant_id)
        return notification_pb2.ListChannelsResponse(
            channels=[_to_proto_channel(tenant_id, s) for s in states]
        )

    @handle_service_errors
    async def update_channel(
        self,
        request: notification_pb2.UpdateChannelRequest,
        ctx: RequestContext[object, object],
    ) -> notification_pb2.UpdateChannelResponse:
        tenant_id, user_id = resolve_identity_connect(request.context)
        state = ChannelPrefState(channel=request.type, enabled=request.is_enabled, categories=[])
        async with tenant_session(tenant_id, self._maker) as db:
            updated = await NotificationService(db).update_preferences(tenant_id, user_id, [state])
            await db.commit()
        current = next((s for s in updated if s.channel == request.type), state)
        return notification_pb2.UpdateChannelResponse(channel=_to_proto_channel(tenant_id, current))

    @handle_service_errors
    async def test_channel(
        self,
        request: notification_pb2.TestChannelRequest,
        ctx: RequestContext[object, object],
    ) -> notification_pb2.TestChannelResponse:
        tenant_id, _ = resolve_identity_connect(request.context)
        if request.type != notification_pb2.CHANNEL_TYPE_EMAIL:
            return notification_pb2.TestChannelResponse(
                success=False, message="only email supports channel tests; use TestWebhook"
            )
        async with tenant_session(tenant_id, self._maker) as db:
            recipients = await email_recipients(db, tenant_id)
        if not recipients:
            return notification_pb2.TestChannelResponse(
                success=False, message="no email destination configured"
            )
        test_rendered = Rendered(title="Test notification", message="Email delivery is working.")
        ok = await self._email.send(
            recipients[0],
            test_rendered.subject,
            test_rendered.message,
            html_body=build_html(test_rendered, events_pb2.NOTIFICATION_SEVERITY_INFO),
        )
        return notification_pb2.TestChannelResponse(
            success=ok, message="delivered" if ok else "smtp send failed"
        )

    # --- price alerts ---

    @handle_service_errors
    async def list_alerts(
        self,
        request: notification_pb2.ListAlertsRequest,
        ctx: RequestContext[object, object],
    ) -> notification_pb2.ListAlertsResponse:
        tenant_id, _ = resolve_identity_connect(request.context)
        async with tenant_session(tenant_id, self._maker) as db:
            alerts = await NotificationService(db).list_alerts(
                tenant_id, active_only=request.active_only
            )
            protos = [_to_proto_alert(a) for a in alerts]
        return notification_pb2.ListAlertsResponse(alerts=protos)

    @handle_service_errors
    async def create_alert(
        self,
        request: notification_pb2.CreateAlertRequest,
        ctx: RequestContext[object, object],
    ) -> notification_pb2.CreateAlertResponse:
        tenant_id, user_id = resolve_identity_connect(request.context)
        try:
            async with tenant_session(tenant_id, self._maker) as db:
                alert = await NotificationService(db).create_alert(
                    tenant_id,
                    user_id,
                    name=request.name,
                    description=request.description,
                    condition_type=request.condition.type,
                    symbol=request.condition.symbol,
                    threshold=request.condition.threshold.value,
                    strategy_id=request.condition.strategy_id,
                    channels=list(request.channels),
                    cooldown_minutes=request.cooldown_minutes,
                )
                await db.commit()
                await db.refresh(alert)
                proto = _to_proto_alert(alert)
        except WebhookValidationError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e)) from e
        return notification_pb2.CreateAlertResponse(alert=proto)

    @handle_service_errors
    async def delete_alert(
        self,
        request: notification_pb2.DeleteAlertRequest,
        ctx: RequestContext[object, object],
    ) -> notification_pb2.DeleteAlertResponse:
        tenant_id, _ = resolve_identity_connect(request.context)
        try:
            async with tenant_session(tenant_id, self._maker) as db:
                await NotificationService(db).delete_alert(tenant_id, alert_id=request.alert_id)
                await db.commit()
        except WebhookValidationError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e)) from e
        except NotFoundError as e:
            raise ConnectError(Code.NOT_FOUND, str(e)) from e
        return notification_pb2.DeleteAlertResponse(success=True)

    @handle_service_errors
    async def toggle_alert(
        self,
        request: notification_pb2.ToggleAlertRequest,
        ctx: RequestContext[object, object],
    ) -> notification_pb2.ToggleAlertResponse:
        tenant_id, _ = resolve_identity_connect(request.context)
        try:
            async with tenant_session(tenant_id, self._maker) as db:
                alert = await NotificationService(db).toggle_alert(
                    tenant_id, alert_id=request.alert_id, is_active=request.is_active
                )
                await db.commit()
                await db.refresh(alert)
                proto = _to_proto_alert(alert)
        except WebhookValidationError as e:
            raise ConnectError(Code.INVALID_ARGUMENT, str(e)) from e
        except NotFoundError as e:
            raise ConnectError(Code.NOT_FOUND, str(e)) from e
        return notification_pb2.ToggleAlertResponse(alert=proto)


def _to_proto_notification(row: Notification) -> notification_pb2.Notification:
    metadata = {str(k): str(v) for k, v in (row.data or {}).items()}
    metadata["category"] = str(row.category)
    metadata["severity"] = str(row.severity)
    proto = notification_pb2.Notification(
        id=str(row.id),
        tenant_id=str(row.tenant_id),
        user_id=str(row.user_id) if row.user_id else "",
        type=row.notification_type,
        title=row.title,
        message=row.message,
        is_read=row.read_at is not None,
        metadata=metadata,
        created_at=to_proto_timestamp(row.created_at),
    )
    if row.read_at is not None:
        proto.read_at.CopyFrom(to_proto_timestamp(row.read_at))
    return proto


def _to_proto_webhook(row: Webhook) -> notification_pb2.Webhook:
    proto = notification_pb2.Webhook(
        id=str(row.id),
        tenant_id=str(row.tenant_id),
        name=row.name,
        url=row.url,
        events=[events_pb2.NotificationCategory.ValueType(int(e)) for e in (row.events or [])],
        is_active=row.is_active,
        failure_count=row.failure_count,
        last_status_code=row.last_status_code or 0,
        created_at=to_proto_timestamp(row.created_at),
        updated_at=to_proto_timestamp(row.updated_at),
    )
    if row.last_triggered_at is not None:
        proto.last_triggered_at.CopyFrom(to_proto_timestamp(row.last_triggered_at))
    return proto


def _to_proto_alert(row: Alert) -> notification_pb2.Alert:
    condition = row.condition or {}
    proto = notification_pb2.Alert(
        id=str(row.id),
        tenant_id=str(row.tenant_id),
        user_id=str(row.created_by),
        name=row.name,
        description=str(condition.get("description", "")),
        is_active=row.status == notification_pb2.ALERT_STATUS_ACTIVE,
        condition=notification_pb2.AlertCondition(
            type=row.alert_type,
            symbol=row.symbol or "",
            threshold=common_pb2.Decimal(value=str(condition.get("threshold", "0"))),
            strategy_id=str(condition.get("strategy_id", "")),
        ),
        channels=[notification_pb2.ChannelType.ValueType(int(c)) for c in (row.channels or [])],
        cooldown_minutes=row.cooldown_minutes,
        times_triggered=row.trigger_count,
        created_at=to_proto_timestamp(row.created_at),
        updated_at=to_proto_timestamp(row.updated_at),
    )
    if row.last_triggered_at is not None:
        proto.last_triggered_at.CopyFrom(to_proto_timestamp(row.last_triggered_at))
    return proto


def _to_proto_pref(state: ChannelPrefState) -> notification_pb2.ChannelPreference:
    return notification_pb2.ChannelPreference(
        channel=state.channel, enabled=state.enabled, categories=state.categories
    )


def _to_proto_channel(tenant_id: object, state: ChannelPrefState) -> notification_pb2.Channel:
    return notification_pb2.Channel(
        tenant_id=str(tenant_id),
        type=state.channel,
        is_enabled=state.enabled,
        is_verified=state.channel == notification_pb2.CHANNEL_TYPE_EMAIL,
    )
