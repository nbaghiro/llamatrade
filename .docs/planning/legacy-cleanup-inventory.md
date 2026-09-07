# Legacy and dead-code cleanup inventory

From the 2026-08-03 repo-wide sweep. Context: pre-launch, no external consumers, house precedent is to delete retired paths outright rather than keep compatibility shims. Grouped by removal risk. Items marked (decision) need an owner call before deletion.

## A. Delete with zero risk

1. `scripts/setup.sh` (73 lines). No invoker (`make dev-setup` runs `scripts/dev-local.sh setup`). Stale four ways: writes a `.env` missing most current vars, uses `pip -e` in a uv workspace, omits the agent service, points at port 8080 for a web app on 8800.
2. `StreamFanout`: `libs/events/llamatrade_events/fanout.py` (99 lines), `tests/test_fanout.py` (126), the `EVENTS_FANOUT_DROPPED_TOTAL` / `EVENTS_FANOUT_CLIENTS` metrics, the `__init__` exports, and the `.docs/telemetry.md` entries. Its docstring claims trading and market-data both use it; they use `StreamManager` and `tail_orders`/`tail_positions` respectively. Zero importers outside the lib.
3. Unused declared dependencies (verified by import grep over each package's `src` and `tests`): agent `openai`; strategy `numpy`; trading `redis`, `tenacity`, `websockets`, `llamatrade-dsl`; market-data `python-jose[cryptography]` (a second crypto stack) and `websockets`; backtest `websockets`; libs/common `httpx`, `prometheus-client`; libs/alpaca `prometheus_client` (both extras); libs/db `pgvector`; libs/proto `grpcio-tools` (codegen runs through buf remote plugins).
4. Dead `libs/common/llamatrade_common/utils.py` helpers, referenced only by `__init__` re-exports and their own tests: `generate_uuid`, `paginate` + `PaginatedResult`, and the sync `decrypt_value`. Callers use `resolve_pagination` / `pagination_response` / `async_decrypt_value`.
5. Dead `.env.example` entries (the only 3 of 45 nothing reads): `USE_GRPC`, `USE_GRPC_MARKET_DATA`, `STRIPE_PUBLISHABLE_KEY` (the web app reads `VITE_STRIPE_PUBLISHABLE_KEY` from its own env file).
6. pgvector vestige: migration 014 creates the extension for `agent_memory_embeddings`, which migration 026 dropped; nothing uses vectors. Drop the `pgvector` dependency and move `infrastructure/docker/docker-compose.yml` and `docker-compose.test.yml` from `pgvector/pgvector:pg16` to `postgres:16`.
7. Docstrings describing deleted files: `services/portfolio/src/ledger/analytics.py` references `domain.py` / `performance_service.py` (neither exists); `read_model.py` narrates the deleted float/JSONB path.
8. Rename-only alias shim in `services/market-data/src/main.py`: the three `llamatrade_alpaca` stream singletons imported under `*_alpaca_stream` aliases.
9. `infrastructure/docker/Dockerfile.migrate` (19 lines): a stale duplicate of `libs/db/Dockerfile` and broken. It installs `libs/common` and `libs/db`, both of which depend on `llamatrade-telemetry`, a workspace-only package resolved by the root manifest, which the image does not copy. Only `deploy-staging.yml` builds it.

## B. Delete after a decision

10. (decision) The trading positions slice is dead end to end. `Position` (`libs/db/.../models/trading.py`) has readers but no writer: `position_service.open_position` / `close_position` / `update_prices` / `count_trades` / `list_all_positions` have zero src callers. The runner holds positions in memory and the ledger is the book of record, so `GetPosition` / `ListPositions` / `ClosePosition` always return empty or NOT_FOUND, and the frontend reads positions from the portfolio service. Either drop the table, model, five methods, three RPCs and the index, or wire a writer.
11. (decision) `services/market-data/src/error_handlers.py` (147 lines) plus its 110-line test. Registered on the app, but every RPC carries `@handle_service_errors`, whose catch-all converts exceptions to `ConnectError(INTERNAL)` before FastAPI's exception middleware sees them, and the only FastAPI-routed endpoint is `/health`. The mapping never fires, so Alpaca rate-limit and symbol-not-found errors reach clients as opaque INTERNAL. Delete, or move the mapping into the servicer.
12. (decision) `services/agent/src/tools/strategy_client.py` (141 lines) plus its 87-line test: a hand-rolled raw-httpx Connect client duplicating the generated `StrategyServiceClient` already imported in `src/tools/clients.py`. It hardcodes the RPC path and a snake_case payload (silently breaks on a proto rename) and reads `STRATEGY_SERVICE_URL`, which no deployment sets. Sole caller: `artifact_service.py`. Related latent bug in `clients.py`: `PORTFOLIO_GRPC_TARGET` defaults to 8830 (backtest's port) and `BACKTEST_GRPC_TARGET` to 8850 (trading's port), masked only because compose and the configmap set both explicitly.
13. (decision) Unfunded-session sizing dual path: `live_session_service` picks `SizingMode.DRIFT` with a sleeve and `BINARY` without, and `_resolve_ledger_identity` documents "(None, None) means a legacy/unfunded session". Reachable only when an execution has no `allocated_capital`. If an execution may never legitimately run unfunded, the BINARY branch and every None-sleeve branch collapse.
14. (decision) `apps/web/src/services/strategy.ts` `listStrategyVersions` and its `listVersions` alias have no consumer. Delete the client wrapper; decide separately whether the RPC stays as product surface.
15. (decision) Strategy-builder conflict machinery in `apps/web/src/store/strategy-builder.ts`: `conflictDetected` and `resolveConflict` are set and cleared but read by no component, and the server has no version field to detect a conflict with anyway (see the round-2 plan's R0.7). Build the UI or delete both.
16. (decision) `reencrypt_value` / `async_reencrypt_value` in `libs/common`: deliberate KMS-rotation scaffolding with no consumer, and the gap register notes a local-to-KMS migration needs a two-cipher pass these do not implement. Keep as planned scaffolding or delete until a rotation runbook exists.

## C. Looks legacy, is alive (do not delete)

17. **Config drift worth fixing on its own.** market-data bus mode and the direct-Alpaca `StreamBridge` are both live: compose sets `MARKET_DATA_BARS_FROM_BUS=true` and `MARKET_DATA_DB_URL`, so compose and CI exercise the bus + Timescale path, while the k8s serving deployment sets neither, so the cluster runs `bridge.py` and the cache-only fallback. Fix the manifests first, soak, and only then remove `bridge.py` (375 lines), its 437-line test, the `_bars_from_bus` branches, and the store-off fallbacks.
18. `TRADING_USE_RUNTIME_LOOP` and the parity harness (`parity_diff.py`, `intent_capture.py`, `runtime_adapters.py`, `test_parity_capture.py`): open gap G54, blocked on a live paper soak. Deletable only after the flip, together with the losing loop.
19. `TRADING_BARS_FROM_SERVICE`: an unflipped optimization pending the same kind of soak.
20. HS256 vs RS256 in `llamatrade_common.auth`: not a dual path to collapse. User tokens pin RS256 when the keypair is configured, service tokens are HS256 by design, the algorithm is pinned by key material, and auth refuses to start in production without the keypair.
21. `select_rate_limiter` / `RedisRateLimiter`: unused from services but wired in `libs/alpaca/client_base.py`.
22. `asyncpg` and `greenlet` are SQLAlchemy asyncio runtime requirements, not imports; `ta-lib` is used via `importorskip` in the golden indicator tests.
23. `services/market-data/src/models.py` is a genuine pure re-export shim over `llamatrade_alpaca`, but about 30 import sites depend on it: a mechanical import rewrite for a separate DRY pass, not a deletion.
24. The `.docs/architecture.md` sections on Redis Streams and the rejected vectorized engine are deliberate decision records.

## Related findings (same cleanup wave, not dead code)

- Undeclared-but-imported dependencies, the latent-break class already recorded for local libs: trading imports `llamatrade_events` undeclared; agent imports `redis`, `sqlalchemy`, `httpx`, `connectrpc`, `starlette`, `llamatrade-telemetry` undeclared; notification imports `numpy` undeclared.
- Clean negative results: no TODO/FIXME/XXX/HACK debt anywhere in `services/`, `libs/`, or the frontend; every module under `services/*/src` is referenced from src except the entrypoints; all Makefile targets resolve; `tests/e2e` and `tests/conformance` are fully wired into Make and CI.

## Not yet audited

The delegated sub-sweeps were killed before reporting, so these remain open: the full proto surface (dead messages, fields, enum values; only partly probed, and note that no service-to-service caller of TradingService exists at all, which makes most of its RPCs unwired product surface rather than deletable code), the full DB surface beyond the positions slice, the full frontend component/page/store reachability graph, the ops sweep over Makefile, compose, k8s, terraform, CI and docs, and the JavaScript half of the dependency audit.
