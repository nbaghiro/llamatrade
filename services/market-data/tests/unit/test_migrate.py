"""Unit tests for the migration statement splitter + discovery (no DB)."""

from src.store import migrate
from src.store.migrate import discover_migrations, split_statements


class TestSplitStatements:
    def test_simple_split(self) -> None:
        assert split_statements("SELECT 1; SELECT 2;") == ["SELECT 1", "SELECT 2"]

    def test_trailing_statement_without_semicolon(self) -> None:
        assert split_statements("SELECT 1") == ["SELECT 1"]

    def test_strips_full_line_comments(self) -> None:
        sql = "-- a comment\nSELECT 1;\n-- another\nSELECT 2;"
        assert split_statements(sql) == ["SELECT 1", "SELECT 2"]

    def test_strips_trailing_inline_comments(self) -> None:
        sql = "SELECT 1; -- inline\nSELECT 2;"
        assert split_statements(sql) == ["SELECT 1", "SELECT 2"]

    def test_blank_and_whitespace_only_dropped(self) -> None:
        assert split_statements("\n\n  ;  \n;SELECT 1;\n\n") == ["SELECT 1"]

    def test_multiline_statement_preserved(self) -> None:
        sql = "CREATE TABLE x (\n  a int,\n  b int\n);"
        stmts = split_statements(sql)
        assert len(stmts) == 1
        assert "CREATE TABLE x" in stmts[0]
        assert "a int" in stmts[0]

    def test_empty_input(self) -> None:
        assert split_statements("") == []
        assert split_statements("-- only a comment") == []


class TestDiscoverMigrations:
    def test_finds_shipped_migrations_in_order(self) -> None:
        files = discover_migrations()
        stems = [p.stem for p in files]
        # The three foundation migrations must be discovered, sorted.
        assert stems == sorted(stems)
        assert "0001_init" in stems
        assert "0002_aggregates" in stems
        assert "0003_policies" in stems

    def test_each_shipped_migration_parses_into_statements(self) -> None:
        # Every shipped migration must split into at least one runnable statement.
        for path in discover_migrations():
            assert split_statements(path.read_text()), f"{path.name} yielded no statements"

    def test_init_migration_creates_hypertables(self) -> None:
        init = next(p for p in discover_migrations() if p.stem == "0001_init")
        body = init.read_text()
        assert "create_hypertable('bars_1m'" in body
        assert "create_hypertable('bars_daily'" in body

    def test_migrations_dir_constant_points_at_sql(self) -> None:
        assert migrate.MIGRATIONS_DIR.name == "migrations"
