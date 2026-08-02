"""Corporate-action detection feed: propose splits, renames and dividends.

The ledger has planners for splits, ticker renames and dividends, and an
operator-only ``ApplyCorporateAction`` RPC that applies them — but nothing has
been *detecting* the actions, so a dividend surfaces only as unattributed cash
drift. This periodic pass reads Alpaca's announcement feed for the symbols each
account actually holds, maps each announcement onto a planner, and records the
result as a PROPOSAL. It never appends to the ledger: the feed proposes, an
operator applies.

Re-polling is idempotent. A proposal's id is derived from the announcement
identity plus the account, so the same announcement always yields the same
proposal; and a proposal whose planned events already exist in the event log
(the operator applied it) is dropped rather than re-proposed.

``run_detection_pass`` and ``plan_proposal`` are the pure, unit-tested core;
``corporate_actions_loop`` is the thin scheduler.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Literal, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llamatrade_alpaca import CorporateActionType
from llamatrade_db import system_session, tenant_session
from llamatrade_db.models.ledger import Account, LedgerEvent
from llamatrade_telemetry import counter, gauge

from src.alerts import LedgerIncident, get_ledger_alert_dispatcher
from src.clients.alpaca import AlpacaCorporateAnnouncements
from src.ledger import corporate
from src.ledger.projector import LedgerProjector
from src.ports import BrokerUnavailableError
from src.tasks.equity_snapshot import projection_symbols
from src.tasks.supervisor import LeadershipProbe

if TYPE_CHECKING:
    from llamatrade_alpaca import CorporateAnnouncement

    from src.ledger.projection import AccountProjection

logger = logging.getLogger(__name__)

# Nightly: announcements land the trading day after declaration, so a faster cadence only re-reads the same feed.
DEFAULT_INTERVAL_SECONDS = 86_400.0
# Window of already-payable actions to re-read each pass; wide enough to survive a few missed nights, well inside Alpaca's 90-day cap.
DEFAULT_LOOKBACK_DAYS = 7
# Announcement reads fan out per account; the cap respects the broker rate limiter.
DEFAULT_CONCURRENCY = 4
DEFAULT_PER_ACCOUNT_TIMEOUT_SECONDS = 120.0

ONE = Decimal("1")

CorporateActionKind = Literal["split", "symbol_change", "dividend"]

# Detected actions the operator has not applied yet.
_PROPOSALS_DETECTED = counter(
    "llamatrade_ledger_corporate_action_proposals_total",
    ("kind",),
    "Corporate actions detected on held symbols and proposed for operator apply",
)
_PROPOSALS_OPEN = gauge(
    "llamatrade_ledger_corporate_action_proposals_open",
    (),
    "Corporate-action proposals from the last pass still awaiting an operator apply",
)
_UNSUPPORTED_ANNOUNCEMENTS = counter(
    "llamatrade_ledger_corporate_actions_unsupported_total",
    ("type",),
    "Announcements on held symbols that no ledger planner models (mergers, spinoffs, ...)",
)


@dataclass(frozen=True)
class CorporateActionProposal:
    """A detected corporate action awaiting an operator ``ApplyCorporateAction``.

    Carries exactly the arguments that RPC takes (kind, symbol, ratio/amount/
    new_symbol, external id) plus the events the planners would append, so the
    proposal can be checked against the log before it is surfaced again.
    """

    proposal_id: UUID
    tenant_id: UUID
    account_id: UUID
    kind: CorporateActionKind
    symbol: str
    announcement_id: str
    external_id: str = ""
    new_symbol: str = ""
    ratio: Decimal | None = None
    amount: Decimal | None = None
    planned_events: tuple[corporate.PlannedCorporateEvent, ...] = ()

    @property
    def event_ids(self) -> list[UUID]:
        """Ledger event ids this action would be applied under (idempotency keys)."""
        return [e.event_id for e in self.planned_events]


@dataclass(frozen=True)
class AccountDetectionResult:
    """Outcome of one account's detection during a pass."""

    account_id: UUID
    proposals: list[CorporateActionProposal] = field(default_factory=list)
    error: str | None = None
    skipped: bool = False  # announcements unreadable this pass


class ProjectingStore(Protocol):
    """The slice of ``LedgerProjector`` the pass needs."""

    async def project_account(self, tenant_id: UUID, account_id: UUID) -> AccountProjection: ...


class AnnouncementSource(Protocol):
    """Announced corporate actions for an account's held symbols."""

    async def announcements(
        self,
        tenant_id: UUID,
        account: Account,
        symbols: Iterable[str],
        *,
        since: date,
        until: date,
    ) -> list[CorporateAnnouncement]: ...


# (tenant, event ids) -> whether every one of them is already in the event log.
AppliedCheck = Callable[[UUID, Sequence[UUID]], Awaitable[bool]]


def proposal_id(account_id: UUID, announcement_id: str) -> UUID:
    """Deterministic proposal id from the announcement identity and account."""
    key = f"corporate-action:{account_id}:{announcement_id}"
    return UUID(bytes=hashlib.sha256(key.encode()).digest()[:16])


def detection_window(today: date, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> tuple[date, date]:
    """The ``since``/``until`` window to poll, ending today."""
    if lookback_days < 0:
        raise ValueError(f"lookback_days must be non-negative, got {lookback_days}")
    return today - timedelta(days=lookback_days), today


def _split_ratio(announcement: CorporateAnnouncement) -> Decimal | None:
    """New-shares-per-old from the announcement rates, or None if unusable."""
    old_rate, new_rate = announcement.old_rate, announcement.new_rate
    if old_rate is None or new_rate is None or old_rate <= corporate.ZERO:
        return None
    if new_rate <= corporate.ZERO:
        return None
    return new_rate / old_rate


def _holders(projection: AccountProjection, symbol: str) -> dict[UUID, Decimal]:
    """Quantity of ``symbol`` per sleeve holding it (non-zero positions only)."""
    holders: dict[UUID, Decimal] = {}
    for sleeve_id, sleeve in projection.sleeves.items():
        position = sleeve.positions.get(symbol)
        if position is not None and position.qty != corporate.ZERO:
            holders[UUID(sleeve_id)] = position.qty
    return holders


def _cost_basis_holders(
    projection: AccountProjection, symbol: str
) -> dict[UUID, tuple[Decimal, Decimal]]:
    """Quantity and cost basis of ``symbol`` per sleeve holding it."""
    holders: dict[UUID, tuple[Decimal, Decimal]] = {}
    for sleeve_id, sleeve in projection.sleeves.items():
        position = sleeve.positions.get(symbol)
        if position is not None and position.qty != corporate.ZERO:
            holders[UUID(sleeve_id)] = (position.qty, position.cost_basis)
    return holders


def plan_proposal(
    *,
    announcement: CorporateAnnouncement,
    tenant_id: UUID,
    account_id: UUID,
    projection: AccountProjection,
) -> CorporateActionProposal | None:
    """Map one announcement onto a ledger planner, or None if it does not apply.

    Returns None when the account holds nothing in the initiating symbol, when
    the announcement carries no usable rates/amount, or when the action is a
    kind the ledger has no planner for (mergers, spinoffs, stock dividends) —
    those are counted and logged so the gap is visible rather than silent.
    """
    symbol = announcement.initiating_symbol.upper()
    if not symbol:
        return None
    holders = _holders(projection, symbol)
    if not holders:
        return None

    target = announcement.target_symbol.upper()
    ratio = _split_ratio(announcement)
    external_id = announcement.corporate_action_id or announcement.id

    if announcement.ca_type is CorporateActionType.DIVIDEND:
        return _plan_dividend(
            announcement=announcement,
            tenant_id=tenant_id,
            account_id=account_id,
            symbol=symbol,
            holders=holders,
            external_id=external_id,
        )
    if (
        announcement.ca_type is CorporateActionType.SPLIT
        and ratio is not None
        and ratio != ONE
        and target in ("", symbol)
    ):
        events = corporate.plan_split(
            symbol=symbol, ratio=ratio, holders=holders, external_id=external_id
        )
        return _proposal(
            announcement=announcement,
            tenant_id=tenant_id,
            account_id=account_id,
            kind="split",
            symbol=symbol,
            external_id=external_id,
            ratio=ratio,
            events=events,
        )
    if target and target != symbol and ratio in (None, ONE):
        events = corporate.plan_symbol_change(
            old_symbol=symbol,
            new_symbol=target,
            holders=_cost_basis_holders(projection, symbol),
            external_id=external_id,
        )
        return _proposal(
            announcement=announcement,
            tenant_id=tenant_id,
            account_id=account_id,
            kind="symbol_change",
            symbol=symbol,
            external_id=external_id,
            new_symbol=target,
            events=events,
        )

    _UNSUPPORTED_ANNOUNCEMENTS.labels(type=str(announcement.ca_type)).inc()
    logger.warning(
        "no ledger planner for corporate action: account=%s symbol=%s type=%s sub_type=%s "
        "target=%s old_rate=%s new_rate=%s announcement=%s",
        account_id,
        symbol,
        announcement.ca_type,
        announcement.ca_sub_type,
        target,
        announcement.old_rate,
        announcement.new_rate,
        announcement.id,
    )
    return None


def _plan_dividend(
    *,
    announcement: CorporateAnnouncement,
    tenant_id: UUID,
    account_id: UUID,
    symbol: str,
    holders: dict[UUID, Decimal],
    external_id: str,
) -> CorporateActionProposal | None:
    """Plan a cash dividend: per-share rate x held shares, split across sleeves.

    The total is an estimate from the announced rate — the broker's actual
    payment (withholding, fractional rounding) is what the operator applies.
    Stock dividends carry no cash rate and have no planner.
    """
    rate = announcement.cash
    long_holders = {sid: qty for sid, qty in holders.items() if qty > corporate.ZERO}
    if rate is None or rate <= corporate.ZERO or not long_holders:
        _UNSUPPORTED_ANNOUNCEMENTS.labels(type=str(announcement.ca_type)).inc()
        logger.info(
            "skipping dividend announcement without a usable cash rate: "
            "account=%s symbol=%s sub_type=%s announcement=%s",
            account_id,
            symbol,
            announcement.ca_sub_type,
            announcement.id,
        )
        return None
    total = rate * sum(long_holders.values(), corporate.ZERO)
    events = corporate.split_dividend(
        symbol=symbol, total_amount=total, holders=long_holders, pay_id=external_id
    )
    return _proposal(
        announcement=announcement,
        tenant_id=tenant_id,
        account_id=account_id,
        kind="dividend",
        symbol=symbol,
        external_id=external_id,
        amount=total,
        events=events,
    )


def _proposal(
    *,
    announcement: CorporateAnnouncement,
    tenant_id: UUID,
    account_id: UUID,
    kind: CorporateActionKind,
    symbol: str,
    external_id: str,
    events: list[corporate.PlannedCorporateEvent],
    new_symbol: str = "",
    ratio: Decimal | None = None,
    amount: Decimal | None = None,
) -> CorporateActionProposal | None:
    """Wrap planned events in a proposal; None when the planners produced nothing."""
    if not events:
        return None
    return CorporateActionProposal(
        proposal_id=proposal_id(account_id, announcement.id),
        tenant_id=tenant_id,
        account_id=account_id,
        kind=kind,
        symbol=symbol,
        announcement_id=announcement.id,
        external_id=external_id,
        new_symbol=new_symbol,
        ratio=ratio,
        amount=amount,
        planned_events=tuple(events),
    )


def record_proposal(proposal: CorporateActionProposal) -> None:
    """Surface a proposal for the operator: structured warning + counter.

    There is no proposal store yet, so the log line carries every argument an
    operator needs to call ``ApplyCorporateAction``.
    """
    _PROPOSALS_DETECTED.labels(kind=proposal.kind).inc()
    logger.warning(
        "corporate action PROPOSED (apply via ApplyCorporateAction): proposal=%s tenant=%s "
        "account=%s kind=%s symbol=%s new_symbol=%s ratio=%s amount=%s external_id=%s "
        "sleeves=%d announcement=%s",
        proposal.proposal_id,
        proposal.tenant_id,
        proposal.account_id,
        proposal.kind,
        proposal.symbol,
        proposal.new_symbol,
        proposal.ratio,
        proposal.amount,
        proposal.external_id,
        len(proposal.planned_events),
        proposal.announcement_id,
    )


async def run_detection_pass(
    *,
    projector: ProjectingStore,
    source: AnnouncementSource,
    accounts: list[Account],
    since: date,
    until: date,
    already_applied: AppliedCheck | None = None,
    seen: set[UUID] | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
    per_account_timeout: float = DEFAULT_PER_ACCOUNT_TIMEOUT_SECONDS,
) -> list[AccountDetectionResult]:
    """Detect corporate actions for every account, concurrently (bounded).

    A failure or timeout on one account never aborts the pass — it is captured
    on that account's result. ``seen`` carries proposal ids across passes so a
    re-poll of the same announcement proposes once; ``already_applied`` drops
    proposals the operator has already applied to the log. Results preserve
    account order.
    """
    sem = asyncio.Semaphore(concurrency)
    reported = seen if seen is not None else set()

    async def _detect_one(account: Account) -> AccountDetectionResult:
        async with sem:
            try:
                proposals = await asyncio.wait_for(
                    _detect_account(
                        projector=projector,
                        source=source,
                        account=account,
                        since=since,
                        until=until,
                        already_applied=already_applied,
                        seen=reported,
                    ),
                    per_account_timeout,
                )
                return AccountDetectionResult(account_id=account.id, proposals=proposals)
            except BrokerUnavailableError as e:
                logger.info("skipping corporate-action detection for account %s: %s", account.id, e)
                return AccountDetectionResult(account_id=account.id, skipped=True)
            except TimeoutError:
                logger.warning("corporate-action detection timed out for account %s", account.id)
                return AccountDetectionResult(account_id=account.id, error="timeout")
            except Exception as e:  # isolate per-account failures
                logger.exception("corporate-action detection failed for account %s", account.id)
                return AccountDetectionResult(account_id=account.id, error=str(e))

    results = list(await asyncio.gather(*(_detect_one(a) for a in accounts)))
    _PROPOSALS_OPEN.set(sum(len(r.proposals) for r in results))
    return results


async def _detect_account(
    *,
    projector: ProjectingStore,
    source: AnnouncementSource,
    account: Account,
    since: date,
    until: date,
    already_applied: AppliedCheck | None,
    seen: set[UUID],
) -> list[CorporateActionProposal]:
    """Detect one account's pending corporate actions (held symbols only)."""
    projection = await projector.project_account(account.tenant_id, account.id)
    symbols = projection_symbols(projection)
    if not symbols:
        return []
    announcements = await source.announcements(
        account.tenant_id, account, symbols, since=since, until=until
    )
    proposals: list[CorporateActionProposal] = []
    for announcement in announcements:
        proposal = plan_proposal(
            announcement=announcement,
            tenant_id=account.tenant_id,
            account_id=account.id,
            projection=projection,
        )
        if proposal is None or proposal.proposal_id in seen:
            continue
        if already_applied is not None and await already_applied(
            account.tenant_id, proposal.event_ids
        ):
            seen.add(proposal.proposal_id)  # applied — never propose it again
            logger.debug(
                "corporate action already applied: account=%s symbol=%s announcement=%s",
                account.id,
                proposal.symbol,
                proposal.announcement_id,
            )
            continue
        seen.add(proposal.proposal_id)
        record_proposal(proposal)
        await get_ledger_alert_dispatcher().dispatch(
            proposal.tenant_id,
            LedgerIncident(
                kind="corporate_action_proposed",
                message=f"{proposal.kind} on {proposal.symbol} awaiting operator apply",
                context={
                    "proposal_id": str(proposal.proposal_id),
                    "account_id": str(proposal.account_id),
                    "symbol": proposal.symbol,
                    "kind": proposal.kind,
                    "amount": str(proposal.amount or ""),
                    "ratio": str(proposal.ratio or ""),
                },
            ),
        )
        proposals.append(proposal)
    return proposals


def make_applied_check(session_factory: async_sessionmaker[AsyncSession]) -> AppliedCheck:
    """An ``AppliedCheck`` that reads the tenant's event log for the planned ids."""

    async def already_applied(tenant_id: UUID, event_ids: Sequence[UUID]) -> bool:
        if not event_ids:
            return False
        async with tenant_session(tenant_id, session_factory) as db:
            rows = await db.scalars(
                select(LedgerEvent.event_id).where(LedgerEvent.event_id.in_(list(event_ids)))
            )
            found = set(rows.all())
        return all(event_id in found for event_id in event_ids)

    return already_applied


class _SessionPerCallProjector:
    """``ProjectingStore`` that opens a fresh session per call.

    The pass runs accounts concurrently, and an ``AsyncSession`` is not safe for
    concurrent use — so each account gets its own short-lived session.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def project_account(self, tenant_id: UUID, account_id: UUID) -> AccountProjection:
        async with tenant_session(tenant_id, self._sf) as db:
            return await LedgerProjector(db).project_account(tenant_id, account_id)


class _SessionPerCallAnnouncements:
    """``AnnouncementSource`` that opens a fresh session per call (see above)."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def announcements(
        self,
        tenant_id: UUID,
        account: Account,
        symbols: Iterable[str],
        *,
        since: date,
        until: date,
    ) -> list[CorporateAnnouncement]:
        async with tenant_session(tenant_id, self._sf) as db:
            return await AlpacaCorporateAnnouncements(db).announcements(
                tenant_id, account, symbols, since=since, until=until
            )


async def _load_accounts(db: AsyncSession) -> list[Account]:
    result = await db.scalars(select(Account))
    return list(result.all())


async def corporate_actions_loop(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    stop_event: asyncio.Event,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    concurrency: int = DEFAULT_CONCURRENCY,
    is_leader: LeadershipProbe | None = None,
) -> None:  # pragma: no cover - scheduler shell, logic covered via run_detection_pass
    """Run detection passes until ``stop_event`` is set.

    Proposals are recorded, never applied — an operator applies them through
    ``ApplyCorporateAction``. ``seen`` lives for the life of the loop so a
    proposal is surfaced once per process, and the event-log check keeps applied
    actions from coming back after a restart. The loop returns as soon as
    ``is_leader`` says this pod no longer holds the writer lock.
    """
    projector = _SessionPerCallProjector(session_factory)
    source = _SessionPerCallAnnouncements(session_factory)
    already_applied = make_applied_check(session_factory)
    seen: set[UUID] = set()
    logger.info("ledger corporate-action detection loop started (interval=%ss)", interval_seconds)
    while not stop_event.is_set():
        if is_leader is not None and not await is_leader():
            break
        try:
            async with system_session(
                session_factory, reason="corporate-action detection sweep"
            ) as db:
                accounts = await _load_accounts(db)
            if accounts:
                since, until = detection_window(datetime.now(UTC).date(), lookback_days)
                results = await run_detection_pass(
                    projector=projector,
                    source=source,
                    accounts=accounts,
                    since=since,
                    until=until,
                    already_applied=already_applied,
                    seen=seen,
                    concurrency=concurrency,
                )
                proposed = sum(len(r.proposals) for r in results)
                if proposed:
                    logger.info("corporate-action pass proposed %d action(s)", proposed)
        except Exception:  # never let a bad pass kill the loop
            logger.exception("corporate-action detection pass errored")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass
    logger.info("ledger corporate-action detection loop stopped")
