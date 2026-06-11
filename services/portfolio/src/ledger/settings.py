"""Feature flags for the portfolio ledger rollout.

Phases are gated so each can ship without changing existing behavior:
``LEDGER_SHADOW_MODE`` (Phase 1) → ``LEDGER_SLEEVES`` (Phase 2) →
``LEDGER_EXECUTION`` (Phase 3) → ``LEDGER_DESIRED_STATE`` (Phase 4) →
``LEDGER_NETTING`` (Phase 5). Defaults are off.
"""

from __future__ import annotations

import os

_TRUE = {"1", "true", "yes", "on"}


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE


def shadow_mode_enabled() -> bool:
    """Phase 1: ingest fills and reconcile read-only; drive nothing."""
    return _flag("LEDGER_SHADOW_MODE")


def sleeves_enabled() -> bool:
    """Phase 2: sleeve lifecycle + fund disbursement APIs."""
    return _flag("LEDGER_SLEEVES")


def execution_enabled() -> bool:
    """Phase 3: sleeve-aware sizing/execution is authoritative."""
    return _flag("LEDGER_EXECUTION")


def desired_state_enabled() -> bool:
    """Phase 4: declarative desired-state reconciliation loop."""
    return _flag("LEDGER_DESIRED_STATE")


def netting_enabled() -> bool:
    """Phase 5: block-and-allocate netting / internal crosses."""
    return _flag("LEDGER_NETTING")
