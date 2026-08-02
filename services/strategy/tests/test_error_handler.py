"""Tests for the strategy-specific integrity-constraint hook.

The generic error mapping (operational/sqlalchemy/value/unexpected) is covered
by the shared decorator's own tests in ``libs/common``; here we cover only what
this service owns: the ``uq_strategy_tenant_name`` / ``uq_version_strategy_version``
constraint messages and that any other constraint falls back to the generic
message without leaking the raw exception text.
"""

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from sqlalchemy.exc import IntegrityError

from llamatrade_common.connect import handle_service_errors

from src.grpc.servicer import _strategy_integrity_message


def _integrity_error(constraint_msg: str) -> IntegrityError:
    return IntegrityError("INSERT ...", None, Exception(constraint_msg))


class TestStrategyIntegrityMessage:
    def test_duplicate_name_by_constraint_name(self) -> None:
        msg = _strategy_integrity_message(
            _integrity_error(
                'duplicate key value violates unique constraint "uq_strategy_tenant_name"'
            )
        )
        assert msg is not None
        assert "name already exists" in msg.lower()

    def test_version_conflict_by_constraint_name(self) -> None:
        msg = _strategy_integrity_message(
            _integrity_error(
                'duplicate key value violates unique constraint "uq_version_strategy_version"'
            )
        )
        assert msg is not None
        assert "version conflict" in msg.lower()

    def test_unknown_constraint_falls_back_to_generic(self) -> None:
        assert (
            _strategy_integrity_message(_integrity_error("some other constraint blew up")) is None
        )


class TestHookWiredToDecorator:
    """End-to-end: the hook mapped through the shared decorator yields the
    strategy message with FAILED_PRECONDITION and never leaks the raw text."""

    async def _run(self, exc: Exception) -> ConnectError:
        @handle_service_errors(on_integrity_error=_strategy_integrity_message)
        async def op() -> None:
            raise exc

        try:
            await op()
        except ConnectError as e:
            return e
        raise AssertionError("expected ConnectError")

    async def test_duplicate_name_maps_to_failed_precondition(self) -> None:
        err = await self._run(
            _integrity_error(
                'duplicate key value violates unique constraint "uq_strategy_tenant_name"'
            )
        )
        assert err.code == Code.FAILED_PRECONDITION
        assert "name already exists" in err.message.lower()

    async def test_unknown_constraint_uses_generic_message(self) -> None:
        err = await self._run(_integrity_error("secret-table-name detail leaked here"))
        assert err.code == Code.FAILED_PRECONDITION
        assert "secret-table-name" not in err.message
        assert "constraint" in err.message.lower()
