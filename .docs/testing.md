# Testing

How the platform is tested: the layer model, what each suite covers, where the fakes sit, what the coverage gates enforce, and how everything runs locally and in CI. The companion architecture document describes what the system does; this one describes how we know it does it.

## 1. Principles

- **Test the subject, never the mock.** Fakes sit at process boundaries (broker HTTP, WebSocket, SMTP, Stripe, the Kafka wire), not inside the code under test. Where a fake is load-bearing it is either shipped by the lib that owns the real implementation (`FakeTransport`, `MockTradeStream`) or pinned to the real surface by a contract test (billing's `MockStripeClient` has a signature-parity test that fails CI on drift).
- **Real infrastructure where semantics live in the infrastructure.** RLS, advisory locks, `ON CONFLICT` predicates, Kafka partition ordering, Celery acks-late: these are proven against real Postgres, Kafka, and Redis via testcontainers, not simulated. SQLite stands in only where the semantics under test are the query predicates themselves (the real-SQL-on-SQLite tier).
- **Money paths get the strictest treatment.** The ledger fill path is proven on a real broker with a tracer-fill exactly-once test; the fill-ingestion consumer is pinned by a six-scenario golden parity suite; the double-spend allocate race and the cancel-vs-complete race run as real concurrent transactions.
- **Suites that do not run do not count.** Every suite has a CI step with a binding coverage gate, and Docker-gated tests hard-fail (rather than skip) in CI via `CI_REQUIRE_DOCKER=1`. A green run means everything actually executed.
- **Coverage gates are ratchets, not targets.** Suites at or above 80 gate at 80. Suites measured below 80 gate at their measured floor, rounded down, so coverage can only move up; the floor is raised as tests land.

## 2. The layer model

```
┌──────────────────────────────────────────────────────────────────────┐
│  e2e (tests/e2e)                 93 tests · zero-mock live mesh      │
│  golden / parity / conformance   drift-catchers across impls         │
│  integration (in-suite)          testcontainers PG/Kafka/Redis/TS    │
│  unit (per-package)              ~5,000 tests · fakes at boundaries  │
└──────────────────────────────────────────────────────────────────────┘
```

Integration tests live inside each package's suite (`tests/integration/`, marked `integration`) rather than in a separate tree, so a package's full local run covers both tiers and the coverage gate measures them together.

## 3. Library suites (`libs/*/tests`)

| Lib | Tests | Gate | Character |
|---|---|---|---|
| dsl | 229 | 80 | Pure unit, zero mocks: parser, validator, serializer, JSON projection, static analysis, plus the conformance-corpus consumer. |
| runtime | 393 | 80 | The real evaluation engine over synthetic bars; TA-Lib as an external numeric oracle (skips without the C lib); live-vs-backtest parity proofs. |
| events | 182 | 80 | Three tiers: the shipped `FakeTransport` (itself contract-tested), an in-memory Kafka broker for transport branches, and real-broker integration including SASL/OAUTHBEARER. |
| telemetry | 78 | 80 | Real OTel SDK; assertions against the actual Prometheus exposition; middleware, conventions, tracing, logging. |
| common | 238 | 80 | Real crypto and real ASGI: token verification, `resolve_identity` forgery cases, fail-closed middleware, rate limiting, revocation, KMS cipher, `supervise()`. Ships the shared `FakeRedis` in `llamatrade_common.testing`. |
| db | 385 | 96 | Three tiers: SQLite model-shape tests; real-SQL-on-SQLite for query-predicate helpers (`_sqlite_tier.py` is the shared plumbing); Docker-gated real Postgres for RLS, session GUCs, advisory-lock failover, and `init_db`. |
| alpaca | 257 | 81 | REST clients through respx at the HTTP seam; resilience (limiter, breaker, retry) with metrics; the real stream loops (`TradingStreamClient.stream()`, `BarStreamClient.stream()`, the run pump) over a `FakeWebSocket`. `MockTradeStream` ships beside the real client and models its give-up exhaustion. |
| proto | 121 | 86 | S2S client request/response mapping at the generated-client seam, interceptors, the service-token cache, timestamps. The servicer-binding conformance test runs in its own CI job. |

## 4. Service suites (`services/*/tests`)

Every service suite includes a `conftest.py` FakeTransport fixture silencing the notification bus, and every service now also asserts its own emissions (decoded envelopes, categories, dedup parts) rather than only silencing them.

| Service | Tests | Gate | Integration tier |
|---|---|---|---|
| auth | 182 | 85 | Real-PG modules for auth tokens and the email-token RPC flows (byte-identical no-account-leak responses, single-use, revoke-all-on-reset). Unit tier uses a per-model-routed `MockAsyncSession`. |
| strategy | 183 | 80 | Real-PG tenant-isolation module. The reference suite for emission assertions (`test_notifications_emitted.py`). |
| billing | 236 | 92 | Real-SQL-on-SQLite tier for servicer flows and cross-tenant denial. One `MockStripeClient` in conftest, pinned by a signature-parity contract test. |
| agent | 310 | 81 | Real-SQL-on-SQLite isolation tier (two seeded tenants through the real models and queries); LLM clients tested over structured SDK fakes with dependency metrics asserted. |
| notification | 156 | 80 | `tests/integration/`: real-PG pipeline (persist-then-deliver, dedup, webhook auto-disable), servicer CRUD with cross-tenant checks, price-alert engine including leader election and the market-loop body. |
| market-data | 445 | 88 | `tests/unit/` for the ingestor, `tests/integration/` on real Timescale (migrations, gap-fill, continuous aggregates), real Kafka (bar publish both directions), and real Redis (cache lifecycle). Alpaca-failure modes covered via `FakeMarketDataClient` raise modes. |
| backtest | 319 | 80 | `tests/integration/` on real PG + Redis: enqueue-failure compensation, the `WHERE status = RUNNING` cancel race with both winner orderings, reaper cutoffs, `CancellationFlag` fail-open, and a live Celery worker smoke proving queue routing, acks-late, JSON serialization, and W3C trace continuity across the broker. |
| trading | 810 | 80 | `tests/integration/` on real PG (client-order-id uniqueness, advisory-lock lease failover with `pg_terminate_backend` and container restart) and real Kafka (fill publish with producer-span and failure-metric assertions). Unit tier covers bracket rollback, the trade-stream supervisor (via the mock's give-up mode), risk layers through the public `check_order`, runner lifecycle, and a 22-case servicer error-code mapping. |
| portfolio | 569 | 80 | Four tiers: pure ledger-kernel fold tests; the six-scenario golden parity suite for fill ingestion (`tests/golden/`); fake-session tests that execute real compiled SQL; and `tests/integration/` on real PG + Kafka (fill e2e with tracer-fill exactly-once proof, non-superuser RLS, writer-election failover, the two-concurrent-allocate double-spend race, checkpoint forward-only predicate, DLQ purge against a real broker, statement tool). |

## 5. Golden, parity, and conformance layers

These catch drift between implementations that unit tests structurally cannot:

- **DSL conformance corpus** (`tests/conformance/`): 17 S-expression cases with committed canonical JSON plus the vocabulary table. The Python DSL is the authority; `libs/dsl` and the TypeScript implementation in `apps/web` both validate against the same files, and a CI job regenerates the corpus and diffs it so an authority change cannot ship without regeneration.
- **Fill-ingestion golden parity** (`services/portfolio/tests/test_fill_ingestion_parity.py` + `tests/golden/`): six recorded scenarios (interleaving, duplicate redelivery, out-of-order reservations, mid-stream poison, injected transient failure, restart-resume) snapshotted across five axes. The suite was the cutover gate for the StreamConsumer migration and remains the regression pin.
- **Live/backtest parity** (`libs/runtime`, `services/trading/tests/test_parity_capture.py`): identical bars through both loop implementations, diffed order intents, with a vacuousness guard.
- **Servicer-binding conformance** (`libs/proto`, own CI job): every service's real servicer resolved against its generated Connect endpoint map, catching method-name drift that type-checks green but dispatches to nothing.
- **Statement golden** (`services/portfolio/tests/golden/statement_full.txt`): the operator statement render locked three ways including CLI stdout.
- **Email shells** (own CI job): the committed React Email HTML shells re-rendered and diffed.

## 6. End-to-end (`tests/e2e`)

93 tests in 20 journey files against the real nine-service mesh: no internal service is mocked, and no `unittest.mock` or monkeypatching exists anywhere in the tree. The harness is a hand-rolled Connect wire client (`client.py`) bound to real login identities; `conftest.py` skips the suite when the mesh is unreachable and mints throwaway tenants for mutating flows; `_ledger.py` and `_scaffold.py` provide bounded pollers and the funded-execution scaffold; `test_seed_contract.py` pins the seed assumptions so drift fails with a precise reason.

The external seams, documented in `tests/e2e/README.md`: Alpaca (fills and bars injected onto the real Kafka topics, standing in for the broker stream; real-Alpaca journeys gated behind `E2E_LIVE_ALPACA=1`), Stripe (stripe-mock for client-initiated flows; webhook-driven transitions exercised by POSTing signed synthetic events to the real endpoint), LLM (gated behind `E2E_LIVE_LLM=1`), mailpit for SMTP, and in-test HTTP listeners as real webhook receivers. Journeys cover onboarding, auth email flows, strategy lifecycle, a real Celery backtest with strict CANCELLED assertion, funded trading round trips with ledger assertions, wallet funding, sleeve close with open-position re-homing, corporate-action apply, billing checkout and webhook transitions, broker-credential lifecycle with the deletion guard, notifications including signed webhook delivery and the 25-failure auto-disable, price-alert cooldown, agent flows, and two-tenant isolation over the wire.

Three journeys deserve separate mention because they assert things the rest of the suite structurally cannot. `test_dashboard_after_activity.py` funds a throwaway tenant from empty, fills it, and reads the dashboard RPCs back, so every assertion is a delta that test caused rather than a property of the seed. `test_two_tenant_concurrency.py` runs two tenants through the same journey in parallel on the same symbol with different quantities, which turns a crossed projection into a wrong number instead of a missing row. `test_restart_resilience.py` (opt-in behind `E2E_RESTART=1`) stops the portfolio container, publishes a fill into its absence, and restarts it, which is the only test that would fail if the fill consumer resumed from the latest offset rather than its committed one. The cooldown *expiry* leg sits behind `E2E_SLOW=1` because one minute is the shortest cooldown the API accepts.

In CI the mesh boots from GitHub service containers plus a honcho Procfile (migrations, Timescale migration, direct-DB seed, nine health gates); the job runs on pull requests and main pushes and completes in about four minutes, of which the tests are under a minute.

## 7. CI enforcement

Remote (`.github/workflows/ci.yml`): lint (ruff pinned, no-suppressions gate, pyright pinned) → Test Backend (Postgres, Redis, Redpanda service containers; per-suite steps with the gates above; `CI_REQUIRE_DOCKER=1` so Docker-gated tiers fail loudly if they cannot run) → e2e, servicer-binding conformance, corpus freshness, email-shell drift, proto lint/breaking, kustomize render, and the nine-image build matrix.

Local (`scripts/ci-local.sh`): the same lint and type gates, the auth/strategy/billing/notification/proto suites, all seven shared-lib suites, and the frontend; `--integration` adds the Docker-backed tiers. `make test-integration` runs the integration tiers for the five stateful services; `make test-e2e` runs the mesh suite against the compose stack.

Conventions the gates rely on: integration modules carry a module-level `pytestmark = pytest.mark.integration` (conftest-level marks are ignored by pytest); Docker guards skip locally and hard-fail under `CI_REQUIRE_DOCKER`; metric assertions match by label containment, never exact match, because the OTel exporter appends `otel_scope_*` labels that vary by version; the frontend runs under an explicit vitest config with `--passWithNoTests` removed, so zero collected tests is a failure.

## 8. Writing tests here

- Prefer the lib-owned fakes: `llamatrade_events.testing.FakeTransport`, `llamatrade_common.testing.FakeRedis`, `llamatrade_alpaca`'s mock streams. Do not hand-roll a parallel copy.
- Assert notification emissions by reading `FakeTransport.published` and decoding envelopes; strategy's `test_notifications_emitted.py` is the pattern.
- For tenant-scoping tests, execute the real query predicates: either the real-SQL-on-SQLite tier (`libs/db/tests/_sqlite_tier.py` is the shared plumbing) or a real-Postgres module. A mock that returns what the test asserts proves nothing.
- Spec every `AsyncMock`/`MagicMock` double against the real class or Protocol so signature drift fails.
- New integration modules: module-level `integration` mark, the Docker guard honoring `CI_REQUIRE_DOCKER`, testcontainers with per-test truncation, and the sibling conftest patterns.
- Production changes to money-adjacent paths ship with tests in the same change, and behavior migrations on the money path are gated on dual-run parity before the old implementation is deleted.

## 9. Known gaps

- The live order path (submit/cancel/close through real Alpaca) and the LLM stream run only under their env gates, so CI never exercises them; they are the two standing manual-QA journeys.
- The OAuth happy path needs a real provider ticket and stays unreachable in e2e; start, state validation, and failure branches are covered.
- The corporate-action propose loop reads the broker announcements feed and is covered by unit and integration tests only; e2e covers apply.
- One open defect found by the e2e work is tracked for a portfolio fix: fills replayed into an already-closed sleeve are applied at ingestion and can drive account cash negative, with the invariant tripping only on the next sleeve close.
