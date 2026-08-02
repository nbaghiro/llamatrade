"""Intent capture from both live loops, and the diff tool that scores them.

The first test drives the hand-rolled loop and the runtime loop over the same recorded minute
bars, in-process, with capture enabled on both, then asserts the diff tool reports zero divergence
over the whole run: the local stand-in for the paper soak the flag flip is gated on. The rest pin
the evaluation-timestamp invariant both loops depend on, the book context each record carries, and
the diff tool's own behaviour, since its exit code is the soak criterion.
"""

import json
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest

from llamatrade_alpaca import MockBarStream, MockTradeStream
from llamatrade_alpaca import StreamBar as BarData
from llamatrade_runtime import StrategySession

from src.runner.intent_capture import CAPTURE_DIR_ENV, LOOP_HAND_ROLLED, LOOP_RUNTIME
from src.runner.runner import RunnerConfig, RunnerPosition, StrategyRunner
from src.tools import parity_diff

ET = ZoneInfo("America/New_York")

SWITCH = (
    '(strategy "RSI Switch" :rebalance daily '
    "(if (> (rsi SPY 14) 70) (asset TLT :weight 100) (else (asset SPY :weight 100))))"
)

SESSION_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OTHER_SESSION_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _bar(symbol: str, ts: datetime, close: float) -> BarData:
    return BarData(
        symbol=symbol,
        timestamp=ts,
        open=close,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        volume=100,
    )


def _recorded_bars() -> list[BarData]:
    """Interleaved minute bars over enough sessions for RSI to warm and the switch to fire."""
    bars: list[BarData] = []
    for day in range(30):
        session_open = datetime(2025, 6, 2, 9, 30, tzinfo=ET) + timedelta(days=day)
        for minute in range(3):
            ts = session_open + timedelta(minutes=minute)
            bars.append(_bar("SPY", ts, 100.0 + day + 0.5 * minute))
            bars.append(_bar("TLT", ts, 50.0 + 0.01 * day))
    return bars


class _FiniteStream:
    def __init__(self, bars: Sequence[BarData]) -> None:
        self._bars = list(bars)

    async def stream(self) -> AsyncIterator[BarData]:
        for bar in self._bars:
            yield bar


def _runner(session: StrategySession, execution_id: UUID) -> StrategyRunner:
    config = RunnerConfig(
        tenant_id=uuid4(),
        execution_id=execution_id,
        strategy_id=uuid4(),
        symbols=["SPY", "TLT"],
        timeframe="1Min",
        warmup_bars=5,
        enforce_trading_hours=False,
    )
    order_executor = AsyncMock()
    order_executor.submit_order.return_value = MagicMock(
        id=uuid4(), status="submitted", client_order_id="lt-test"
    )
    risk_manager = AsyncMock()
    risk_manager.check_order.return_value = MagicMock(passed=True, violations=[])
    return StrategyRunner(
        config=config,
        strategy_fn=None,
        bar_stream=MockBarStream(bars={"SPY": [], "TLT": []}),
        trade_stream=MockTradeStream(),
        order_executor=order_executor,
        risk_manager=risk_manager,
        session=session,
    )


def _seed_book(runner: StrategyRunner) -> None:
    """Give the runner a non-trivial book, as a funded sleeve session would have."""
    runner.set_equity(Decimal("50000"))
    runner.sync_position(
        "SPY",
        RunnerPosition(
            symbol="SPY",
            side="long",
            quantity=Decimal("4"),
            entry_price=Decimal("100"),
            entry_date=datetime(2025, 6, 2, tzinfo=UTC),
        ),
    )


async def _capture_hand_rolled(
    execution_id: UUID,
    bars: Sequence[BarData],
    *,
    prepare: Callable[[StrategyRunner], None] | None = None,
) -> Path:
    runner = _runner(StrategySession(SWITCH), execution_id)
    if prepare is not None:
        prepare(runner)
    for bar in bars:
        await runner._process_bar(bar)
    assert runner._intent_capture is not None
    return runner._intent_capture.path


async def _capture_runtime(
    execution_id: UUID,
    bars: Sequence[BarData],
    monkeypatch: pytest.MonkeyPatch,
    *,
    prepare: Callable[[StrategyRunner], None] | None = None,
) -> Path:
    monkeypatch.setenv("TRADING_USE_RUNTIME_LOOP", "true")
    runner = _runner(StrategySession(SWITCH), execution_id)
    if prepare is not None:
        prepare(runner)
    runner.bar_stream = _FiniteStream(bars)
    runner._running = True
    await runner._run_via_runtime()
    assert runner._intent_capture is not None
    return runner._intent_capture.path


# --- both loops over the same recorded bars --------------------------------------------------


async def test_both_loops_capture_identical_intents_over_the_same_bars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CAPTURE_DIR_ENV, str(tmp_path))
    bars = _recorded_bars()

    hand_rolled = await _capture_hand_rolled(SESSION_ID, bars)
    runtime = await _capture_runtime(SESSION_ID, bars, monkeypatch)

    left = parity_diff.load_capture(hand_rolled)
    right = parity_diff.load_capture(runtime)
    assert left.loops == (LOOP_HAND_ROLLED,)
    assert right.loops == (LOOP_RUNTIME,)

    report = parity_diff.compare(left, right)
    assert report.alignment == parity_diff.ALIGN_SESSION
    assert report.order_ids_compared
    assert report.divergences == ()
    assert report.compared == report.identical > 0
    # The run must actually trade, or parity would be vacuous.
    assert sum(len(evaluation.intents) for evaluation in left.evaluations) > 1
    assert parity_diff.run([str(hand_rolled), str(runtime)]) == 0


async def test_capture_records_every_evaluation_including_the_empty_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CAPTURE_DIR_ENV, str(tmp_path))
    bars = _recorded_bars()

    path = await _capture_hand_rolled(SESSION_ID, bars)
    capture = parity_diff.load_capture(path)

    # One record per evaluated period-complete snapshot, not one per order.
    assert len(capture.evaluations) == len(bars) // 2
    assert any(not evaluation.intents for evaluation in capture.evaluations)
    assert [e.sequence for e in capture.evaluations] == list(range(1, len(capture.evaluations) + 1))


async def test_both_loops_stamp_an_evaluation_with_the_completing_bar_timestamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both loops stamp an evaluation with the source timestamp of the bar that completed it.

    The hand-rolled loop takes it from ``bar.timestamp``; the runtime loop takes it from the tick
    its feed yields, which is the completing bar's source timestamp. The deterministic client
    order id hashes that instant, so any drift between the loops would make the same evaluation
    submit under a different order id and break idempotent replay across a flag flip.
    """
    monkeypatch.setenv(CAPTURE_DIR_ENV, str(tmp_path))
    bars = _recorded_bars()

    hand_rolled = parity_diff.load_capture(await _capture_hand_rolled(SESSION_ID, bars))
    runtime = parity_diff.load_capture(await _capture_runtime(SESSION_ID, bars, monkeypatch))

    assert [e.timestamp for e in hand_rolled.evaluations] == [
        e.timestamp for e in runtime.evaluations
    ]
    hand_rolled_ids = [i.order_id for e in hand_rolled.evaluations for i in e.intents]
    runtime_ids = [i.order_id for e in runtime.evaluations for i in e.intents]
    assert len(hand_rolled_ids) > 1
    assert hand_rolled_ids == runtime_ids


async def test_both_loops_capture_the_book_the_evaluation_sized_against(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CAPTURE_DIR_ENV, str(tmp_path))
    bars = _recorded_bars()

    hand_rolled = parity_diff.load_capture(
        await _capture_hand_rolled(SESSION_ID, bars, prepare=_seed_book)
    )
    runtime = parity_diff.load_capture(
        await _capture_runtime(SESSION_ID, bars, monkeypatch, prepare=_seed_book)
    )

    expected = parity_diff.Book(equity=50000.0, holdings=(("SPY", 4.0),))
    assert {e.book for e in hand_rolled.evaluations} == {expected}
    assert {e.book for e in runtime.evaluations} == {expected}


async def test_no_capture_is_written_when_the_directory_is_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(CAPTURE_DIR_ENV, raising=False)
    runner = _runner(StrategySession(SWITCH), SESSION_ID)

    for bar in _recorded_bars()[:20]:
        await runner._process_bar(bar)

    assert runner._intent_capture is None
    assert list(tmp_path.iterdir()) == []


# --- diff tool -------------------------------------------------------------------------------


def _record(
    ts: datetime,
    intents: Sequence[tuple[str, str, float, float]],
    *,
    session: UUID = SESSION_ID,
    loop: str = LOOP_HAND_ROLLED,
    sequence: int = 1,
    equity: float = 100000.0,
    holdings: Mapping[str, float] | None = None,
) -> dict[str, object]:
    return {
        "session": str(session),
        "loop": loop,
        "sequence": sequence,
        "timestamp": ts.isoformat(),
        "book": {"equity": equity, "holdings": dict(holdings or {})},
        "intents": [
            {
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "order_id": f"lt-{session.hex[:8]}{symbol.lower()}",
            }
            for symbol, side, quantity, price in intents
        ],
    }


TS = [datetime(2026, 7, 29, 20, minute, tzinfo=UTC) for minute in range(3)]


def _pair(tmp_path: Path, left: Sequence[object], right: Sequence[object]) -> tuple[Path, Path]:
    a = tmp_path / "left.jsonl"
    b = tmp_path / "right.jsonl"
    a.write_text("".join(f"{json.dumps(r)}\n" for r in left), encoding="utf-8")
    b.write_text("".join(f"{json.dumps(r)}\n" for r in right), encoding="utf-8")
    return a, b


def test_diff_reports_a_mismatched_quantity(tmp_path: Path) -> None:
    left, right = _pair(
        tmp_path,
        [_record(TS[0], [("SPY", "buy", 10.0, 100.0)])],
        [_record(TS[0], [("SPY", "buy", 9.5, 100.0)], loop=LOOP_RUNTIME)],
    )

    report = parity_diff.compare(parity_diff.load_capture(left), parity_diff.load_capture(right))

    assert report.compared == 1 and report.identical == 0
    assert len(report.divergences) == 1
    divergence = report.divergences[0]
    assert divergence.kind == parity_diff.KIND_INTENTS
    assert divergence.details == ("intent 0 quantity: 10.0 != 9.5",)
    assert parity_diff.run([str(left), str(right)]) == 1


def test_a_book_difference_alone_is_not_a_divergence(tmp_path: Path) -> None:
    """Two pods legitimately hold different books; only the intents they produce must match."""
    left, right = _pair(
        tmp_path,
        [_record(TS[0], [("SPY", "buy", 10.0, 100.0)], equity=100000.0, holdings={"SPY": 1.0})],
        [
            _record(
                TS[0],
                [("SPY", "buy", 10.0, 100.0)],
                loop=LOOP_RUNTIME,
                equity=25000.0,
                holdings={"TLT": 3.0},
            )
        ],
    )

    report = parity_diff.compare(parity_diff.load_capture(left), parity_diff.load_capture(right))

    assert report.divergences == ()
    assert report.compared == report.identical == 1


def test_a_divergence_reports_the_book_each_side_sized_against(tmp_path: Path) -> None:
    left, right = _pair(
        tmp_path,
        [_record(TS[0], [("SPY", "buy", 10.0, 100.0)], equity=100000.0, holdings={"SPY": 1.0})],
        [_record(TS[0], [("SPY", "buy", 9.0, 100.0)], loop=LOOP_RUNTIME, equity=25000.0)],
    )
    report = parity_diff.compare(parity_diff.load_capture(left), parity_diff.load_capture(right))

    text = parity_diff.render_text(report, 10)

    assert "left book equity=100000.0 holdings=SPY:1.0" in text
    assert "right book equity=25000.0 holdings=flat" in text


def test_an_evaluation_missing_on_one_side_reports_only_the_book_it_has(tmp_path: Path) -> None:
    left, right = _pair(
        tmp_path,
        [
            _record(TS[0], [("SPY", "buy", 10.0, 100.0)], sequence=1),
            _record(TS[1], [], sequence=2, equity=42.0),
        ],
        [_record(TS[0], [("SPY", "buy", 10.0, 100.0)], loop=LOOP_RUNTIME, sequence=1)],
    )

    report = parity_diff.compare(parity_diff.load_capture(left), parity_diff.load_capture(right))

    divergence = report.divergences[0]
    assert divergence.left_book == parity_diff.Book(equity=42.0, holdings=())
    assert divergence.right_book is None
    assert "right book" not in parity_diff.render_text(report, 10)


def test_a_record_without_a_book_is_rejected(tmp_path: Path) -> None:
    record = _record(TS[0], [("SPY", "buy", 10.0, 100.0)])
    del record["book"]
    path = tmp_path / "bookless.jsonl"
    path.write_text(f"{json.dumps(record)}\n", encoding="utf-8")

    with pytest.raises(parity_diff.CaptureError, match=r"bookless.jsonl:1: field 'book'"):
        parity_diff.load_capture(path)


def test_diff_reports_an_evaluation_missing_on_one_side(tmp_path: Path) -> None:
    left, right = _pair(
        tmp_path,
        [
            _record(TS[0], [("SPY", "buy", 10.0, 100.0)], sequence=1),
            _record(TS[1], [], sequence=2),
        ],
        [_record(TS[0], [("SPY", "buy", 10.0, 100.0)], loop=LOOP_RUNTIME, sequence=1)],
    )

    report = parity_diff.compare(parity_diff.load_capture(left), parity_diff.load_capture(right))

    assert report.compared == 1 and report.identical == 1
    assert [d.kind for d in report.divergences] == [parity_diff.KIND_ABSENT_RIGHT]
    assert report.count(parity_diff.KIND_ABSENT_RIGHT) == 1
    assert parity_diff.run([str(left), str(right)]) == 1


def test_diff_is_insensitive_to_record_order_within_a_file(tmp_path: Path) -> None:
    ordered = [
        _record(TS[0], [("SPY", "buy", 10.0, 100.0)], sequence=1),
        _record(TS[1], [("TLT", "sell", 2.0, 50.0)], sequence=2),
        _record(TS[2], [], sequence=3),
    ]
    shuffled = [ordered[2], ordered[0], ordered[1]]
    left, right = _pair(tmp_path, ordered, [{**r, "loop": LOOP_RUNTIME} for r in shuffled])

    report = parity_diff.compare(parity_diff.load_capture(left), parity_diff.load_capture(right))

    assert report.compared == 3 and report.identical == 3
    assert report.divergences == ()
    assert parity_diff.run([str(left), str(right)]) == 0


def test_diff_reports_a_reordered_intent_within_one_evaluation(tmp_path: Path) -> None:
    """The intent list is ordered: the same orders in a different order is a divergence."""
    intents = [("SPY", "buy", 10.0, 100.0), ("TLT", "sell", 2.0, 50.0)]
    left, right = _pair(
        tmp_path,
        [_record(TS[0], intents)],
        [_record(TS[0], list(reversed(intents)), loop=LOOP_RUNTIME)],
    )

    report = parity_diff.compare(parity_diff.load_capture(left), parity_diff.load_capture(right))

    assert len(report.divergences) == 1
    assert report.divergences[0].details[0].startswith("intent 0 symbol: SPY != TLT")


def test_tolerance_admits_a_small_difference_only_when_asked(tmp_path: Path) -> None:
    left, right = _pair(
        tmp_path,
        [_record(TS[0], [("SPY", "buy", 10.0, 100.0)])],
        [_record(TS[0], [("SPY", "buy", 10.000001, 100.0)], loop=LOOP_RUNTIME)],
    )
    captures = (parity_diff.load_capture(left), parity_diff.load_capture(right))

    assert parity_diff.compare(*captures).divergences  # exact by default
    assert parity_diff.compare(*captures, tolerance=1e-5).divergences == ()
    assert parity_diff.run([str(left), str(right), "--tolerance", "0.00001"]) == 0


def test_diff_across_two_sessions_aligns_on_timestamps_and_skips_order_ids(
    tmp_path: Path,
) -> None:
    """Two pods run two sessions: intents must match, deterministic ids cannot."""
    left, right = _pair(
        tmp_path,
        [_record(TS[0], [("SPY", "buy", 10.0, 100.0)])],
        [
            _record(
                TS[0],
                [("SPY", "buy", 10.0, 100.0)],
                session=OTHER_SESSION_ID,
                loop=LOOP_RUNTIME,
            )
        ],
    )

    report = parity_diff.compare(parity_diff.load_capture(left), parity_diff.load_capture(right))

    assert report.alignment == parity_diff.ALIGN_TIMESTAMP
    assert not report.order_ids_compared
    assert report.divergences == ()
    assert "skipped (sessions differ)" in parity_diff.render_text(report, 10)


def test_conflicting_records_for_one_evaluation_are_a_divergence(tmp_path: Path) -> None:
    left, right = _pair(
        tmp_path,
        [
            _record(TS[0], [("SPY", "buy", 10.0, 100.0)], sequence=1),
            _record(TS[0], [("SPY", "buy", 11.0, 100.0)], sequence=2),
        ],
        [_record(TS[0], [("SPY", "buy", 10.0, 100.0)], loop=LOOP_RUNTIME)],
    )

    report = parity_diff.compare(parity_diff.load_capture(left), parity_diff.load_capture(right))

    assert [d.kind for d in report.divergences] == [parity_diff.KIND_DUPLICATE_LEFT]
    assert parity_diff.run([str(left), str(right)]) == 1


def test_identical_duplicates_are_collapsed(tmp_path: Path) -> None:
    record = _record(TS[0], [("SPY", "buy", 10.0, 100.0)])
    left, right = _pair(tmp_path, [record, record], [{**record, "loop": LOOP_RUNTIME}])

    report = parity_diff.compare(parity_diff.load_capture(left), parity_diff.load_capture(right))

    assert report.divergences == ()
    assert report.compared == 1


def test_an_empty_capture_is_an_error_not_a_pass(tmp_path: Path) -> None:
    left, right = _pair(tmp_path, [_record(TS[0], [])], [])

    assert parity_diff.run([str(left), str(right)]) == 2
    with pytest.raises(parity_diff.CaptureError, match="no evaluations"):
        parity_diff.load_capture(right)


def test_a_malformed_record_is_rejected_with_its_line(tmp_path: Path) -> None:
    path = tmp_path / "broken.jsonl"
    path.write_text('{"session": "x"}\n', encoding="utf-8")

    with pytest.raises(parity_diff.CaptureError, match=r"broken.jsonl:1: field 'intents'"):
        parity_diff.load_capture(path)


def test_multi_session_files_that_do_not_match_need_an_explicit_alignment(
    tmp_path: Path,
) -> None:
    left, right = _pair(
        tmp_path,
        [
            _record(TS[0], [], sequence=1),
            _record(TS[1], [], session=OTHER_SESSION_ID, sequence=2),
        ],
        [_record(TS[0], [], loop=LOOP_RUNTIME)],
    )
    captures = (parity_diff.load_capture(left), parity_diff.load_capture(right))

    with pytest.raises(parity_diff.CaptureError, match="different sets of sessions"):
        parity_diff.compare(*captures)
    assert parity_diff.compare(*captures, alignment=parity_diff.ALIGN_TIMESTAMP).compared == 1
    assert parity_diff.run([str(left), str(right)]) == 2


def test_json_output_carries_the_counts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    left, right = _pair(
        tmp_path,
        [_record(TS[0], [("SPY", "buy", 10.0, 100.0)])],
        [_record(TS[0], [("SPY", "buy", 9.0, 100.0)], loop=LOOP_RUNTIME)],
    )

    assert parity_diff.run([str(left), str(right), "--json"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["compared"] == 1
    assert payload["divergent"] == 1
    assert payload["divergences"][0]["details"] == ["intent 0 quantity: 10.0 != 9.0"]
    assert payload["divergences"][0]["left_book"] == {"equity": 100000.0, "holdings": {}}
    assert payload["divergences"][0]["right_book"] == {"equity": 100000.0, "holdings": {}}


def test_a_negative_tolerance_is_rejected(tmp_path: Path) -> None:
    left, right = _pair(tmp_path, [_record(TS[0], [])], [_record(TS[0], [], loop=LOOP_RUNTIME)])

    assert parity_diff.run([str(left), str(right), "--tolerance", "-1"]) == 2
