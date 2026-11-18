# E2E suite

This suite drives the REAL running service mesh over the same Connect wire the
browser uses. There are no mocks and no monkeypatching: every request traverses
the real auth middleware, servicers, Postgres, Redis, and Kafka. The wire format
(unary Connect-JSON POSTs, enveloped server-stream frames) is hand-rolled in
`client.py`, which keeps the tests transparently close to what the frontend
sends.

## Running

```bash
make dev            # or: cd infrastructure/docker && docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
make seed-demo      # idempotent demo tenant (demo@llamatrade.ai / demo1234)
make test-e2e       # or: cd tests/e2e && pytest . -o addopts=""
```

The suite skips itself when the mesh is unreachable (`_require_mesh` in
`conftest.py`) and requires Python 3.14+ (the repo uses PEP 758 syntax). The
host process needs `llamatrade_proto` and `llamatrade_events` installed
(`make test-e2e` installs them into `.venv`).

## Harness

- `client.py` — `MeshClient`, one per identity (a real `Login` bearer token plus
  the tenant `context` the frontend stores attach per call). `NO_CONTEXT_METHODS`
  lists the RPCs whose proto requests carry no `TenantContext` (they authenticate
  on the JWT alone); adding a context to those bodies is a wire error.
- `conftest.py` — the session-scoped `demo` client (seeded read identity) and the
  `throwaway_tenant` factory. Convention: reads may use `demo`; every mutating
  flow registers its own throwaway tenant so the suite is order-independent and
  repeatable. The exceptions are delta-based, balance-neutral legs on demo
  (wallet deposit/withdraw, execution fill round trips).
- `_ledger.py` — bounded pollers over the ledger/portfolio read surface
  (`wait_position`, `wait_sleeve_closed`, `unallocated_free`, ...). All waiting
  in this suite is a bounded poll with an explicit budget; there are no fixed
  sleeps for asynchronous outcomes.
- `_scaffold.py` — the throwaway money-path scaffold: placeholder broker
  credential (stored unvalidated; the live check is the separate
  `ValidateAlpacaCredentials` RPC), unseeded ledger account, deposit, strategy
  from seeded DSL, funded execution. This lets corporate-action, sleeve-close,
  credential-guard, and producer-notification journeys run entirely on
  throwaway tenants.
- `test_seed_contract.py` — pins what `make seed-demo` must provide; when the
  seed drifts these fail with a precise reason instead of a downstream flow
  failing obscurely.

## The three external seams

Only genuine third parties are substituted; everything downstream of each seam
runs for real.

1. **Alpaca.** The runner's broker fill emitter is the one Alpaca-dependent
   piece with no service-level simulator, so tests publish terminal
   `LedgerFill`s onto the real Kafka fills stream (`publish_ledger_fill`).
   Portfolio's consumer, the ledger writer, FIFO lots, and the projection all
   run for real. Live bars are injected the same way (`publish_bar`, drives
   price alerts).
2. **Stripe.** Billing points at `stripe-mock` (real-shaped API), so
   checkout/subscribe exercise the real Stripe SDK path. stripe-mock cannot
   EMIT webhooks, so `test_billing_webhooks.py` plays Stripe itself: it POSTs
   synthetic events to the real `/webhooks/stripe` route with a genuine
   `t=<ts>,v1=<hmac>` signature (signed with `STRIPE_WEBHOOK_SECRET` when the
   mesh sets one; the dev mesh leaves it unset and billing's dev-only branch
   skips verification while still requiring the header).
3. **The LLM.** Agent model turns are non-deterministic and cost tokens, so
   they are opt-in (below). Deterministic agent coverage (session CRUD,
   artifact reads, unary validation, commit rejection paths) always runs.

Two further in-test *actors* are not mocks but real external endpoints the
suite operates: **mailpit** (the SMTP catcher; email round trips assert real
delivery and skip when mailpit is absent) and the **in-test HTTP listener** in
`test_webhook_delivery.py`, which receives the notification service's real
signed webhook POSTs across the Docker bridge.

## Gated journeys

Four markers gate flows that need a real third party, real wall-clock, or a
container restart; everything else runs unconditionally.

- `live_alpaca` (`E2E_LIVE_ALPACA=1`, needs real paper keys on the demo
  account): the live `TradingService` session lifecycle
  (`test_trading_lifecycle.py::test_live_session_lifecycle`) and broker asset
  resolution (`test_market_data.py::test_assets_resolve_for_seeded_symbols` —
  asset reference data has no seeded fallback, it comes only from the broker).
- `live_llm` (`E2E_LIVE_LLM=1`): the streaming turn shape
  (`test_agent_copilot.py::test_stream_message_yields_deltas_and_a_terminal_complete`),
  the unary `SendMessage` full turn, and the `CommitArtifact` accept path.
  The accept path is live-gated because a pending artifact can only be produced
  by a model turn: there is no LLM-free RPC that creates one, and committing
  the demo seed's artifact would consume it permanently (it creates a real
  strategy and flips `is_committed`), breaking the seed contract for every
  later run.

- `slow` (`E2E_SLOW=1`): the price-alert cooldown *expiry* leg
  (`test_notifications.py::test_cooldown_expiry_re_arms_the_alert`). One minute
  is the shortest cooldown the API accepts (0 falls back to 60 minutes), so the
  test spends it. The suppression half of the contract runs unconditionally.
- `restart` (`E2E_RESTART=1`): `test_restart_resilience.py`, which stops the
  portfolio container, publishes a fill into its absence, and starts it again to
  prove the durable consumer folds the backlog. It is opt-in because the restart
  disrupts anything else sharing the mesh.

Permanently out of e2e reach (documented, not silently skipped):

- **The Alpaca OAuth happy path** needs a genuine provider authorization code.
  `test_auth_flows.py::TestOAuthRoutes` covers the reachable surface: start is
  fail-closed without `ALPACA_OAUTH_*` config, the public callback rejects a
  forged `state`, and exchange/complete-signup reject invalid tickets.
- **`CORPORATE_ACTION_PROPOSED`** is emitted only by portfolio's internal
  leader-elected loop over Alpaca's announcement feed; there is no propose RPC.
  `test_corporate_actions.py` drives the apply side over the wire and asserts
  the `CORPORATE_ACTION_APPLIED` notification.

## Environment knobs

| Variable | Default | Purpose |
|---|---|---|
| `E2E_*_URL` | `http://localhost:88xx` | Per-service Connect endpoints |
| `E2E_KAFKA_BOOTSTRAP` | `localhost:9092` | Broker for the injection seams |
| `E2E_MAILPIT_URL` | `http://localhost:8025` | Mail catcher API |
| `E2E_DEMO_EMAIL` / `E2E_DEMO_PASSWORD` | seeded demo | Read identity |
| `E2E_WEBHOOK_CALLBACK_HOST` | `host.docker.internal` | How the mesh reaches the in-test webhook listener; set `localhost` for a host-local (honcho) mesh, or a `host-gateway` mapping / bridge IP on Linux CI |
| `E2E_AUTH_CONTAINER` | `llamatrade-auth` | Where invite codes are minted for fresh registrations; set it empty for a host-local (honcho) mesh to run the operator tool from `services/auth` against `DATABASE_URL` |
| `STRIPE_WEBHOOK_SECRET` | unset | Signs synthetic Stripe events when the mesh verifies signatures |
| `E2E_LIVE_ALPACA` / `E2E_LIVE_LLM` | off | Opt-in gated journeys |
| `E2E_SLOW` | off | Legs that wait on a real timer (~70s) |
| `E2E_RESTART` | off | Legs that stop and start a container |

## Known contract constants

- Injected fills are globally deduplicated on `client_order_id` alone
  (`derive_event_id(fill.client_order_id)` in
  `libs/events/llamatrade_events/catalog/fills.py`), so every
  `publish_ledger_fill` id must be unique per run — embed a fresh uuid or the
  execution id, never a constant. A reused id is silently dropped by the
  writer's event-id dedupe and the test times out at `wait_position`.

- The webhook auto-disable threshold is `WEBHOOK_DISABLE_THRESHOLD = 25`, a
  module constant in `services/notification/src/delivery.py` (not env-tunable);
  the disable test drives 25 real failed deliveries against a 404 endpoint
  (4xx responses are not retried, so each delivery is a single POST).
- The notification market loop refreshes its watched-symbol set every 30s and
  only on bar arrival, so alert tests keep feeding bars while polling.
- The free tier allows one RUNNING execution per tenant; scaffolded flows that
  need two holder sleeves stop the first execution (its open lots re-home to
  the Unmanaged sleeve at cost) before starting the second.
