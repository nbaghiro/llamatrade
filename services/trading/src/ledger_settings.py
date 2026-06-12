"""Feature flags for the portfolio-ledger rollout (trading side).

Mirrors ``services/portfolio/src/ledger/settings.py`` — the flags are
deliberately read per-service from the environment so each service can be
rolled independently. Defaults are off (zero behavior change).

- ``LEDGER_SHADOW_MODE``: trading emits ledger fill events (portfolio ingests
  read-only); nothing about execution behavior changes.
- ``LEDGER_EXECUTION``: trading sizes/risks against sleeves and reserves cash.
"""

from __future__ import annotations

import os

_TRUE = {"1", "true", "yes", "on"}


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE


def shadow_mode_enabled() -> bool:
    """Emit ledger fill events for portfolio's read-only shadow ingestion."""
    return _flag("LEDGER_SHADOW_MODE")


def execution_enabled() -> bool:
    """Sleeve-aware sizing/risk/reservations are authoritative."""
    return _flag("LEDGER_EXECUTION")
