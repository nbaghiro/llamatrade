# Trading Service Hardening Plan (2026-06-19)

Outcome of a deep BIG review of `services/trading` (scope: trading + platform auth).
16 numbered issues across Architecture → Code Quality → Tests → Performance; the
chosen direction for each is recorded below (all the recommended option except
#16 = do nothing). See memory `trading-service-hardening-decisions`.

## Decisions (issue → direction)

| # | Area | Decision |
|---|------|----------|
| 1 | Arch | **1A** shared Connect/ASGI auth middleware (verify JWT locally, derive identity into a contextvar; servicers read that). Platform-wide. |
| 2 | Arch | **2A** manual order RPCs resolve per-tenant Alpaca creds from the session (reject if none) — not env defaults. |
| 3 | Arch | **3A** recover-and-resubmit stranded PENDING orders; replay continues submitting; recovery sweep includes null-alpaca orders, guarded by `get_order_by_client_id`. |
| 4 | Arch | **4A** ledger reconciliation safety net (periodic re-publish of recently-terminal orders, idempotent) + tolerant reservation release. |
| 5 | CQ | **5A** Decimal end-to-end in the trading service. |
| 6 | CQ | **6A** OrderCreate type↔price Pydantic validator; map ValidationError → INVALID_ARGUMENT. |
| 7 | CQ | **7A** error-mapping helper (no raw `{e}` to clients, consistent codes); attribution distinguishes transient ledger errors from no-attribution. |
| 8 | CQ | **8A** single executor/service factory for DI + gRPC; fix `_to_proto_order` (real client_order_id, tenant/session). |
| 9 | Tests | **9A** per-RPC tenant-isolation tests (paired with 1A). |
| 10 | Tests | **10A** production shared-`StrategySession` multi-symbol eval tests. |
| 11 | Tests | **11A** full crash-recovery/sync coverage. |
| 12 | Tests | **12A** end-to-end trading↔ledger contract test (fakeredis) + DB-backed order lifecycle. |
| 13 | Perf | **13A** request-scoped DB session per RPC (fixes `await anext(get_db())` leak). |
| 14 | Perf | **14A** reuse process-singletons (RiskManager + caches, publisher); per-request only the session. |
| 15 | Perf | **15A** offload `StrategySession.evaluate()` to `asyncio.to_thread`. |
| 16 | Perf | **16A** do nothing (sequential risk-check awaits are fine at current order rates). |

## Phasing

- **Phase 1 (P0, platform):** 1A + 9A — shared auth lib + edge wiring + trading adoption + tests.
- **Phase 2 (P0/P1, trading):** 8A keystone, carrying 2A + 13A + 14A + 7A + proto fix.
- **Phase 3 (P1):** 3A + 6A + 11A.
- **Phase 4 (P2):** 4A + 5A.
- **Phase 5 (P2):** 15A + 10A + 12A.

## Auth design (Phase 1) — shared `llamatrade_common.auth`

Cross-cutting decision (see memory `platform-connect-auth-gap`): the auth fix is a
**shared lib built here**; portfolio/backtest reviews deferred their adoption to it.

**Mechanism**
- `TenantContext` (frozen): `tenant_id`, `user_id`, `email`, `roles`, `is_service`.
- A request-scoped `ContextVar[TenantContext | None]` + `get/set/current` accessors.
- `AuthMiddleware` (pure ASGI, so contextvars propagate to the handler task):
  - Public paths (health, metrics, OPTIONS preflight, auth `Login`/`Register`) pass through.
  - Else require **either** a valid user access JWT (`type=access`, HS256, `JWT_SECRET`)
    → user `TenantContext`, **or** a valid service token → service context
    (`is_service=True`). Missing/invalid → 401 (fail-closed).
- **Service tokens:** a short-lived JWT with `type=service` signed with `JWT_SECRET`,
  minted on demand and attached by inter-service gRPC clients via a client
  interceptor on `BaseGRPCClient`. This keeps inter-service calls working under the
  fail-closed edge (they carry no user token today).
- `resolve_identity(wire_context) -> (tenant_id, user_id)` for servicers:
  - user context → return the **token** identity; if the wire `context.tenant_id`
    is present and differs → reject (cross-tenant guard);
  - service context → trust the wire context (the calling service already
    authenticated the user and forwards tenant);
  - no context (unit tests; never in prod because the middleware is fail-closed) →
    trust the wire context. This keeps existing servicer unit tests green.

**Rollout**
- Wire `AuthMiddleware` into all 9 services' `main.py` (edge protection everywhere).
- Attach the service-token interceptor to `BaseGRPCClient` (all inter-service calls).
- **Fully adopt** in the trading servicer: a single `_context(request)` helper using
  `resolve_identity`, used by every RPC (closes cross-tenant on the money path).
- Other services keep trusting their wire context for now but are protected at the
  edge (anonymous access closed) and adopt `resolve_identity` as queued follow-up.

## Notes
- Money: `Decimal` end-to-end in trading (DB + ledger already Decimal).
- `fakeredis` added to trading dev deps for the Phase-5 integration test.
- Built on [[trading-ledger-integration-decisions]], [[trading-event-sourcing-target-arch]].
