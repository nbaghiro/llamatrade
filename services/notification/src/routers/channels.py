"""Channels router - notification channel configuration."""

from fastapi import APIRouter, Depends
from llamatrade_common.middleware import TenantContext, require_auth

from src.models import ChannelConfig, ChannelType, WebhookConfig

router = APIRouter()


@router.get("", response_model=list[ChannelConfig])
async def list_channels(ctx: TenantContext = Depends(require_auth)) -> list[ChannelConfig]:
    """List configured notification channels."""
    return [
        ChannelConfig(type=ChannelType.EMAIL, is_enabled=True),
        ChannelConfig(type=ChannelType.WEBHOOK, is_enabled=False),
    ]


@router.put("/{channel_type}", response_model=ChannelConfig)
async def update_channel(
    channel_type: ChannelType,
    config: dict[str, str],
    ctx: TenantContext = Depends(require_auth),
) -> ChannelConfig:
    """Update channel configuration."""
    # The config dict will be validated by Pydantic at runtime
    return ChannelConfig.model_validate(
        {"type": channel_type, "is_enabled": True, "config": config}
    )


@router.post("/webhooks", response_model=dict)
async def register_webhook(
    webhook: WebhookConfig,
    ctx: TenantContext = Depends(require_auth),
) -> dict[str, str]:
    """Register a webhook endpoint."""
    return {"status": "registered", "url": webhook.url}


@router.post("/test/{channel_type}")
async def test_channel(
    channel_type: ChannelType,
    ctx: TenantContext = Depends(require_auth),
) -> dict[str, str]:
    """Send a test notification through a channel."""
    return {"status": "sent", "channel": channel_type}
