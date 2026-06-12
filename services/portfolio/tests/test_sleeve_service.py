"""SleeveService tests with an in-memory fake repository — no DB, no network."""

from decimal import Decimal
from uuid import UUID, uuid4

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

    async def add_account(self, account: Account) -> None:
        if account.id is None:
            account.id = uuid4()
        self.accounts.append(account)

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
    svc = SleeveService(repo)
    a1 = await svc.get_or_create_account(TENANT, CREDS)
    a2 = await svc.get_or_create_account(TENANT, CREDS)
    assert a1.id == a2.id
    assert len(repo.accounts) == 1
    assert a1.credentials_id == CREDS


async def test_separate_credentials_get_separate_accounts() -> None:
    repo = FakeSleeveRepository()
    svc = SleeveService(repo)
    a1 = await svc.get_or_create_account(TENANT, CREDS)
    a2 = await svc.get_or_create_account(TENANT, uuid4())
    assert a1.id != a2.id
    assert len(repo.accounts) == 2


async def test_ensure_base_sleeves_creates_three_singletons() -> None:
    repo = FakeSleeveRepository()
    svc = SleeveService(repo)
    acct = await svc.get_or_create_account(TENANT, CREDS)

    first = await svc.ensure_base_sleeves(acct)
    assert set(first) == {SleeveType.UNALLOCATED, SleeveType.MANUAL, SleeveType.UNMANAGED}
    assert len(repo.sleeves) == 3

    # Idempotent: a second call returns the same rows, creates nothing new.
    again = await svc.ensure_base_sleeves(acct)
    assert again[SleeveType.UNALLOCATED].id == first[SleeveType.UNALLOCATED].id
    assert len(repo.sleeves) == 3


async def test_base_sleeves_are_active_zero_cash() -> None:
    repo = FakeSleeveRepository()
    svc = SleeveService(repo)
    acct = await svc.get_or_create_account(TENANT, CREDS)
    u = (await svc.ensure_base_sleeves(acct))[SleeveType.UNALLOCATED]
    assert u.status == SleeveStatus.ACTIVE.value
    assert u.cash_balance == Decimal("0")
    assert u.strategy_execution_id is None


async def test_unallocated_sleeve_helper() -> None:
    svc = SleeveService(FakeSleeveRepository())
    acct = await svc.get_or_create_account(TENANT, CREDS)
    u = await svc.unallocated_sleeve(acct)
    assert u.type == SleeveType.UNALLOCATED.value


async def test_strategy_sleeve_one_per_execution() -> None:
    repo = FakeSleeveRepository()
    svc = SleeveService(repo)
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
