"""SleeveService tests with an in-memory fake repository — no DB, no network."""

import logging
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from llamatrade_db.models.ledger import Account, Sleeve, SleeveStatus, SleeveType

from src.services.sleeve_service import SleeveService

TENANT = uuid4()
CREDS = uuid4()


class FakeSleeveRepository:
    """In-memory SleeveRepository; assigns ids on add (simulating a flush)."""

    def __init__(self) -> None:
        self.accounts: list[Account] = []
        self.sleeves: list[Sleeve] = []

    async def get_account_by_credentials(
        self, tenant_id: UUID, credentials_id: UUID
    ) -> Account | None:
        return next(
            (
                a
                for a in self.accounts
                if a.tenant_id == tenant_id and a.credentials_id == credentials_id
            ),
            None,
        )

    async def get_account_by_broker_id(
        self, tenant_id: UUID, broker_account_id: str
    ) -> Account | None:
        return next(
            (
                a
                for a in self.accounts
                if a.tenant_id == tenant_id and a.alpaca_account_id == broker_account_id
            ),
            None,
        )

    async def add_account(self, account: Account) -> None:
        if account.id is None:
            account.id = uuid4()
        self.accounts.append(account)

    async def set_account_credentials(self, account: Account, credentials_id: UUID) -> None:
        account.credentials_id = credentials_id

    async def set_account_broker_id(self, account: Account, broker_account_id: str) -> None:
        account.alpaca_account_id = broker_account_id

    async def get_sleeve(self, tenant_id: UUID, sleeve_id: UUID) -> Sleeve | None:
        return next(
            (s for s in self.sleeves if s.tenant_id == tenant_id and s.id == sleeve_id), None
        )

    async def get_sleeve_by_type(
        self, tenant_id: UUID, account_id: UUID, sleeve_type: SleeveType
    ) -> Sleeve | None:
        return next(
            (
                s
                for s in self.sleeves
                if s.tenant_id == tenant_id
                and s.account_id == account_id
                and s.type == sleeve_type.value
                and s.strategy_execution_id is None
            ),
            None,
        )

    async def get_strategy_sleeve(
        self, tenant_id: UUID, account_id: UUID, strategy_execution_id: UUID
    ) -> Sleeve | None:
        return next(
            (
                s
                for s in self.sleeves
                if s.tenant_id == tenant_id
                and s.account_id == account_id
                and s.type == SleeveType.STRATEGY.value
                and s.strategy_execution_id == strategy_execution_id
            ),
            None,
        )

    async def list_sleeves(self, tenant_id: UUID, account_id: UUID) -> list[Sleeve]:
        return [s for s in self.sleeves if s.tenant_id == tenant_id and s.account_id == account_id]

    async def add_sleeve(self, sleeve: Sleeve) -> None:
        if sleeve.id is None:
            sleeve.id = uuid4()
        self.sleeves.append(sleeve)


async def test_get_or_create_account_is_idempotent() -> None:
    repo = FakeSleeveRepository()
    svc = SleeveService(cast(Any, repo))
    a1 = await svc.get_or_create_account(TENANT, CREDS)
    a2 = await svc.get_or_create_account(TENANT, CREDS)
    assert a1.id == a2.id
    assert len(repo.accounts) == 1
    assert a1.credentials_id == CREDS


async def test_separate_credentials_get_separate_accounts() -> None:
    repo = FakeSleeveRepository()
    svc = SleeveService(cast(Any, repo))
    a1 = await svc.get_or_create_account(TENANT, CREDS)
    a2 = await svc.get_or_create_account(TENANT, uuid4())
    assert a1.id != a2.id
    assert len(repo.accounts) == 2


async def test_new_account_records_the_broker_account_id() -> None:
    repo = FakeSleeveRepository()
    svc = SleeveService(cast(Any, repo))
    account = await svc.get_or_create_account(TENANT, CREDS, "broker-1")
    assert account.alpaca_account_id == "broker-1"


async def test_re_added_credentials_reuse_the_existing_account() -> None:
    """Deleting and re-adding broker keys must not fork a second book."""
    repo = FakeSleeveRepository()
    svc = SleeveService(cast(Any, repo))
    original = await svc.get_or_create_account(TENANT, CREDS, "broker-1")

    new_creds = uuid4()
    relinked = await svc.get_or_create_account(TENANT, new_creds, "broker-1")

    assert relinked.id == original.id
    assert relinked.credentials_id == new_creds  # re-pointed at the new credential row
    assert relinked.alpaca_account_id == "broker-1"
    assert len(repo.accounts) == 1


async def test_re_link_keeps_the_sleeves_of_the_existing_account() -> None:
    repo = FakeSleeveRepository()
    svc = SleeveService(cast(Any, repo))
    original = await svc.get_or_create_account(TENANT, CREDS, "broker-1")
    before = await svc.ensure_base_sleeves(original)

    relinked = await svc.get_or_create_account(TENANT, uuid4(), "broker-1")
    after = await svc.ensure_base_sleeves(relinked)

    assert {t: s.id for t, s in after.items()} == {t: s.id for t, s in before.items()}
    assert len(repo.sleeves) == 3


async def test_different_broker_accounts_stay_separate() -> None:
    repo = FakeSleeveRepository()
    svc = SleeveService(cast(Any, repo))
    a1 = await svc.get_or_create_account(TENANT, CREDS, "broker-1")
    a2 = await svc.get_or_create_account(TENANT, uuid4(), "broker-2")

    assert a1.id != a2.id
    assert len(repo.accounts) == 2


async def test_same_broker_account_in_another_tenant_is_a_new_account() -> None:
    repo = FakeSleeveRepository()
    svc = SleeveService(cast(Any, repo))
    a1 = await svc.get_or_create_account(TENANT, CREDS, "broker-1")
    a2 = await svc.get_or_create_account(uuid4(), uuid4(), "broker-1")

    assert a1.id != a2.id
    assert len(repo.accounts) == 2


async def test_broker_account_id_is_backfilled_on_next_touch() -> None:
    """An account booked before the broker id was recorded adopts it lazily."""
    repo = FakeSleeveRepository()
    svc = SleeveService(cast(Any, repo))
    account = await svc.get_or_create_account(TENANT, CREDS)
    assert account.alpaca_account_id is None

    again = await svc.get_or_create_account(TENANT, CREDS, "broker-1")

    assert again.id == account.id
    assert again.alpaca_account_id == "broker-1"
    assert len(repo.accounts) == 1


async def test_backfill_is_skipped_when_another_account_claims_the_broker_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Pre-existing duplicates are reported for an operator, never merged."""
    repo = FakeSleeveRepository()
    svc = SleeveService(cast(Any, repo))
    booked = await svc.get_or_create_account(TENANT, CREDS, "broker-1")
    legacy_creds = uuid4()
    legacy = await svc.get_or_create_account(TENANT, legacy_creds)

    with caplog.at_level(logging.ERROR):
        again = await svc.get_or_create_account(TENANT, legacy_creds, "broker-1")

    assert again.id == legacy.id
    assert legacy.alpaca_account_id is None  # not merged, not re-keyed
    assert booked.alpaca_account_id == "broker-1"
    assert len(repo.accounts) == 2
    assert "duplicate ledger accounts" in caplog.text


async def test_credentials_reporting_a_different_broker_account_is_not_re_keyed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The book stays keyed to the broker account it was built from."""
    repo = FakeSleeveRepository()
    svc = SleeveService(cast(Any, repo))
    account = await svc.get_or_create_account(TENANT, CREDS, "broker-1")

    with caplog.at_level(logging.ERROR):
        again = await svc.get_or_create_account(TENANT, CREDS, "broker-2")

    assert again.id == account.id
    assert again.alpaca_account_id == "broker-1"
    assert "booked against broker account broker-1" in caplog.text
    assert "now report broker-2" in caplog.text


async def test_ensure_base_sleeves_creates_three_singletons() -> None:
    repo = FakeSleeveRepository()
    svc = SleeveService(cast(Any, repo))
    acct = await svc.get_or_create_account(TENANT, CREDS)

    first = await svc.ensure_base_sleeves(acct)
    assert set(first) == {SleeveType.UNALLOCATED, SleeveType.MANUAL, SleeveType.UNMANAGED}
    assert len(repo.sleeves) == 3

    # Idempotent: a second call returns the same rows, creates nothing new.
    again = await svc.ensure_base_sleeves(acct)
    assert again[SleeveType.UNALLOCATED].id == first[SleeveType.UNALLOCATED].id
    assert len(repo.sleeves) == 3


async def test_base_sleeves_are_active() -> None:
    repo = FakeSleeveRepository()
    svc = SleeveService(cast(Any, repo))
    acct = await svc.get_or_create_account(TENANT, CREDS)
    u = (await svc.ensure_base_sleeves(acct))[SleeveType.UNALLOCATED]
    assert u.status == SleeveStatus.ACTIVE.value
    assert u.allocated_capital == Decimal("0")
    assert u.strategy_execution_id is None


async def test_unallocated_sleeve_helper() -> None:
    svc = SleeveService(cast(Any, FakeSleeveRepository()))
    acct = await svc.get_or_create_account(TENANT, CREDS)
    u = await svc.unallocated_sleeve(acct)
    assert u.type == SleeveType.UNALLOCATED.value


async def test_strategy_sleeve_one_per_execution() -> None:
    repo = FakeSleeveRepository()
    svc = SleeveService(cast(Any, repo))
    acct = await svc.get_or_create_account(TENANT, CREDS)
    exec_id = uuid4()

    s1 = await svc.get_or_create_strategy_sleeve(acct, exec_id, "MA Cross", Decimal("1000"))
    s2 = await svc.get_or_create_strategy_sleeve(acct, exec_id, "MA Cross", Decimal("1000"))
    assert s1.id == s2.id  # idempotent per execution
    assert s1.type == SleeveType.STRATEGY.value
    assert s1.strategy_execution_id == exec_id
    assert s1.allocated_capital == Decimal("1000")

    s3 = await svc.get_or_create_strategy_sleeve(acct, uuid4(), "RSI", Decimal("500"))
    assert s3.id != s1.id  # different execution -> different sleeve
    assert len([s for s in repo.sleeves if s.type == SleeveType.STRATEGY.value]) == 2
