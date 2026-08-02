"""Broker symbol lifecycle: whether a subscribed symbol can still be traded.

Both the session-start preflight and the live runner's periodic asset probe ask
the same question of an Alpaca asset record, so the classification lives here.
"""

from __future__ import annotations

from llamatrade_alpaca import Asset

# Why a symbol cannot be traded (bounded set — safe as a metric label).
HALT_UNKNOWN = "unknown"
HALT_INACTIVE = "inactive"
HALT_NOT_TRADABLE = "not_tradable"

_HALT_DESCRIPTIONS = {
    HALT_UNKNOWN: "unknown at the broker",
    HALT_INACTIVE: "no longer active (delisted or suspended)",
    HALT_NOT_TRADABLE: "not tradable on this account",
}


def asset_halt_reason(asset: Asset | None) -> str | None:
    """Why ``asset`` cannot be traded, or None when it is active and tradable."""
    if asset is None:
        return HALT_UNKNOWN
    if asset.status.lower() != "active":
        return HALT_INACTIVE
    if not asset.tradable:
        return HALT_NOT_TRADABLE
    return None


def halt_description(reason: str) -> str:
    """Human-readable phrasing for a halt reason, for alerts and error messages."""
    return _HALT_DESCRIPTIONS.get(reason, reason)
