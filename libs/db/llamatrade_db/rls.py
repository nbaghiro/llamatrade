"""Postgres row-level security (RLS) — defense-in-depth tenant isolation.

A tenant-scoped table can be locked down so that, even if an application query
forgets its ``WHERE tenant_id = ...`` filter, Postgres exposes only rows for the
tenant bound to the current transaction. The binding is a transaction-local GUC
(``app.current_tenant``), set from the request's *verified* identity by
:func:`llamatrade_db.set_tenant_guc` / :func:`llamatrade_db.tenant_session`.

Two access modes:

- **tenant** — ``app.current_tenant`` = a tenant UUID → only that tenant's rows.
  Unset (or blank) → **zero** rows (fail-closed).
- **system** — ``app.rls_bypass`` = ``'on'`` → policies pass unconditionally, for
  trusted, non-request background sweeps that legitimately span tenants (equity
  snapshot, reconciliation). Set only by server code via
  :func:`llamatrade_db.system_session`; never influenced by request input.

``FORCE ROW LEVEL SECURITY`` makes the policy apply to the table *owner* too;
without it, the owning role (which migrations run as) silently bypasses RLS. Note
a Postgres **superuser** bypasses RLS regardless — the application (and the RLS
tests) must connect as a non-superuser role for enforcement to take effect.
"""

from __future__ import annotations

TENANT_GUC = "app.current_tenant"
BYPASS_GUC = "app.rls_bypass"

# A row is visible when a trusted system bypass is active, or the row's tenant
# matches the transaction-local tenant GUC. ``NULLIF(..., '')`` maps an unset or
# blank GUC to NULL so ``tenant_id = NULL`` yields no rows (fail-closed) instead
# of raising on an invalid-uuid cast.
_PREDICATE = (
    f"(current_setting('{BYPASS_GUC}', true) = 'on' "
    f"OR tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid)"
)

# Every tenant-scoped ledger table (all carry ``tenant_id`` via ``TenantMixin``).
LEDGER_RLS_TABLES: tuple[str, ...] = (
    "ledger_accounts",
    "ledger_sleeves",
    "ledger_lots",
    "ledger_events",
    "ledger_sleeve_snapshots",
)

# Every tenant-scoped table platform-wide (carries ``tenant_id`` via
# ``TenantMixin``). Keep in sync with the models:
# ``test_rls_tables_match_tenant_scoped_metadata`` fails on drift.
RLS_TABLES: tuple[str, ...] = (
    # agent
    "agent_sessions",
    "agent_messages",
    "pending_artifacts",
    "tool_call_logs",
    "agent_memory_facts",
    # auth / identity
    "users",
    "alpaca_credentials",
    "api_keys",
    # audit / risk
    "audit_logs",
    "risk_configs",
    "daily_pnl",
    # backtest
    "backtests",
    # billing
    "subscriptions",
    "usage_records",
    "invoices",
    "payment_methods",
    # ledger
    "ledger_accounts",
    "ledger_sleeves",
    "ledger_lots",
    "ledger_events",
    "ledger_sleeve_snapshots",
    # notification
    "alerts",
    "notifications",
    "notification_channels",
    "webhooks",
    # strategy
    "strategies",
    "strategy_versions",
    "strategy_executions",
    # trading
    "trading_sessions",
    "orders",
    "positions",
)


def _policy_name(table: str) -> str:
    return f"{table}_tenant_isolation"


def enable_rls_statements(table: str) -> list[str]:
    """DDL enabling fail-closed tenant RLS on ``table`` (safe to re-run)."""
    policy = _policy_name(table)
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS {policy} ON {table}",
        f"CREATE POLICY {policy} ON {table} USING {_PREDICATE} WITH CHECK {_PREDICATE}",
    ]


def disable_rls_statements(table: str) -> list[str]:
    """DDL reverting :func:`enable_rls_statements` on ``table``."""
    policy = _policy_name(table)
    return [
        f"DROP POLICY IF EXISTS {policy} ON {table}",
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
    ]
