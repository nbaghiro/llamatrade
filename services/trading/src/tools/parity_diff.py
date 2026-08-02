"""Operator tool: diff two live-loop intent captures and report order-for-order parity.

Each capture file is the JSON-lines log written by ``TRADING_INTENT_CAPTURE_DIR`` (see
``src/runner/intent_capture.py``): one record per evaluation, holding the session, the evaluation
timestamp, the loop that produced it and the ordered intents that evaluation sized. This tool
aligns two captures evaluation by evaluation and reports whether they asked for exactly the same
orders, which is the criterion for flipping ``TRADING_USE_RUNTIME_LOOP``.

Alignment is by ``(session, evaluation timestamp)`` when both captures cover the same sessions
(sequential runs of one session), and by evaluation timestamp alone when each capture covers a
single, different session (two pods, one per flag value). Records are indexed, not zipped, so file
order does not matter. Deterministic order ids are derived from the session id, so they are
compared only when the two sides share a session.

Quantities and prices compare exactly by default: both loops drive the same aggregator, session
and sizer, so any difference at all is a real divergence. ``--tolerance`` exists to characterise a
divergence during investigation, not to pass a soak.

Each record also carries the book (equity and held quantities) its evaluation sized against. Two
pods legitimately hold different books, so the book is never compared — it is printed alongside
every divergence so an operator can tell a sizing-input difference from a loop difference.

Exit codes: 0 no divergence, 1 divergences reported, 2 unusable input.

    python -m src.tools.parity_diff captures/hand_rolled.jsonl captures/runtime.jsonl
    python -m src.tools.parity_diff left.jsonl right.jsonl --limit 50 --json
"""

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

ALIGN_SESSION = "session"
ALIGN_TIMESTAMP = "timestamp"
ALIGN_AUTO = "auto"

KIND_INTENTS = "intents"
KIND_ABSENT_LEFT = "absent_left"
KIND_ABSENT_RIGHT = "absent_right"
KIND_DUPLICATE_LEFT = "duplicate_left"
KIND_DUPLICATE_RIGHT = "duplicate_right"

DEFAULT_LIMIT = 10


class CaptureError(Exception):
    """A capture file could not be read, parsed, or aligned with its counterpart."""


@dataclass(frozen=True, slots=True)
class Intent:
    """One captured order intent."""

    symbol: str
    side: str
    quantity: float
    price: float
    order_id: str


@dataclass(frozen=True, slots=True)
class Book:
    """The book one evaluation sized against — reported on divergence, never compared."""

    equity: float
    holdings: tuple[tuple[str, float], ...]

    def describe(self) -> str:
        held = " ".join(f"{symbol}:{quantity!r}" for symbol, quantity in self.holdings)
        return f"equity={self.equity!r} holdings={held or 'flat'}"


@dataclass(frozen=True, slots=True)
class Evaluation:
    """One evaluation's captured intent set and the book it sized against."""

    session: str
    loop: str
    sequence: int
    timestamp: datetime
    book: Book
    intents: tuple[Intent, ...]


@dataclass(frozen=True, slots=True)
class Capture:
    """A parsed capture file."""

    path: Path
    evaluations: tuple[Evaluation, ...]

    @property
    def sessions(self) -> tuple[str, ...]:
        return tuple(sorted({e.session for e in self.evaluations}))

    @property
    def loops(self) -> tuple[str, ...]:
        return tuple(sorted({e.loop for e in self.evaluations}))


@dataclass(frozen=True, slots=True)
class Divergence:
    """One evaluation the two captures do not agree on, with each side's book."""

    timestamp: datetime
    session: str
    kind: str
    details: tuple[str, ...]
    left_book: Book | None = None
    right_book: Book | None = None


@dataclass(frozen=True, slots=True)
class DiffReport:
    """The outcome of comparing two captures."""

    left: Capture
    right: Capture
    alignment: str
    tolerance: float
    order_ids_compared: bool
    compared: int
    identical: int
    divergences: tuple[Divergence, ...]

    def count(self, kind: str) -> int:
        return sum(1 for d in self.divergences if d.kind == kind)


# --- loading ---------------------------------------------------------------------------------


def load_capture(path: Path) -> Capture:
    """Parse a JSON-lines capture file, rejecting anything malformed."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CaptureError(f"cannot read {path}: {exc}") from exc

    evaluations: list[Evaluation] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        evaluations.append(_parse_line(line, f"{path}:{number}"))
    if not evaluations:
        raise CaptureError(f"{path} holds no evaluations")
    return Capture(path, tuple(evaluations))


def _parse_line(line: str, where: str) -> Evaluation:
    record = _require_object(line, where)
    intents: list[Intent] = []
    for index, raw in enumerate(_require_list(record, "intents", where)):
        if not isinstance(raw, dict):
            raise CaptureError(f"{where}: intent {index} is not an object")
        intent = cast("Mapping[str, object]", raw)
        intents.append(
            Intent(
                symbol=_require_str(intent, "symbol", where),
                side=_require_str(intent, "side", where),
                quantity=_require_number(intent, "quantity", where),
                price=_require_number(intent, "price", where),
                order_id=_require_str(intent, "order_id", where),
            )
        )
    return Evaluation(
        session=_require_str(record, "session", where),
        loop=_require_str(record, "loop", where),
        sequence=_require_int(record, "sequence", where),
        timestamp=_require_timestamp(record, "timestamp", where),
        book=_require_book(record, "book", where),
        intents=tuple(intents),
    )


def _require_book(record: Mapping[str, object], field: str, where: str) -> Book:
    value = record.get(field)
    if not isinstance(value, dict):
        raise CaptureError(f"{where}: field '{field}' must be an object")
    book = cast("Mapping[str, object]", value)
    holdings = book.get("holdings")
    if not isinstance(holdings, dict):
        raise CaptureError(f"{where}: field '{field}.holdings' must be an object")
    held: list[tuple[str, float]] = []
    for symbol, quantity in cast("Mapping[str, object]", holdings).items():
        if isinstance(quantity, bool) or not isinstance(quantity, int | float):
            raise CaptureError(f"{where}: holding {symbol!r} must be a number")
        held.append((symbol, float(quantity)))
    return Book(equity=_require_number(book, "equity", where), holdings=tuple(sorted(held)))


def _require_object(line: str, where: str) -> Mapping[str, object]:
    try:
        raw: object = json.loads(line)
    except json.JSONDecodeError as exc:
        raise CaptureError(f"{where}: invalid JSON ({exc.msg})") from exc
    if not isinstance(raw, dict):
        raise CaptureError(f"{where}: expected a JSON object")
    return cast("Mapping[str, object]", raw)


def _require_str(record: Mapping[str, object], field: str, where: str) -> str:
    value = record.get(field)
    if not isinstance(value, str):
        raise CaptureError(f"{where}: field '{field}' must be a string")
    return value


def _require_int(record: Mapping[str, object], field: str, where: str) -> int:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CaptureError(f"{where}: field '{field}' must be an integer")
    return value


def _require_number(record: Mapping[str, object], field: str, where: str) -> float:
    value = record.get(field)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CaptureError(f"{where}: field '{field}' must be a number")
    return float(value)


def _require_list(record: Mapping[str, object], field: str, where: str) -> list[object]:
    value = record.get(field)
    if not isinstance(value, list):
        raise CaptureError(f"{where}: field '{field}' must be a list")
    return cast("list[object]", value)


def _require_timestamp(record: Mapping[str, object], field: str, where: str) -> datetime:
    raw = _require_str(record, field, where)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise CaptureError(f"{where}: field '{field}' is not an ISO timestamp") from exc
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


# --- comparison ------------------------------------------------------------------------------


def compare(
    left: Capture,
    right: Capture,
    *,
    tolerance: float = 0.0,
    alignment: str = ALIGN_AUTO,
) -> DiffReport:
    """Align two captures and report every evaluation they do not agree on."""
    resolved = _resolve_alignment(left, right, alignment)
    order_ids_compared = left.sessions == right.sessions

    divergences: list[Divergence] = []
    left_index = _index(left, resolved, KIND_DUPLICATE_LEFT, divergences)
    right_index = _index(right, resolved, KIND_DUPLICATE_RIGHT, divergences)

    compared = 0
    identical = 0
    for key in sorted(left_index.keys() | right_index.keys()):
        session, timestamp = key
        if key not in right_index:
            divergences.append(_absent(key, KIND_ABSENT_RIGHT, left_index[key]))
            continue
        if key not in left_index:
            divergences.append(_absent(key, KIND_ABSENT_LEFT, right_index[key]))
            continue

        left_eval = left_index[key]
        right_eval = right_index[key]
        compared += 1
        details = _compare_intents(
            left_eval, right_eval, tolerance=tolerance, compare_order_ids=order_ids_compared
        )
        if details:
            divergences.append(
                Divergence(
                    timestamp=timestamp,
                    session=session or left_eval.session,
                    kind=KIND_INTENTS,
                    details=details,
                    left_book=left_eval.book,
                    right_book=right_eval.book,
                )
            )
        else:
            identical += 1

    return DiffReport(
        left=left,
        right=right,
        alignment=resolved,
        tolerance=tolerance,
        order_ids_compared=order_ids_compared,
        compared=compared,
        identical=identical,
        divergences=tuple(sorted(divergences, key=lambda d: (d.timestamp, d.session, d.kind))),
    )


def _absent(key: tuple[str, datetime], kind: str, evaluation: Evaluation) -> Divergence:
    """An evaluation only one capture holds."""
    present_left = kind == KIND_ABSENT_RIGHT
    side = "left" if present_left else "right"
    session, timestamp = key
    return Divergence(
        timestamp=timestamp,
        session=session or evaluation.session,
        kind=kind,
        details=(f"{len(evaluation.intents)} intent(s) captured in {side} only",),
        left_book=evaluation.book if present_left else None,
        right_book=None if present_left else evaluation.book,
    )


def _resolve_alignment(left: Capture, right: Capture, requested: str) -> str:
    if requested != ALIGN_AUTO:
        return requested
    if left.sessions == right.sessions:
        return ALIGN_SESSION
    if len(left.sessions) == 1 and len(right.sessions) == 1:
        return ALIGN_TIMESTAMP
    raise CaptureError(
        "captures cover different sets of sessions; rerun with "
        f"--align {ALIGN_TIMESTAMP} or split the files by session"
    )


def _index(
    capture: Capture,
    alignment: str,
    duplicate_kind: str,
    divergences: list[Divergence],
) -> dict[tuple[str, datetime], Evaluation]:
    """Key a capture's evaluations, reporting conflicting records for one key as a divergence."""
    indexed: dict[tuple[str, datetime], Evaluation] = {}
    for evaluation in capture.evaluations:
        session = evaluation.session if alignment == ALIGN_SESSION else ""
        key = (session, evaluation.timestamp)
        existing = indexed.get(key)
        if existing is None:
            indexed[key] = evaluation
        elif existing.intents != evaluation.intents:
            left_side = duplicate_kind == KIND_DUPLICATE_LEFT
            divergences.append(
                Divergence(
                    timestamp=evaluation.timestamp,
                    session=evaluation.session,
                    kind=duplicate_kind,
                    details=(
                        f"conflicting records for one evaluation "
                        f"(sequence {existing.sequence} and {evaluation.sequence})",
                    ),
                    left_book=evaluation.book if left_side else None,
                    right_book=None if left_side else evaluation.book,
                )
            )
    return indexed


def _compare_intents(
    left: Evaluation,
    right: Evaluation,
    *,
    tolerance: float,
    compare_order_ids: bool,
) -> tuple[str, ...]:
    details: list[str] = []
    if len(left.intents) != len(right.intents):
        details.append(f"intent count: {len(left.intents)} != {len(right.intents)}")
    for index, (a, b) in enumerate(zip(left.intents, right.intents, strict=False)):
        if a.symbol != b.symbol:
            details.append(f"intent {index} symbol: {a.symbol} != {b.symbol}")
        if a.side != b.side:
            details.append(f"intent {index} side: {a.side} != {b.side}")
        if not _within(a.quantity, b.quantity, tolerance):
            details.append(f"intent {index} quantity: {a.quantity!r} != {b.quantity!r}")
        if not _within(a.price, b.price, tolerance):
            details.append(f"intent {index} price: {a.price!r} != {b.price!r}")
        if compare_order_ids and a.order_id != b.order_id:
            details.append(f"intent {index} order_id: {a.order_id} != {b.order_id}")
    for index, extra in enumerate(left.intents[len(right.intents) :], start=len(right.intents)):
        details.append(f"intent {index} left only: {_describe(extra)}")
    for index, extra in enumerate(right.intents[len(left.intents) :], start=len(left.intents)):
        details.append(f"intent {index} right only: {_describe(extra)}")
    return tuple(details)


def _within(left: float, right: float, tolerance: float) -> bool:
    return left == right if tolerance == 0.0 else abs(left - right) <= tolerance


def _describe(intent: Intent) -> str:
    return f"{intent.side} {intent.quantity!r} {intent.symbol} @ {intent.price!r}"


# --- rendering -------------------------------------------------------------------------------


def render_text(report: DiffReport, limit: int) -> str:
    lines = [
        "runtime-loop intent parity",
        f"  left       {report.left.path}",
        f"             {_capture_summary(report.left)}",
        f"  right      {report.right.path}",
        f"             {_capture_summary(report.right)}",
        f"  alignment  {report.alignment}",
        f"  quantities {'exact' if report.tolerance == 0.0 else f'tolerance {report.tolerance}'}",
        f"  order ids  {'compared' if report.order_ids_compared else 'skipped (sessions differ)'}",
        "",
        f"  compared   {report.compared}",
        f"  identical  {report.identical}",
        f"  divergent  {len(report.divergences)}",
        f"  left only  {report.count(KIND_ABSENT_RIGHT)}",
        f"  right only {report.count(KIND_ABSENT_LEFT)}",
        "",
    ]
    if not report.divergences:
        lines.append("no divergence")
        return "\n".join(lines) + "\n"

    shown = report.divergences[:limit] if limit > 0 else report.divergences
    lines.append(f"divergences (showing {len(shown)} of {len(report.divergences)})")
    for divergence in shown:
        lines.append(
            f"  {divergence.timestamp.isoformat()} session={divergence.session} [{divergence.kind}]"
        )
        lines.extend(f"      {detail}" for detail in divergence.details)
        lines.extend(
            f"      {side} book {book.describe()}"
            for side, book in (("left", divergence.left_book), ("right", divergence.right_book))
            if book is not None
        )
    return "\n".join(lines) + "\n"


def render_json(report: DiffReport, limit: int) -> str:
    shown = report.divergences[:limit] if limit > 0 else report.divergences
    payload = {
        "left": _capture_json(report.left),
        "right": _capture_json(report.right),
        "alignment": report.alignment,
        "tolerance": report.tolerance,
        "order_ids_compared": report.order_ids_compared,
        "compared": report.compared,
        "identical": report.identical,
        "divergent": len(report.divergences),
        "left_only": report.count(KIND_ABSENT_RIGHT),
        "right_only": report.count(KIND_ABSENT_LEFT),
        "divergences": [
            {
                "timestamp": d.timestamp.isoformat(),
                "session": d.session,
                "kind": d.kind,
                "details": list(d.details),
                "left_book": _book_json(d.left_book),
                "right_book": _book_json(d.right_book),
            }
            for d in shown
        ],
    }
    return json.dumps(payload, indent=2) + "\n"


def _book_json(book: Book | None) -> dict[str, object] | None:
    if book is None:
        return None
    return {"equity": book.equity, "holdings": dict(book.holdings)}


def _capture_summary(capture: Capture) -> str:
    return (
        f"loop={','.join(capture.loops)} evaluations={len(capture.evaluations)} "
        f"sessions={len(capture.sessions)}"
    )


def _capture_json(capture: Capture) -> dict[str, object]:
    return {
        "path": str(capture.path),
        "loops": list(capture.loops),
        "sessions": list(capture.sessions),
        "evaluations": len(capture.evaluations),
    }


# --- CLI -------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.tools.parity_diff",
        description="Diff two live-loop order-intent captures.",
    )
    parser.add_argument("left", type=Path, help="Capture file from one loop")
    parser.add_argument("right", type=Path, help="Capture file from the other loop")
    parser.add_argument(
        "--align",
        choices=(ALIGN_AUTO, ALIGN_SESSION, ALIGN_TIMESTAMP),
        default=ALIGN_AUTO,
        help="How evaluations are paired (default: auto)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=0.0,
        help="Absolute quantity/price slack for investigation only (default: exact)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Divergences to print, 0 for all (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument("--json", action="store_true", help="Emit structured JSON instead of text")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    """Parse arguments, render the diff to stdout, and return the process exit code."""
    args = build_parser().parse_args(argv)
    left_path: Path = args.left
    right_path: Path = args.right
    alignment: str = args.align
    tolerance: float = args.tolerance
    limit: int = args.limit
    as_json: bool = args.json

    if tolerance < 0.0:
        sys.stderr.write("error: --tolerance must not be negative\n")
        return 2

    try:
        report = compare(
            load_capture(left_path),
            load_capture(right_path),
            tolerance=tolerance,
            alignment=alignment,
        )
    except CaptureError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    sys.stdout.write(render_json(report, limit) if as_json else render_text(report, limit))
    return 1 if report.divergences else 0


def main() -> int:
    return run()


if __name__ == "__main__":
    sys.exit(main())
