"""Unit tests for the RLS policy DDL builders (no database needed)."""

import importlib
import pkgutil

from llamatrade_db.rls import (
    BYPASS_GUC,
    LEDGER_RLS_TABLES,
    RLS_EXEMPT_TABLES,
    RLS_TABLES,
    TENANT_GUC,
    disable_rls_statements,
    enable_rls_statements,
)


def _model_tables() -> tuple[set[str], set[str]]:
    """(tenant_scoped, non_tenant_scoped) table names across the real models."""
    import llamatrade_db.models as models_pkg

    for mod in pkgutil.iter_modules(models_pkg.__path__):
        importlib.import_module(f"llamatrade_db.models.{mod.name}")
    from llamatrade_db.base import Base

    # Only real model classes (test suites register throwaway models on the same
    # shared Base.metadata, so filter by defining module).
    tenant: set[str] = set()
    non_tenant: set[str] = set()
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if not cls.__module__.startswith("llamatrade_db.models"):
            continue
        if "tenant_id" in cls.__table__.columns:
            tenant.add(cls.__tablename__)
        else:
            non_tenant.add(cls.__tablename__)
    return tenant, non_tenant


def test_rls_tables_match_tenant_scoped_metadata() -> None:
    """RLS_TABLES must cover EXACTLY every tenant-scoped table.

    Fails if a new ``tenant_id`` table is added without RLS coverage (or a table
    is dropped), so the platform-wide RLS migration can never silently miss one.
    """
    tenant_tables, _ = _model_tables()
    assert set(RLS_TABLES) == tenant_tables
    assert len(RLS_TABLES) == len(set(RLS_TABLES))  # no duplicates
    assert set(LEDGER_RLS_TABLES) <= set(RLS_TABLES)


def test_non_tenant_tables_are_declared_exemptions() -> None:
    """Every table WITHOUT a tenant_id must be a documented RLS exemption.

    A child-keyed table holding tenant data (e.g. ``backtest_results`` before
    039) has no ``tenant_id`` column, so the metadata parity check above cannot
    see it. This asserts the exempt set is EXACTLY the non-tenant tables, so a
    new such table forces a conscious choice: give it a ``tenant_id`` (moving it
    under RLS) or record it in ``RLS_EXEMPT_TABLES`` with a reason.
    """
    _, non_tenant_tables = _model_tables()
    assert non_tenant_tables == set(RLS_EXEMPT_TABLES)
    assert set(RLS_TABLES).isdisjoint(RLS_EXEMPT_TABLES)


def test_gucs_are_namespaced() -> None:
    assert TENANT_GUC == "app.current_tenant"
    assert BYPASS_GUC == "app.rls_bypass"


def test_enable_statements_shape() -> None:
    stmts = enable_rls_statements("ledger_accounts")
    assert stmts[0] == "ALTER TABLE ledger_accounts ENABLE ROW LEVEL SECURITY"
    assert stmts[1] == "ALTER TABLE ledger_accounts FORCE ROW LEVEL SECURITY"
    assert stmts[2] == "DROP POLICY IF EXISTS ledger_accounts_tenant_isolation ON ledger_accounts"
    create = stmts[3]
    assert create.startswith("CREATE POLICY ledger_accounts_tenant_isolation ON ledger_accounts")
    # Fail-closed tenant match + trusted system bypass, on both USING and WITH CHECK.
    assert "USING" in create and "WITH CHECK" in create
    assert f"current_setting('{BYPASS_GUC}', true) = 'on'" in create
    assert f"NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid" in create


def test_disable_statements_reverse_enable() -> None:
    stmts = disable_rls_statements("ledger_sleeves")
    assert stmts == [
        "DROP POLICY IF EXISTS ledger_sleeves_tenant_isolation ON ledger_sleeves",
        "ALTER TABLE ledger_sleeves NO FORCE ROW LEVEL SECURITY",
        "ALTER TABLE ledger_sleeves DISABLE ROW LEVEL SECURITY",
    ]


def test_ledger_tables_cover_every_tenant_scoped_ledger_table() -> None:
    assert LEDGER_RLS_TABLES == (
        "ledger_accounts",
        "ledger_sleeves",
        "ledger_lots",
        "ledger_events",
        "ledger_sleeve_snapshots",
        "ledger_projection_checkpoints",
    )
