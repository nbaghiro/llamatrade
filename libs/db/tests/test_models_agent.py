"""Tests for llamatrade_db.models.agent module."""

from sqlalchemy import ForeignKey
from sqlalchemy.sql.schema import Column

from llamatrade_db.models.agent import (
    AgentMemoryFact,
    AgentMessage,
    AgentSession,
    PendingArtifact,
    ToolCallLog,
)


def _fk(column: Column[object]) -> ForeignKey:
    (fk,) = column.foreign_keys
    return fk


class TestAgentSession:
    def test_tablename(self) -> None:
        assert AgentSession.__tablename__ == "agent_sessions"

    def test_has_required_columns(self) -> None:
        columns = AgentSession.__table__.columns
        for name in (
            "id",
            "tenant_id",
            "user_id",
            "title",
            "status",
            "message_count",
            "last_activity_at",
            "created_at",
            "updated_at",
        ):
            assert name in columns

    def test_user_id_not_nullable(self) -> None:
        assert AgentSession.__table__.columns["user_id"].nullable is False

    def test_title_nullable(self) -> None:
        assert AgentSession.__table__.columns["title"].nullable is True

    def test_status_defaults_active(self) -> None:
        col = AgentSession.__table__.columns["status"]
        assert col.nullable is False
        assert col.default is not None and col.default.arg == 1

    def test_message_count_defaults_zero(self) -> None:
        col = AgentSession.__table__.columns["message_count"]
        assert col.default is not None and col.default.arg == 0

    def test_last_activity_not_nullable(self) -> None:
        assert AgentSession.__table__.columns["last_activity_at"].nullable is False

    def test_has_expected_indexes(self) -> None:
        names = {i.name for i in AgentSession.__table__.indexes}
        assert {
            "ix_agent_sessions_tenant_user",
            "ix_agent_sessions_tenant_status",
            "ix_agent_sessions_last_activity",
        } <= names

    def test_child_relationships_delete_orphans(self) -> None:
        for rel in ("messages", "pending_artifacts", "tool_call_logs"):
            cascade = getattr(AgentSession, rel).property.cascade
            assert "delete-orphan" in cascade, rel


class TestAgentMessage:
    def test_tablename(self) -> None:
        assert AgentMessage.__tablename__ == "agent_messages"

    def test_has_required_columns(self) -> None:
        columns = AgentMessage.__table__.columns
        for name in (
            "id",
            "tenant_id",
            "session_id",
            "role",
            "content",
            "tool_calls_json",
            "inline_artifact_ids",
            "thinking",
        ):
            assert name in columns

    def test_session_fk_cascades_on_delete(self) -> None:
        fk = _fk(AgentMessage.__table__.columns["session_id"])
        assert fk.column.table.name == "agent_sessions"
        assert fk.ondelete == "CASCADE"

    def test_role_and_content_not_nullable(self) -> None:
        assert AgentMessage.__table__.columns["role"].nullable is False
        assert AgentMessage.__table__.columns["content"].nullable is False

    def test_optional_payloads_nullable(self) -> None:
        columns = AgentMessage.__table__.columns
        assert columns["tool_calls_json"].nullable is True
        assert columns["inline_artifact_ids"].nullable is True
        assert columns["thinking"].nullable is True


class TestPendingArtifact:
    def test_tablename(self) -> None:
        assert PendingArtifact.__tablename__ == "pending_artifacts"

    def test_has_required_columns(self) -> None:
        columns = PendingArtifact.__table__.columns
        for name in (
            "id",
            "tenant_id",
            "session_id",
            "artifact_type",
            "name",
            "description",
            "artifact_json",
            "is_committed",
            "committed_resource_id",
            "committed_at",
        ):
            assert name in columns

    def test_session_fk_cascades_on_delete(self) -> None:
        fk = _fk(PendingArtifact.__table__.columns["session_id"])
        assert fk.column.table.name == "agent_sessions"
        assert fk.ondelete == "CASCADE"

    def test_artifact_type_name_and_json_not_nullable(self) -> None:
        columns = PendingArtifact.__table__.columns
        assert columns["artifact_type"].nullable is False
        assert columns["name"].nullable is False
        assert columns["artifact_json"].nullable is False

    def test_is_committed_defaults_false(self) -> None:
        col = PendingArtifact.__table__.columns["is_committed"]
        assert col.nullable is False
        assert col.default is not None and col.default.arg is False

    def test_commit_fields_nullable_until_committed(self) -> None:
        columns = PendingArtifact.__table__.columns
        assert columns["committed_resource_id"].nullable is True
        assert columns["committed_at"].nullable is True


class TestToolCallLog:
    def test_tablename(self) -> None:
        assert ToolCallLog.__tablename__ == "tool_call_logs"

    def test_has_required_columns(self) -> None:
        columns = ToolCallLog.__table__.columns
        for name in (
            "id",
            "tenant_id",
            "session_id",
            "message_id",
            "tool_name",
            "arguments_json",
            "result_json",
            "duration_ms",
            "success",
            "error_message",
        ):
            assert name in columns

    def test_session_fk_cascades_on_delete(self) -> None:
        fk = _fk(ToolCallLog.__table__.columns["session_id"])
        assert fk.column.table.name == "agent_sessions"
        assert fk.ondelete == "CASCADE"

    def test_message_fk_nulls_on_delete(self) -> None:
        col = ToolCallLog.__table__.columns["message_id"]
        assert col.nullable is True
        fk = _fk(col)
        assert fk.column.table.name == "agent_messages"
        assert fk.ondelete == "SET NULL"

    def test_tool_name_not_nullable(self) -> None:
        assert ToolCallLog.__table__.columns["tool_name"].nullable is False

    def test_success_defaults_true(self) -> None:
        col = ToolCallLog.__table__.columns["success"]
        assert col.nullable is False
        assert col.default is not None and col.default.arg is True


class TestAgentMemoryFact:
    def test_tablename(self) -> None:
        assert AgentMemoryFact.__tablename__ == "agent_memory_facts"

    def test_has_required_columns(self) -> None:
        columns = AgentMemoryFact.__table__.columns
        for name in (
            "id",
            "tenant_id",
            "user_id",
            "category",
            "content",
            "confidence",
            "source_session_id",
            "source_message_id",
            "extraction_method",
            "is_active",
            "supersedes_id",
            "expires_at",
            "last_accessed_at",
            "access_count",
        ):
            assert name in columns

    def test_user_category_content_not_nullable(self) -> None:
        columns = AgentMemoryFact.__table__.columns
        assert columns["user_id"].nullable is False
        assert columns["category"].nullable is False
        assert columns["content"].nullable is False

    def test_confidence_defaults(self) -> None:
        col = AgentMemoryFact.__table__.columns["confidence"]
        assert col.nullable is False
        assert col.default is not None and col.default.arg == 0.7

    def test_extraction_method_defaults_heuristic(self) -> None:
        col = AgentMemoryFact.__table__.columns["extraction_method"]
        assert col.default is not None and col.default.arg == "heuristic"

    def test_is_active_defaults_true(self) -> None:
        col = AgentMemoryFact.__table__.columns["is_active"]
        assert col.default is not None and col.default.arg is True

    def test_access_count_defaults_zero(self) -> None:
        col = AgentMemoryFact.__table__.columns["access_count"]
        assert col.default is not None and col.default.arg == 0

    def test_source_fks_null_on_delete(self) -> None:
        columns = AgentMemoryFact.__table__.columns
        for name, target in (
            ("source_session_id", "agent_sessions"),
            ("source_message_id", "agent_messages"),
        ):
            col = columns[name]
            assert col.nullable is True
            fk = _fk(col)
            assert fk.column.table.name == target
            assert fk.ondelete == "SET NULL"

    def test_supersedes_is_self_referential_set_null(self) -> None:
        fk = _fk(AgentMemoryFact.__table__.columns["supersedes_id"])
        assert fk.column.table.name == "agent_memory_facts"
        assert fk.ondelete == "SET NULL"

    def test_has_expected_indexes(self) -> None:
        names = {i.name for i in AgentMemoryFact.__table__.indexes}
        assert {
            "ix_agent_memory_facts_tenant_user",
            "ix_agent_memory_facts_tenant_category",
            "ix_agent_memory_facts_tenant_active",
            "ix_agent_memory_facts_last_accessed",
        } <= names
