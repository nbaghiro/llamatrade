"""Tests for the @handle_service_errors decorator and parse_uuid (Issue 10A).

This maps DB/technical exceptions to user-facing ConnectError codes; a silent
break here corrupts every error response, so each branch is covered.
"""

from uuid import uuid4

import pytest
from connectrpc.code import Code
from connectrpc.errors import ConnectError
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

from src.grpc.error_handler import handle_service_errors, parse_uuid


def _integrity_error(constraint_msg: str) -> IntegrityError:
    return IntegrityError("INSERT ...", None, Exception(constraint_msg))


async def _raise(exc: Exception) -> None:
    @handle_service_errors
    async def op() -> None:
        raise exc

    await op()


class TestHandleServiceErrors:
    async def test_connect_error_passes_through(self) -> None:
        original = ConnectError(Code.NOT_FOUND, "missing")
        with pytest.raises(ConnectError) as exc:
            await _raise(original)
        assert exc.value is original  # re-raised as-is, not re-wrapped

    async def test_value_error_maps_to_invalid_argument(self) -> None:
        # An unconverted ValueError surfaces as a meaningful 400, not a generic 500.
        with pytest.raises(ConnectError) as exc:
            await _raise(ValueError("bad input"))
        assert exc.value.code == Code.INVALID_ARGUMENT
        assert "bad input" in exc.value.message

    async def test_duplicate_name_integrity(self) -> None:
        with pytest.raises(ConnectError) as exc:
            await _raise(
                _integrity_error(
                    'duplicate key value violates unique constraint "uq_strategy_tenant_name"'
                )
            )
        assert exc.value.code == Code.FAILED_PRECONDITION
        assert "name already exists" in exc.value.message.lower()

    async def test_version_conflict_integrity(self) -> None:
        with pytest.raises(ConnectError) as exc:
            await _raise(
                _integrity_error(
                    'duplicate key value violates unique constraint "uq_version_strategy_version"'
                )
            )
        assert exc.value.code == Code.FAILED_PRECONDITION
        assert "version conflict" in exc.value.message.lower()

    async def test_unknown_integrity_generic_message(self) -> None:
        with pytest.raises(ConnectError) as exc:
            await _raise(_integrity_error("some other constraint blew up"))
        assert exc.value.code == Code.FAILED_PRECONDITION
        assert "constraint" in exc.value.message.lower()

    async def test_operational_error_unavailable(self) -> None:
        with pytest.raises(ConnectError) as exc:
            await _raise(OperationalError("stmt", None, Exception("connection reset")))
        assert exc.value.code == Code.UNAVAILABLE

    async def test_sqlalchemy_error_internal(self) -> None:
        with pytest.raises(ConnectError) as exc:
            await _raise(SQLAlchemyError("boom"))
        assert exc.value.code == Code.INTERNAL

    async def test_unexpected_error_internal(self) -> None:
        with pytest.raises(ConnectError) as exc:
            await _raise(RuntimeError("kaboom"))
        assert exc.value.code == Code.INTERNAL
        assert "unexpected" in exc.value.message.lower()

    async def test_success_passes_value_through(self) -> None:
        @handle_service_errors
        async def op() -> int:
            return 42

        assert await op() == 42


class TestParseUuid:
    def test_valid_uuid(self) -> None:
        u = uuid4()
        assert parse_uuid(str(u), "strategy_id") == u

    def test_invalid_uuid_raises_invalid_argument(self) -> None:
        with pytest.raises(ConnectError) as exc:
            parse_uuid("not-a-uuid", "strategy_id")
        assert exc.value.code == Code.INVALID_ARGUMENT
        assert "strategy_id" in exc.value.message
