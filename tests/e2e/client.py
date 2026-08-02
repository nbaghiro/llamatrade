"""Zero-mock E2E client for the live LlamaTrade service mesh.

The suite drives the REAL running services over the same Connect wire the browser
uses: unary calls are ``application/json`` POSTs to ``/{ServiceFQN}/{Method}``;
server-streams are ``application/connect+json`` enveloped frames. A ``MeshClient``
is bound to one identity (a real ``Login`` bearer token + the tenant ``context``
the stores attach per call), so each test reads like a user session and every
request traverses the real auth middleware, servicers, DB, Redis and Kafka.

The host has no ``connectrpc``/generated clients (they live only in the images),
so the wire format is hand-rolled here — which also keeps the tests transparently
close to what the frontend sends.

The only substitutions are the genuine third parties we do not control:
  * Alpaca — a fill is published to the real ledger stream (``publish_ledger_fill``)
    to stand in for the runner's broker fill emitter; everything downstream is real.
  * Stripe — the billing service points at ``stripe-mock`` (real-shaped API).
  * The LLM — agent chat streaming runs only when explicitly enabled.
"""

from __future__ import annotations

import json
import os
import struct
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import IO, Any

# Decoded Connect-JSON payloads are dynamically shaped (proto→JSON); typed as a
# JSON object at the wire boundary, like the codebase's JSONB columns.
JSON = dict[str, Any]

# --- Service endpoints (env-overridable; default to the local split stack) ----
HOSTS: dict[str, str] = {
    "auth": os.getenv("E2E_AUTH_URL", "http://localhost:8810"),
    "strategy": os.getenv("E2E_STRATEGY_URL", "http://localhost:8820"),
    "backtest": os.getenv("E2E_BACKTEST_URL", "http://localhost:8830"),
    "market_data": os.getenv("E2E_MARKET_DATA_URL", "http://localhost:8840"),
    "trading": os.getenv("E2E_TRADING_URL", "http://localhost:8850"),
    "portfolio": os.getenv("E2E_PORTFOLIO_URL", "http://localhost:8860"),
    # LedgerService is served by the portfolio process.
    "ledger": os.getenv("E2E_PORTFOLIO_URL", "http://localhost:8860"),
    "billing": os.getenv("E2E_BILLING_URL", "http://localhost:8880"),
    "notification": os.getenv("E2E_NOTIFICATION_URL", "http://localhost:8870"),
    "agent": os.getenv("E2E_AGENT_URL", "http://localhost:8990"),
}
SERVICE_FQN: dict[str, str] = {
    "auth": "llamatrade.AuthService",
    "strategy": "llamatrade.StrategyService",
    "backtest": "llamatrade.BacktestService",
    "market_data": "llamatrade.MarketDataService",
    "trading": "llamatrade.TradingService",
    "portfolio": "llamatrade.PortfolioService",
    "ledger": "llamatrade.LedgerService",
    "billing": "llamatrade.BillingService",
    "notification": "llamatrade.NotificationService",
    "agent": "llamatrade.AgentService",
}

# RPCs that carry identity in the JWT only — the stores send NO body ``context``
# for these (auth's Alpaca-credential RPCs, GetMarketStatus). Requests here are
# not auto-augmented with the tenant context.
NO_CONTEXT_METHODS: frozenset[str] = frozenset(
    {
        "GetCurrentUser",
        "ListAlpacaCredentials",
        "CreateAlpacaCredentials",
        "DeleteAlpacaCredentials",
        "ValidateAlpacaCredentials",
        "GetAlpacaCredentials",
        # Market-data reads are identified by the JWT only (no body context) — the
        # web market store sends them without a TenantContext.
        "GetMarketStatus",
        "GetSnapshot",
        "GetSnapshots",
        "GetHistoricalBars",
        "GetMultiBars",
        "GetAssets",
    }
)

# Connect public methods never carry a bearer token (the frontend interceptor
# skips them).
PUBLIC_METHODS: frozenset[str] = frozenset({"Login", "Register", "RefreshToken"})

DEMO_EMAIL = os.getenv("E2E_DEMO_EMAIL", "demo@llamatrade.ai")
DEMO_PASSWORD = os.getenv("E2E_DEMO_PASSWORD", "demo1234")

# The harness publishes fills to the *live* mesh's Kafka broker (the one the
# running portfolio consumer reads).
KAFKA_BOOTSTRAP = (
    os.getenv("E2E_KAFKA_BOOTSTRAP") or os.getenv("KAFKA_BOOTSTRAP_SERVERS") or "localhost:9092"
)

_UNARY_TIMEOUT = float(os.getenv("E2E_UNARY_TIMEOUT", "30"))
_STREAM_TIMEOUT = float(os.getenv("E2E_STREAM_TIMEOUT", "120"))


class MeshError(Exception):
    """A Connect error from the live mesh (carries the Connect code + HTTP status)."""

    def __init__(self, where: str, http_status: int, code: str, message: str, raw: str = ""):
        self.where = where
        self.http_status = http_status
        self.code = code
        self.message = message
        self.raw = raw
        super().__init__(f"{where} -> HTTP {http_status} [{code}]: {message}")


def _parse_connect_error(where: str, http_status: int, body: bytes) -> MeshError:
    """Decode a Connect unary error body ({'code','message'}) into a MeshError."""
    raw = body.decode(errors="replace")
    code, message = "unknown", raw
    try:
        doc = json.loads(raw)
        if isinstance(doc, dict):
            code = str(doc.get("code", code))
            message = str(doc.get("message", message))
    except ValueError, TypeError:
        pass
    return MeshError(where, http_status, code, message, raw)


def _read_exactly(fp: IO[bytes], n: int) -> bytes:
    """Read exactly ``n`` bytes from a stream (urllib may return short reads)."""
    chunks: list[bytes] = []
    remaining = n
    while remaining > 0:
        chunk = fp.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class MeshClient:
    """A Connect client bound to one identity (token + tenant context).

    ``call`` auto-attaches the tenant ``context`` to the request body exactly as
    the frontend stores do (except for the NO_CONTEXT RPCs), and the bearer token
    to every non-public request — so tests mirror real UI calls without repeating
    boilerplate. ``stream`` reads Connect server-stream frames.
    """

    def __init__(self, token: str | None = None, ctx: JSON | None = None):
        self.token = token
        self.ctx: JSON = ctx or {}

    # -- request building -----------------------------------------------------
    def _headers(self, method: str, content_type: str) -> dict[str, str]:
        headers = {"Content-Type": content_type}
        if self.token and method not in PUBLIC_METHODS:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _with_context(self, method: str, body: JSON, context: bool) -> JSON:
        """Attach the tenant context to the body as the frontend stores do."""
        if not context or method in NO_CONTEXT_METHODS or not self.ctx or "context" in body:
            return body
        return {"context": self.ctx, **body}

    # -- unary ----------------------------------------------------------------
    def call(
        self, service: str, method: str, body: JSON | None = None, *, context: bool = True
    ) -> JSON:
        """POST a unary Connect-JSON request; return the decoded response.

        Raises MeshError on any non-2xx (with the Connect code + message).
        """
        payload = self._with_context(method, dict(body or {}), context)
        url = f"{HOSTS[service]}/{SERVICE_FQN[service]}/{method}"
        where = f"{service}.{method}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers=self._headers(method, "application/json"),
        )
        try:
            with urllib.request.urlopen(req, timeout=_UNARY_TIMEOUT) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise _parse_connect_error(where, e.code, e.read()) from e
        except urllib.error.URLError as e:
            raise MeshError(
                where, 0, "unavailable", f"unreachable ({e.reason}); is the mesh up?"
            ) from e

    # -- server-stream --------------------------------------------------------
    def stream(
        self, service: str, method: str, body: JSON | None = None, *, context: bool = True
    ) -> Iterator[JSON]:
        """Open a Connect server-stream; yield each decoded message frame.

        Frames are enveloped: [1 flag byte][4-byte big-endian length][payload].
        The end-of-stream frame (flag & 0x02) carries any error and terminates.
        """
        payload = self._with_context(method, dict(body or {}), context)
        url = f"{HOSTS[service]}/{SERVICE_FQN[service]}/{method}"
        where = f"{service}.{method}"
        data = json.dumps(payload).encode()
        frame = struct.pack(">BI", 0, len(data)) + data
        headers = self._headers(method, "application/connect+json")
        headers["Connect-Protocol-Version"] = "1"
        req = urllib.request.Request(url, data=frame, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=_STREAM_TIMEOUT)
        except urllib.error.HTTPError as e:
            raise _parse_connect_error(where, e.code, e.read()) from e
        except urllib.error.URLError as e:
            raise MeshError(
                where, 0, "unavailable", f"unreachable ({e.reason}); is the mesh up?"
            ) from e
        with resp:
            while True:
                header = _read_exactly(resp, 5)
                if len(header) < 5:
                    break
                flag, length = struct.unpack(">BI", header)
                msg = _read_exactly(resp, length) if length else b""
                if flag & 0x02:  # end-of-stream envelope
                    end = json.loads(msg or b"{}")
                    err = end.get("error") if isinstance(end, dict) else None
                    if err:
                        raise MeshError(
                            where, 200, str(err.get("code", "unknown")), str(err.get("message", ""))
                        )
                    break
                yield json.loads(msg or b"{}")

    def try_call(
        self, service: str, method: str, body: JSON | None = None, *, context: bool = True
    ) -> None:
        """Best-effort call for cleanup paths — swallows MeshError."""
        try:
            self.call(service, method, body, context=context)
        except MeshError:
            pass


# --- Identity ----------------------------------------------------------------
def login(
    email: str = DEMO_EMAIL,
    password: str = DEMO_PASSWORD,
    *,
    retries: int = 4,
    backoff: float = 5.0,
) -> MeshClient:
    """Log in via the real AuthService and return a MeshClient bound to the user.

    Backs off and retries on a Login rate-limit (429) so the suite tolerates a
    busy auth bucket; a wrong-password (401) still raises immediately.
    """
    anon = MeshClient()
    last: MeshError | None = None
    for attempt in range(max(1, retries)):
        try:
            resp = anon.call("auth", "Login", {"email": email, "password": password}, context=False)
        except MeshError as e:
            if e.http_status != 429 and e.code != "resource_exhausted":
                raise
            last = e
            time.sleep(backoff * (attempt + 1))
            continue
        token = resp.get("accessToken")
        user = resp.get("user", {})
        tenant_id = user.get("tenantId", "")
        if not token or not tenant_id:
            raise MeshError("auth.Login", 200, "unauthenticated", f"login failed for {email}")
        ctx = {"tenantId": tenant_id, "userId": user.get("id", ""), "roles": user.get("roles", [])}
        return MeshClient(token=token, ctx=ctx)
    raise last or MeshError("auth.Login", 429, "resource_exhausted", "login rate-limited")


def register_and_login(tenant_name: str, email: str, password: str = "e2e-Passw0rd!") -> MeshClient:
    """Register a fresh tenant then log in (Register does not auto-login in the UI)."""
    anon = MeshClient()
    anon.call(
        "auth",
        "Register",
        {"tenantName": tenant_name, "email": email, "password": password},
        context=False,
    )
    return login(email, password)


def mesh_up() -> bool:
    """True when the auth service answers /health (the suite's liveness gate)."""
    try:
        req = urllib.request.Request(f"{HOSTS['auth']}/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except urllib.error.URLError, TimeoutError, OSError:
        return False


# --- Proto/JSON helpers ------------------------------------------------------
def epoch(dt: datetime) -> str:
    """proto3 JSON encodes int64 (Timestamp seconds) as a string."""
    return str(int(dt.timestamp()))


def decimal_val(d: object) -> float:
    """Parse a proto Decimal ({'value': '...'}) — or a plain number — to float."""
    if isinstance(d, dict):
        return float(d.get("value", 0) or 0)
    if isinstance(d, int | float | str):
        return float(d or 0)
    return 0.0


def status_is(value: object, name: str, number: int) -> bool:
    """Connect-JSON may render an enum as its NAME or its integer."""
    return value == name or value == number or value == str(number)


def pick_strategy(strategies: list[JSON]) -> JSON | None:
    """First ACTIVE/PAUSED strategy with symbols (backtestable; drafts are rejected)."""
    for s in strategies:
        if not s.get("symbols"):
            continue
        st = s.get("status")
        if status_is(st, "STRATEGY_STATUS_ACTIVE", 2) or status_is(st, "STRATEGY_STATUS_PAUSED", 3):
            return s
    return None


# --- Alpaca fill seam (the ledger fill stream) -------------------------------
def publish_ledger_fill(
    tenant_id: str,
    account_id: str,
    sleeve_id: str,
    client_order_id: str,
    symbol: str,
    side: str,
    qty: str,
    price: str,
) -> None:
    """Publish a terminal LedgerFill to the real ledger fills stream.

    Stands in for the ONE Alpaca-dependent piece — the runner's fill emitter
    (which has no service-level sim seam). Everything downstream (portfolio's
    consumer, LedgerWriter, FIFO lots, projection) runs for real.
    """

    async def _pub() -> None:
        from llamatrade_events import EventBus, KafkaTransport
        from llamatrade_events.catalog.fills import FillEvents
        from llamatrade_proto.generated import events_pb2

        bus = EventBus(KafkaTransport(KAFKA_BOOTSTRAP))
        try:
            fill = events_pb2.LedgerFill(
                tenant_id=tenant_id,
                account_id=account_id,
                sleeve_id=sleeve_id,
                client_order_id=client_order_id,
                symbol=symbol,
                side=side,
                qty=qty,
                price=price,
                filled_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            await FillEvents(bus=bus).publish_fill(fill)
        finally:
            await bus.close()

    _run_async(_pub())


# --- Notification seam (the notifications stream + mailpit) ------------------
MAILPIT_URL = os.getenv("E2E_MAILPIT_URL", "http://localhost:8025")


def publish_notification_event(
    tenant_id: str,
    category: int,
    *,
    user_id: str = "",
    symbol: str = "",
    reason: str = "",
    dedup: str = "",
) -> None:
    """Publish a NotificationEvent onto the real notifications stream.

    Stands in for any producing service; everything downstream (the durable
    consumer, persist, preference resolution, delivery) runs for real.
    """

    async def _pub() -> None:
        from llamatrade_events import EventBus, KafkaTransport
        from llamatrade_events.catalog.notifications import NotificationEvents
        from llamatrade_proto.generated import events_pb2

        bus = EventBus(KafkaTransport(KAFKA_BOOTSTRAP))
        try:
            event = events_pb2.NotificationEvent(category=category, symbol=symbol, reason=reason)
            await NotificationEvents(bus=bus).publish(
                event,
                tenant_id=tenant_id,
                user_id=user_id,
                dedup_parts=(dedup,) if dedup else (),
            )
        finally:
            await bus.close()

    _run_async(_pub())


def publish_bar(symbol: str, close: str, volume: int = 100_000) -> None:
    """Publish one live Bar onto the real bars stream (drives price alerts)."""

    async def _pub() -> None:
        from llamatrade_events import EventBus, KafkaTransport
        from llamatrade_events.catalog.bars import BarEvents
        from llamatrade_proto.generated import common_pb2, market_data_pb2

        bus = EventBus(KafkaTransport(KAFKA_BOOTSTRAP))
        try:
            bar = market_data_pb2.Bar(
                symbol=symbol,
                timestamp=common_pb2.Timestamp(seconds=int(datetime.now(UTC).timestamp())),
                close=common_pb2.Decimal(value=close),
                open=common_pb2.Decimal(value=close),
                high=common_pb2.Decimal(value=close),
                low=common_pb2.Decimal(value=close),
                volume=volume,
            )
            await BarEvents(bus=bus).publish(bar)
        finally:
            await bus.close()

    _run_async(_pub())


def mailpit_messages(query: str) -> list[dict[str, object]]:
    """Search the mailpit catcher; empty when mailpit is not running."""
    import httpx

    try:
        response = httpx.get(f"{MAILPIT_URL}/api/v1/search", params={"query": query}, timeout=5.0)
        response.raise_for_status()
    except httpx.HTTPError:
        return []
    body = response.json()
    messages = body.get("messages", [])
    return messages if isinstance(messages, list) else []


def mailpit_message_text(message_id: str) -> str:
    import httpx

    try:
        response = httpx.get(f"{MAILPIT_URL}/api/v1/message/{message_id}", timeout=5.0)
        response.raise_for_status()
    except httpx.HTTPError:
        return ""
    body = response.json()
    return str(body.get("Text", ""))


def mailpit_message_html(message_id: str) -> str:
    """The rendered HTML part of a captured email (empty when unavailable)."""
    import httpx

    try:
        response = httpx.get(f"{MAILPIT_URL}/api/v1/message/{message_id}", timeout=5.0)
        response.raise_for_status()
    except httpx.HTTPError:
        return ""
    body = response.json()
    return str(body.get("HTML", ""))


def mailpit_available() -> bool:
    import httpx

    try:
        return httpx.get(f"{MAILPIT_URL}/api/v1/info", timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


def _run_async(coro: Any) -> object:
    """Run a coroutine even when a loop is already running (pytest-asyncio)."""
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(asyncio.run, coro).result()
