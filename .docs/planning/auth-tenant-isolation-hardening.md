# Auth Tenant-Isolation Hardening Plan

**Status:** APPROVED (with RLS folded into the same pass). **P0 foundation +
portfolio pilot DELIVERED** (2026-07-16) — see §9. Remaining services pending
pattern sign-off.
**Author:** hardening pass, 2026-07-16.
**Related:** `.docs/planning/platform-gap-review-2026-07.md` (forged-tenant gap #1),
`.docs/planning/trading-hardening-plan.md` (where `resolve_identity` was introduced),
memory `platform-connect-auth-gap`.

---

## 1. Threat model

### The split-auth defect
Auth is two independent checks; the second is missing almost everywhere.

1. **Transport gate — present and fail-closed.** `AuthMiddleware`
   (`libs/common/llamatrade_common/auth.py:206`) verifies the `Authorization:
   Bearer` token via `verify_credential`, 401s if absent/invalid, and stashes the
   decoded `TenantContext` in a ContextVar (`current_context()`). It reads ONLY
   the bearer token — never `X-Tenant-ID`, never the request body.
2. **Data-access identity — missing.** Almost every servicer re-derives identity
   from the request **body**: `tenant_id = UUID(request.context.tenant_id)`,
   without ever comparing that body value against the authenticated principal.

`verify_credential` (auth.py:122) accepts two token types:
- `type=access` → real user; carries authoritative `tenant_id`/`sub`.
- `type=service` → internal S2S token minted by `mint_service_token`
  (auth.py:102); decodes to `TenantContext(tenant_id=NIL, user_id=NIL,
  is_service=True)` — it legitimately supplies identity via the wire body.

The intended bridge is `resolve_identity(wire_tenant_id, wire_user_id)`
(auth.py:161): for a **user** token the token identity wins and a differing wire
tenant is rejected (`permission_denied`); for a **service** token (or no
ContextVar, i.e. unit tests) it trusts the wire. **Only `trading` adopted it.**

### Concrete exploit
Attacker Mallory is a legitimate user of tenant **A** (valid access token
`T_A`, `tenant_id=A`). She calls any vulnerable RPC over HTTP/Connect:

```
POST /portfolio.v1.PortfolioService/GetPortfolioSummary
Authorization: Bearer <T_A>                      # valid -> middleware admits, ctx.tenant_id = A
Content-Type: application/json
{ "context": { "tenant_id": "<TENANT_B_UUID>", "user_id": "<any>" } }
```

The middleware admits the request (token is valid). The servicer executes
`tenant_id = UUID(request.context.tenant_id)` → **B**, and every downstream query
is filtered by **B**. Mallory reads tenant B's portfolio. The same body swap works
for writes: run a backtest billed to B, create/delete B's strategies, move B's
ledger capital, place orders on B's account. This is a **cross-tenant IDOR /
horizontal privilege escalation across the whole platform.** There is **no
Postgres RLS** as a backstop — the app-layer `WHERE tenant_id = :t` is the only
isolation boundary, and its `:t` is attacker-controlled.

### Blast radius — most dangerous RPCs (writes, in priority order)
- **portfolio ledger** (`ledger_servicer.py`): `DepositFunds`, `WithdrawFunds`,
  `AllocateCapital`, `TransferCapital`, `CloseSleeve` — move money/positions
  between another tenant's sleeves. **Highest impact.**
- **trading** (already SAFE): `SubmitOrder`, `CancelOrder`, `StartSession` —
  place/cancel real (paper) orders. Confirms the fix pattern works.
- **strategy**: `CreateStrategy`, `UpdateStrategy`, `ArchiveStrategy`,
  `StartExecution`/`StopExecution` — destroy or hijack another tenant's automation.
- **backtest**: `RunBacktest` — consume another tenant's compute/quota; read their
  strategy configs and results.
- **auth alpaca-credentials**: read/create/delete brokerage API keys (mitigated —
  these derive tenant from the token, see §2, but bespoke).
- **billing**: subscription/payment-method mutations (mitigated — token-derived).
- **portfolio reads / agent / notification**: cross-tenant data disclosure.

---

## 2. Current-state map

**Transports:** `connectrpc` (raises `ConnectError`): agent, auth, backtest,
billing, market-data, portfolio (both servicers), strategy. `grpc.aio` (aborts
with `grpc.StatusCode`): notification, trading.

**`AuthMiddleware` is installed on every service** (`services/*/src/main.py`).
Public-suffix exemptions (unauthenticated pass-through) — everything else only
exempts the default `/health`, `/metrics`, `/docs`, `/openapi.json`:
- `auth` (`main.py:65`): `/Login`, `/Register`, `/RefreshToken`.
- `strategy` (`main.py:65`): `/ListTemplates`, `/GetTemplate` (public templates).

### Classification legend
- **SAFE** — derives identity from the verified token via `resolve_identity`.
- **VULNERABLE** — trusts body `request.context.*` (user token can forge it).
- **MITIGATED** — derives tenant from its own JWT decode (not body), so not a body
  IDOR, but bespoke/duplicated and does not go through `resolve_identity`.
- **HEADER-TRUST** — trusts a forgeable `X-Tenant-ID` header.

### Per-service map

**trading** — `services/trading/src/grpc/servicer.py` — **SAFE (reference).**
Helper `_identity()` (`:43`) → `resolve_identity(request_context.tenant_id or
None, request_context.user_id or None)` (`:50`); `_abort_auth()` (`:56`) maps
`AuthError.code` → `grpc.StatusCode` via `_AUTH_CODE_TO_GRPC` (`:36`). ~15 call
sites, all through `_identity` (`:169,207,240,273,306,337,380,440,473,502,554,592,626,684,716`).

**strategy** — `services/strategy/src/grpc/servicer.py` — **VULNERABLE (15).**
Helper `_validate_tenant_context()` (`:43`) does shape-validation only — checks
non-empty / valid-UUID / non-nil on `context.tenant_id`/`context.user_id`
(`:56-57`) but **never** consults `current_context()`, so a forged body passes.
Call sites: `:113,150,212,263,312,403,458,505,557,616,671,697,743,778,808`.

**agent** — `services/agent/src/grpc/servicer.py` — **VULNERABLE (9). COORDINATE
BEFORE EDITING** (actively edited by the main thread). Identical
`_validate_tenant_context()` (`:59`, shape-only, `:72-73`). Call sites:
`:124,158,245,295,321,441,594,635,663`. (Outbound S2S auth in
`agent/src/tools/clients.py` + `strategy_client.py` was already fixed by another
engineer — out of scope; it now presents a service token + carries the real
tenant on the wire, which the fix must keep working.)

**backtest** — `services/backtest/src/grpc/servicer.py` — **VULNERABLE (7).**
Raw `UUID(request.context.tenant_id)` inline per RPC:
`:107,189,233,283,333,408,452` (`run_backtest`, `get_backtest`, `list_backtests`,
`cancel_backtest`, `get_backtest_progress`, plus the delete/compare paths). No
identity helper at all. (Also holds a syntax landmine at `:52` — see §7.)

**portfolio** — `services/portfolio/src/grpc/servicer.py` — **VULNERABLE (10).**
Raw `UUID(request.context.tenant_id)`: `:74,103,141,218,272,298,342,376,431,473`.

**portfolio ledger** — `services/portfolio/src/grpc/ledger_servicer.py` —
**VULNERABLE (9), HIGHEST-VALUE WRITES.** Raw `UUID(request.context.tenant_id)`:
`:124,178,197,222,271,301,339,363,403` (`GetOrCreateAccount`, `DepositFunds`,
`WithdrawFunds`, `AllocateCapital`, `TransferCapital`, `CloseSleeve`,
`ListSleeves`, `GetSleeve`, `GetHoldingHistory`).

**notification** — `services/notification/src/grpc/servicer.py` — **VULNERABLE
(8), grpc.aio, stub.** Raw string `request.context.tenant_id` /`.user_id`:
`:43-44,98-99,140-141,170-171,226-227,262-263,304-305,346-347`. In-memory stub
storage keyed `f"{tenant_id}:{user_id}"`; low data value today but same defect
class, and the only other grpc.aio service besides trading.

**market-data** — `services/market-data/src/grpc/servicer.py` — **HEADER-TRUST
(10), low-value.** `_extract_tenant_context()` (`:62`) reads `X-Tenant-ID` /
`X-User-ID` from **headers** (`:80,90`), used only for logging/rate-limiting
(`:202,267,329,382,417,454,507,588,646,701`). Bars/quotes/snapshots are shared
market data, not tenant-scoped, so the disclosure impact is low — but trusting a
forgeable header is a smell and should move to `current_context()` for
consistency and to feed rate-limiting a real principal.

**billing** — `services/billing/src/grpc/servicer.py` — **MITIGATED (13).**
`_get_tenant_id()` (`:58`) re-decodes the bearer JWT itself and reads
`payload["tenant_id"]` — token-derived, **not** a body IDOR. But it duplicates
`verify_credential` (own `jwt.decode`, own `JWT_SECRET`/`JWT_ALGORITHM` at
`:36-37`), ignores the middleware ContextVar, and would **break on a service
token** (no `tenant_id` in payload → "Token missing tenant_id"). Call sites all via
`_get_tenant_id` (`:89,112,151,176,201,248,354,397,443,464,493,516,530`).

**auth** — `services/auth/src/grpc/servicer.py` — **MIXED.**
- MITIGATED (bespoke, token-derived): `change_password` (`:497`),
  `get_current_user` (`:549-550`), `create/get/list/delete_alpaca_credentials`
  (`:682,731,781,824`) — each re-decodes the bearer JWT (7 near-identical
  `jwt.decode` blocks) instead of using `current_context()`. High value (Alpaca
  API keys) → worth unifying to kill copy-paste risk, even though not a body IDOR.
- **VULNERABLE — unscoped body lookups:** `get_user` (`:276`
  `UUID(request.user_id)`) and `get_tenant` (`:302` `UUID(request.tenant_id)`)
  fetch **any** user/tenant by id with **no** tenant scoping and no ownership
  check. Any authenticated caller can enumerate users/tenants (email, roles,
  tenant_id) across the platform. Primarily S2S today, but reachable by any user
  token behind the fail-closed edge.
- **check_permission** (`:611` `roles = list(request.context.roles)`) authorizes
  off **body-supplied roles** — a caller can claim `["admin"]` and get
  `allowed=True`. Advisory RPC, but any consumer treating it as authoritative
  inherits a privilege-escalation. Should read roles from `current_context()`.
- `validate_token` / `validate_a_p_i_key` verify supplied credentials — that IS
  their job; leave as-is.
- `login`/`register`/`refresh_token` are public (or self-authenticating) — leave.

### Legacy note
`libs/common/llamatrade_common/middleware.py` still ships `TenantMiddleware` /
`get_tenant_context` and an outbound `X-Tenant-ID` writer (`:175`). It is
superseded by `AuthMiddleware` and is not part of the inbound trust path;
flagged only so we do not accidentally re-introduce header-trust through it.

### Headline count
**~58 body-forgeable IDOR call sites across 6 services** (strategy 15, portfolio
19 across two servicers, agent 9, backtest 7, notification 8), **plus** auth's 2
unscoped body lookups + 1 body-roles authorization = a **7th** service with the
same defect class. Separately: market-data (10 header-trust, low value) and
billing + auth-creds (20 bespoke token-decode sites — safe from IDOR but
un-DRY and service-token-incompatible).

---

## 3. Docs reviewed (constraints honored)

- **`CLAUDE.md` → Multi-Tenancy:** JWT carries `tenant_id`; extract via
  `require_auth`; filter ALL queries by `tenant_id`; S2S propagate via
  `X-Tenant-ID`. Our fix operationalizes "extract via the verified context, not
  the body." Note the doc's `X-Tenant-ID` guidance predates the token-only
  `AuthMiddleware`; S2S identity now rides `request.context` under a service
  token, not a trusted header.
- **`.docs/planning/CONTRACTS.md` (LOCKED):** §5 "Identity threading" fixes
  `account_id`/`sleeve_id`/`client_order_id`; it does **not** govern transport
  auth. `resolve_identity` changes *how the tenant is trusted*, not any payload
  shape or idempotency key → **contract preserved.** The ledger being "always on"
  is likewise unaffected.
- **`.docs/planning/trading-hardening-plan.md`:** origin of `resolve_identity`
  and trading's `_identity`/`_abort_auth` — the template we generalize.
- **`.docs/planning/platform-gap-review-2026-07.md`:** already ranks
  forged-tenant as the #1 platform gap; this plan closes it.
- No Postgres RLS exists anywhere (confirmed — no `row security`/`SET app.` /
  session-GUC usage in `libs/db`).

---

## 4. Remediation options

### Option 1 — `resolve_identity` everywhere, via one shared per-transport helper *(RECOMMENDED)*
Replace every raw/shape-only extraction with a call that runs
`resolve_identity(request.context.tenant_id, request.context.user_id)` and maps
`AuthError` to the servicer's transport error. DRY it with **two** tiny shared
helpers (one per transport) rather than 58 hand-written blocks:

- **Connect helper** — add `resolve_identity_connect(request_context) ->
  tuple[UUID, UUID]` to `llamatrade_common` (new `connect.py`, exported from
  `__init__`). It calls `resolve_identity` and translates `AuthError.code` →
  `ConnectError(Code.*)`. `connectrpc` is a light, already-ubiquitous dep in
  these services; `auth.py` itself stays import-clean (the adapter lives in a
  sibling module, mirroring how the grpc interceptor lives in `llamatrade_proto`).
- **grpc helper** — trading already has `_identity` + `_abort_auth`; lift them
  into a shared `llamatrade_proto` (grpc-side) helper or just copy the 12-line
  pair into `notification` (only one other grpc service). Given it is a stub,
  copying is acceptable; promoting to a shared helper is the DRY choice.

Then, per servicer:
- strategy/agent: replace `_validate_tenant_context(request.context)` →
  `resolve_identity_connect(request.context)` (delete the shape-only helper).
- backtest/portfolio/portfolio-ledger: replace inline
  `UUID(request.context.tenant_id)` (+`user_id`) → helper call.
- notification: adopt the grpc `_identity`/`_abort_auth` pair.
- market-data: swap header extraction → `current_context()` (keep "auth optional"
  semantics only if we deliberately want anonymous market data; otherwise the
  fail-closed edge already guarantees a principal — prefer just reading it).
- billing + auth (creds/current-user/change-password): replace the bespoke
  `jwt.decode` blocks with `current_context()` (tenant/user/roles from the
  verified token). This also fixes billing's service-token incompatibility.
- auth `get_user`/`get_tenant`: add tenant scoping — reject when the requested
  id is outside the caller's tenant unless the caller is a service token
  (`current_context().is_service`). auth `check_permission`: read roles from
  `current_context()`, not the body.

*Effort:* M (mechanical, ~60 edited call sites + 2 helpers + tests).
*Risk:* Low-moderate — behavior-preserving for legitimate calls; the sharp edge
is the service-token wire path (see §6). *Blast radius:* touches every service
but each change is local and uniform. *Maintenance:* **improves** — one canonical
identity call, matches trading, easy to lint for.

### Option 2 — Derive identity purely from the token ContextVar for user calls
Servicers ignore `request.context` entirely for user tokens and read
`current_context().tenant_id/user_id`; keep a service-token branch that reads the
wire. This is effectively what `resolve_identity` already encapsulates — doing it
inline everywhere just re-implements `resolve_identity` per site (un-DRY) and
loses the explicit cross-tenant **rejection** (a forged body would be silently
ignored rather than 403'd, which is worse for detection/telemetry).
*Effort:* M. *Risk:* moderate (per-site divergence). *Recommendation:* fold its
good idea (token is authoritative) into Option 1 — which is exactly what
`resolve_identity` does — rather than adopt it standalone.

### Option 3 — Postgres RLS as defense-in-depth
Add `ENABLE ROW LEVEL SECURITY` + policies keyed on a per-request GUC
(`SET LOCAL app.tenant_id = :t`), set from the verified context at the start of
each DB session. With async SQLAlchemy this means a session/connection hook
(e.g. an `AsyncSession` `after_begin` / a dependency that issues `SET LOCAL`
before queries) and careful handling of the async connection pool so a GUC never
leaks across pooled connections (`SET LOCAL` scoped to the transaction is the
safe form). Feasible but non-trivial: needs a migration per tenant-scoped table,
a reliable "who am I" source (the same verified context), and an escape hatch for
service-token/cross-tenant admin paths and for the ledger writer.
*Effort:* L. *Risk:* moderate-high (pooling/GUC-leak, migration surface, breaks
if any query runs off-session). *Value:* real — it makes a forged/omitted app
filter non-exploitable. **But it must not be the *only* fix** (it doesn't cover
non-DB reads, and mis-set GUC = self-inflicted outage).

### Recommendation
**Option 1 now (app-layer `resolve_identity` everywhere via shared helpers),
Option 3 later as a tracked defense-in-depth follow-up.** Option 1 is the
minimal, uniform, already-proven (trading) closure of the live IDOR with the best
maintenance profile and directly satisfies the CLAUDE.md multi-tenancy mandate.
RLS is the right belt-and-suspenders but is a larger, riskier change that
shouldn't gate shipping the actual fix. Explicitly rejecting forged tenants
(403) rather than silently ignoring them (Option 2) gives us the audit signal to
detect abuse.

---

## 5. Test strategy

**Key fixture insight:** existing servicer unit tests build
`request.context = TenantContext(tenant_id=..., user_id=...)` but do **not** set
the ContextVar, so they exercise `resolve_identity`'s "no context → trust wire"
branch and keep passing. Real isolation tests must **set the ContextVar** to
simulate an authenticated principal (`libs/common/tests/test_auth.py:97-152` is
the template — `set_context(...)` / `reset_context(token)` in try/finally).

Per service (and one shared parametrized helper), add:
1. **Cross-tenant rejection (the core regression):** `set_context(user, tenant=A)`;
   invoke RPC with `request.context.tenant_id = B` → expect
   `PERMISSION_DENIED` (grpc) / `Code.PERMISSION_DENIED` (Connect). One per
   servicer at minimum; ideally parametrized over its mutating RPCs.
2. **Same-tenant happy path:** `set_context(user, tenant=A)` + wire `A` (or empty
   wire, since token wins) → succeeds, queries scoped to A.
3. **Service-token wire-trust:** `set_context(is_service=True, NIL)` + wire
   `tenant=B,user=U` → succeeds and resolves to B (protects the already-fixed
   agent S2S path). Include a nil-wire-under-service-token → `unauthenticated`.
4. **Forged roles (auth only):** `check_permission` with body `roles=["admin"]`
   but a non-admin token → not allowed.
5. **Unscoped-lookup guard (auth only):** `get_user`/`get_tenant` for an id in
   another tenant under a user token → denied; under a service token → allowed.

**Where fixtures live:** `libs/common/tests/test_auth.py` (resolve_identity unit
coverage — already green); per-service `tests/conftest.py` already provide
`valid_tenant_context` builders (e.g. `agent/tests/conftest.py:101`,
`backtest/tests/test_grpc_servicer.py`). Add a shared `set_authenticated_context`
context-manager fixture (thin wrapper over `set_context`) to `libs/common` test
utils so every service imports one helper. Target the CLAUDE.md 80% bar on the
new/edited identity code; each isolation test is cheap and high-signal.

**Migration-risk tests already covered by resolve_identity:** nil-UUID rejection,
bad-type wire, missing-wire — keep as-is in `test_auth.py`.

---

## 6. Rollout / migration

**Order (highest-value writes first):**
1. `libs/common` — add the Connect adapter + shared test helper; fix the auth.py
   syntax landmine (§7). Ship first so services can depend on it.
2. **portfolio ledger_servicer** (money movement) → **portfolio servicer** →
   **strategy** (destructive strategy/exec writes) → **backtest**.
3. **auth** (creds unification + `get_user`/`get_tenant` scoping +
   `check_permission` roles).
4. **billing** (token-derived → `current_context`; also fixes service-token break).
5. **notification** (grpc pair) and **market-data** (header → context) — lower
   value, do last.
6. **agent** — LAST and **only after coordinating with the main thread** (actively
   edited). The change is a one-line-per-callsite swap identical to strategy.

**Backward-compat / things that currently rely on wire identity:**
- **Service tokens are NIL**, so every legitimate S2S call *must* keep flowing
  through the wire-trust path — `resolve_identity` already does this for
  `is_service=True`. The fix must NOT force token==wire for service tokens.
- **S2S callers must populate BOTH `tenant_id` AND `user_id` in
  `request.context`.** `resolve_identity`'s service/no-context branch requires
  both non-nil (auth.py:192,199). **Audit the agent outbound request builders**
  (`agent/src/tools/*`) to confirm they set `user_id` on the wire context, not
  just tenant — otherwise service calls that previously "worked" via raw
  `UUID(...tenant_id)` (which never read user_id) will start failing. This is the
  single most likely breakage and must be checked before flipping strategy/backtest.
- **Existing unit tests that omit `user_id`** in the wire context (e.g.
  `backtest/tests/test_e2e_lifecycle.py:298,380` pass only `tenant_id`) run the
  no-context branch and will begin failing (`user_id` required). Update those
  fixtures to include a user_id as part of each service's PR.
- **market-data "auth optional"**: if we keep any anonymous path, it must be an
  explicit `public_suffix`, not header-trust. Decide per §4.
- **Do not touch** `agent/src/tools/clients.py` / `strategy_client.py` (already
  fixed outbound) — the inbound fix keeps them working because service tokens
  supply identity via the wire, which `resolve_identity` honors.

Each service PR is independently deployable (helpers are additive); no coordinated
big-bang cutover required.

---

## 7. Syntax landmines (flagged, fold-in recommended)

Both rely on **PEP 758** (unparenthesized `except A, B:` — legal only on **Python
3.14+**; confirmed: both files parse on 3.14.3, would `SyntaxError` on ≤3.13):
- `libs/common/llamatrade_common/auth.py:157` — `except ValueError, TypeError:`
- `services/backtest/src/grpc/servicer.py:52` — `except ArithmeticError, ValueError:`

They are **semantically correct on 3.14** (catch both types), so this is a
portability/tooling risk, not a live bug: any ≤3.13 interpreter, or a linter/type
checker/editor not yet 3.14-aware, chokes on import.

**DISCOVERY (2026-07-16):** the unparenthesized form is **enforced by the repo's
own `ruff format`** — root `pyproject.toml` sets `target-version = "py314"`
(matching `requires-python = ">=3.14"`), so `ruff format` *rewrites*
`except (A, B):` back to `except A, B:`. Parenthesizing therefore **fails
`ruff format --check`** in `ci-local.sh` — the approved "just add parens" fix
fights the toolchain and cannot be applied in isolation. The paren edit was
**reverted** to keep the pilot green (see §9, open item OD-1). The durable fix is
a toolchain decision (e.g. set ruff `target-version = "py313"` so the formatter
keeps parens and the code parses on ≤3.13), which reformats repo-wide and needs
explicit sign-off — it is **not** a two-line change.

---

## 8. Open decisions (need sign-off before implementation)

1. **Scope of the fix — app-layer now, RLS later?** Recommend **Option 1 now**
   (`resolve_identity` everywhere) and file RLS (Option 3) as a tracked
   defense-in-depth follow-up, not a blocker. Agree, or do you want RLS designed
   in the same pass?
2. **DRY mechanism — shared helper vs per-call?** Recommend a **shared
   `resolve_identity_connect` helper in `llamatrade_common`** (+ reuse trading's
   grpc pair) over 58 inline blocks. Accept adding a `connectrpc` import to a new
   `llamatrade_common.connect` module (auth.py stays clean)? Or keep the adapter
   in each service's `error_handler.py`?
3. **Syntax landmines — fold in?** Recommend **yes**, fix both
   `except (A, B):` in this PR series (trivial, in-scope files). Agree?
4. **Rollout ordering + auth/billing/market-data scope.** Recommend money-first
   ordering (§6) and including auth (`get_user`/`get_tenant` scoping +
   `check_permission` roles + creds unification), billing, and market-data
   (header→context) in scope. Or limit round 1 to the pure body-IDOR services
   (strategy/portfolio/backtest/notification/agent) and treat
   auth/billing/market-data as a fast-follow?

---

## 9. APPROVED PLAN + P0/PILOT DELIVERED (2026-07-16)

Approved decisions (override §4/§8 where noted): **(1) app-layer
`resolve_identity` everywhere AND Postgres RLS in the SAME pass**, RLS as its own
independently-testable phase; **(2)** shared `resolve_identity_connect` in
`llamatrade_common` + reuse trading's grpc `_identity`/`_abort_auth`; **(3)** fix
the two syntax landmines — *but see OD-1, this collides with `ruff format`*;
**(4)** full comprehensive pass (auth + billing + market-data included).

### 9.1 Two-layer model
1. **App layer (primary fix)** — every servicer resolves identity from the
   *verified* principal, not the wire body, and rejects a forged tenant with
   `PERMISSION_DENIED`.
2. **RLS (defense-in-depth)** — Postgres itself scopes every query to the tenant
   bound to the current transaction, so a *missing* app-layer filter still can't
   leak across tenants.

### 9.2 The shared helper API (P0)
- `llamatrade_common/connect.py` → `resolve_identity_connect(request_context) ->
  (UUID, UUID)`: calls transport-neutral `resolve_identity`, maps `AuthError` →
  `ConnectError(Code.*)`. Kept out of `__init__` (so `import llamatrade_common`
  stays connectrpc-free); servicers `from llamatrade_common.connect import ...`.
  `connect-python>=0.8.1` added to `libs/common` deps (was undeclared).
- grpc.aio services (trading, notification) keep trading's `_identity` /
  `_abort_auth` pair (grpc StatusCode mapping) — unchanged pattern.

### 9.3 Per-call-site swap pattern (connect servicers)
Before: `tenant_id = UUID(request.context.tenant_id)` inside a broad
`try/except Exception`. After: resolve **outside** any broad catch so
`PERMISSION_DENIED` isn't masked to `INTERNAL`, and open a tenant-scoped session:
```python
tenant_id, _user_id = resolve_identity_connect(request.context)
try:
    async with tenant_session(tenant_id, self._maker()) as db:
        ...
except ConnectError:      # let auth/NOT_FOUND codes through
    raise
except Exception as e:
    raise ConnectError(Code.INTERNAL, ...) from e
```
`self._maker()` returns the servicer's `async_sessionmaker` (tests inject the
test-DB factory via `servicer._session_factory = ...`, preserving the seam).

### 9.4 RLS wiring (P0)
- `llamatrade_db/rls.py` — canonical policy DDL. GUCs `app.current_tenant`
  (tenant) and `app.rls_bypass` (system). Policy per table (USING + WITH CHECK):
  `current_setting('app.rls_bypass',true)='on' OR tenant_id =
  NULLIF(current_setting('app.current_tenant',true),'')::uuid`. `NULLIF` →
  unset/blank GUC yields **zero** rows (fail-closed), never an invalid-uuid error.
  `ENABLE` + **`FORCE`** RLS (owner is subject too). `LEDGER_RLS_TABLES` = the 5
  `ledger_*` tables.
- `llamatrade_db/session.py` — `set_tenant_guc(session, tid)` /
  `set_rls_bypass(session)` via `set_config(..., is_local=>true)` (transaction-
  scoped, no pooled-connection leak); context managers `tenant_session(tid,
  maker=None)` and `system_session(maker=None)`. Exported from `__init__`.
- Migration `022_enable_rls_ledger_tables` — applies `rls.enable_rls_statements`
  to the 5 ledger tables; `downgrade` reverts. (Numbering: chains off `021`;
  **must be reconciled with the uncommitted demo-seed `022` on main** before
  merge — see OD-3.)
- **Non-superuser role is mandatory**: superusers bypass RLS regardless of FORCE.
  Production/app must connect as a plain role; the RLS test provisions one.

### 9.5 Two access modes — the key RLS design point
Portfolio has **legitimate cross-tenant background sweeps** (`equity_snapshot`,
`reconciliation` enumerate *all* accounts via `_load_accounts`). Fail-closed RLS
would return them zero rows. Resolution:
- **request / per-tenant paths** → `tenant_session(tenant_id)` (servicers; the
  fill handler `tenant_session(append.tenant_id)`; reconciliation adapters &
  drift handler `tenant_session(account.tenant_id)`; snapshot per-account persist).
- **trusted cross-tenant enumeration** → `system_session()` (snapshot pass load +
  projection; reconciliation loop `_load_accounts`). The bypass GUC is set **only**
  by server code, never from request input — equivalent to a BYPASSRLS role but
  keeps a single DB role. This is the pattern every service with background sweeps
  will reuse.

### 9.6 Pilot delivered — portfolio (fully green)
Edited: `services/portfolio/src/grpc/servicer.py` (10 RPCs),
`ledger_servicer.py` (9 RPCs), and 4 task files (`fill_ingestion`,
`equity_snapshot`, `reconciliation`, `drift_policy`) threaded onto
`tenant_session`/`system_session`. Tests:
- `libs/common/tests/test_connect.py` (6) — helper: user-match, forged→DENIED,
  service-trust, no-context, missing→UNAUTH, bad-uuid→INVALID_ARGUMENT.
- `libs/db/tests/test_rls.py` (4) — policy DDL builders (no DB).
- `services/portfolio/tests/test_servicer_auth.py` (3, no DB) — servicer forged
  tenant → `PERMISSION_DENIED` before any DB access; empty wire → UNAUTHENTICATED.
- `services/portfolio/tests/integration/test_rls.py` (3, real PG, non-superuser
  role) — reads scoped per-tenant on UN-filtered queries; **no GUC → 0 rows**;
  `system_session` → all; WITH-CHECK blocks cross-tenant insert; **service-token
  happy path end-to-end under RLS**.
- Results: `libs/common` 93 pass (88% cov); `libs/db` 232 pass; **portfolio 247
  pass** (unit + Docker integration); ruff check + `ruff format --check` clean on
  all changed files.

### 9.7 Migration-risk confirmed handled
`resolve_identity`'s service/no-context path needs BOTH wire `tenant_id` AND
`user_id`. Portfolio's integration `_tenant_ctx` already sets both, and the agent
outbound builders (`backtest_tools.py`/`portfolio_tools.py`) set both — verified
non-breaking. Existing app-layer isolation tests still pass (they run on the
create_all/no-RLS integration DB; the extra `set_config` is a harmless no-op there).

### 9.8 Updated open decisions (need sign-off before rollout)
- **OD-1 (syntax landmines):** the approved parenthesize-the-`except` fix
  **conflicts with `ruff format` (`target-version=py314`)** and fails
  `format --check`; reverted for now. Choose: **(a)** leave unparenthesized
  (repo is 3.14-only; accept the ≤3.13/older-tooling risk) — recommended, zero
  churn; or **(b)** set ruff `target-version="py313"` and reformat repo-wide so
  parens are kept and code parses on ≤3.13 (larger, toolchain-wide). Not a
  two-line change either way.
- **OD-2 (RLS rollout breadth):** RLS is proven on the ledger tables. Extend
  table-by-table to each service's tenant tables **as that service is migrated**
  (strategy, backtest, billing, auth, notification), each with its own
  `NNN_enable_rls_*` migration + a non-superuser-role integration test, and audit
  each service's background/cross-tenant paths for `system_session`. Confirm this
  incremental approach vs. one big RLS migration.
- **OD-3 (migration numbering):** `022_enable_rls_ledger_tables` chains off `021`
  in this worktree; memory notes an **uncommitted `022` (demo-seed) on main**.
  Reconcile before merge (rebase/rechain to `023`, or coordinate the head).
- **OD-4 (prod DB role):** RLS requires the app to connect as a **non-superuser,
  non-BYPASSRLS** role. Confirm the deploy/DATABASE_URL role is (or becomes) such
  a role, and that migrations/admin run under a role that can still manage schema.

---

## 10. FULL ROLLOUT COMPLETE (2026-07-16)

App-layer identity (IDOR closure) + RLS session-binding rolled out to **all
services**, and the platform-wide RLS migration written. All suites green.

### 10.1 Per-service outcome
| Service | Transport | Identity fix | Session binding | Suite |
|---|---|---|---|---|
| portfolio | connect | `resolve_identity_connect` (pilot) | `tenant_session` servicers + tasks (`system_session` for sweeps) | 247 ✓ (incl real-PG RLS) |
| strategy | connect | helper → `resolve_identity_connect` (15 sites, 1 fn) | `tenant_session`; `compile_strategy` (stateless) → `system_session` | 152 ✓ |
| backtest | **grpc.aio** | local `_identity`/`_abort_auth` + per-method `except AuthError` | `_get_db(tenant_id)` wraps `tenant_session` | 326 ✓ |
| notification | **grpc.aio** | local `_identity`/`_abort_auth` (stub, string keys stringified) | none (in-memory stub) | 99 ✓ |
| market-data | connect | `_extract_tenant_context` → `current_context()` (was `X-Tenant-ID` header) | none (shared market data, non-tenant store) | 55 ✓ |
| billing | connect | kept token-derived `_get_tenant_id` (already not body-IDOR) | `tenant_session`; `list_plans` (global) → `system_session` | 170 ✓ |
| auth | connect | **`get_user`/`get_tenant` cross-tenant scoping**; `check_permission` roles from `current_context()` | `_get_db` → `set_rls_bypass` (identity authority: pre-tenant/cross-tenant) | 40 ✓ |
| agent | connect | chokepoint helper → `resolve_identity_connect` (9 sites, 1 fn) | `tenant_session` servicers; `_extract_and_store_memories` + `memory_tools` bind the GUC | 196 ✓ |
| trading | **grpc.aio** | already SAFE (`_identity`/`resolve_identity`) | factories (`create_live_session_service`/`create_position_service`/`create_order_executor`) take `tenant_id` → `set_tenant_guc` | 561 ✓ (non-integration) |

libs: common 93 ✓, db 233 ✓.

### 10.2 Final RLS migration
- `rls.py` now exports **`RLS_TABLES`** — every tenant-scoped table (31), i.e. all
  33 `tenant_id` tables minus the deprecated `agent_memory_embeddings` /
  `agent_session_summaries`. `libs/db/tests/test_rls.py::test_rls_tables_match_tenant_scoped_metadata`
  fails on any drift (new tenant table without RLS coverage).
- **`025_enable_rls_all_tenant_tables`** (single migration, `down_revision =
  024_add_user_avatar_url` — main's current uncommitted tip) enables fail-closed
  RLS + FORCE on all `RLS_TABLES` via `rls.enable_rls_statements`. The pilot's
  `022_enable_rls_ledger_tables` was **removed** (folded in).
- Enforcement proven end-to-end by `services/portfolio/tests/integration/test_rls.py`
  (real Postgres, dedicated **non-superuser** role): no-GUC → 0 rows,
  tenant-scoped reads, `system_session` → all, WITH-CHECK blocks cross-tenant
  insert, service-token happy path. The policy is table-agnostic, so this proves
  the mechanism the `025` migration applies platform-wide.

### 10.3 DRY / design notes
- **grpc auth pair duplicated** in the 3 grpc services (trading pre-existing,
  backtest, notification): `llamatrade_common` stays grpc-free by design and
  `llamatrade_proto` deliberately avoids a hard `llamatrade_common` dep (lazy
  import), so neither is a clean host. Coordinator-sanctioned ("reuse trading's
  pair"). ~12 lines × 3.
- **Two session modes** used throughout: `tenant_session(tid)` for request/
  per-tenant paths; `system_session()` (RLS bypass) for trusted cross-tenant work
  — portfolio sweeps, `list_plans`/`compile_strategy` (global/stateless), and
  **auth** (identity authority, queries `users` pre-tenant).
- Test-injection updates (mock session factories) were needed where suites drive
  RPC bodies against a real-but-unused session (strategy, billing) so
  `tenant_session`'s `set_config` is a mocked no-op.
- **Migration-risk (`resolve_identity` needs wire `user_id` too)** fixed where it
  bit: backtest unit + e2e contexts and mock `_get_db` signatures.

### 10.4 Open items (before the RLS *cutover*, i.e. the DB-role switch — OD-4)
RLS is **inert until prod connects as a non-superuser role**, so these don't
block the app-layer IDOR closure (already effective) but must land before flipping
the role:
- **OD-5 — background/runner GUC threading.** Trading's **background runner**
  sessions (order executor invoked from runners, position-sync loops) and any
  other non-request background DB paths that touch tenant tables must set the GUC
  (via `tenant_session`/`system_session`) before the role switch, or they read 0
  rows. Request paths are done; these are not yet audited exhaustively.
- **OD-6 — agent merge.** The agent servicer session-wrapping was applied to all
  methods including `stream_message`/`send_message`, which the main thread is
  editing; reconcile at merge (chokepoint `_validate_tenant_context` won't
  collide; the `async with tenant_session(...)` lines may). `_extract_and_store_memories`
  was changed to open its own `tenant_session` (aligns with main's fresh-session
  direction).
- **OD-3 (updated) — migration chain.** `025` chains off `024_add_user_avatar_url`
  (main's uncommitted tip: 022 backtest-result-columns, 023 agent-msg-artifact-ids,
  024 user-avatar). Not present in this worktree — verify the down_revision is the
  real head at merge.
- **OD-1 (settled) — syntax landmines left unparenthesized** (`auth.py:157`,
  `backtest/servicer.py:52`), per approval; ruff `target-version=py314` enforces it.
