# Core extraction plan — everything sharable through `@llamatrade/core`

**Objective:** every feature that web and mobile can share lives in `apps/core`
(`@llamatrade/core`). The apps keep only platform UI (React DOM / React Native),
platform bindings (persistence adapters, navigation, Tailwind class strings), and
the one-line `configure()` call site. No duplicated stores, view-models, DSL
tooling, or proto-parsing helpers across the two apps.

**Guardrail (unchanged):** core imports only `@connectrpc/connect`,
`@bufbuild/protobuf`, `zustand`, `immer`, `uuid` — NEVER React DOM, RN native
modules (`expo-*`), `window`/`document`/DOM, `localStorage`, `import.meta.env`,
`@tanstack/react-query`, Tailwind, or `Intl` (core hand-rolls formatting for
iOS/Android Hermes parity — keep that policy). Anything platform-specific is
**injected** through `configure()`.

Audit basis: two full store-by-store audits (web `apps/web/src/store/*` + shared
services; mobile `apps/mobile/src/stores/*` + inline mappers), 2026-07-16.

---

## 1. Current core surface + the ONE new injection

Core today: `net/` (`configure` + lazy clients + `getTenantContext`), `format.ts`,
`theme/tokens.ts` (incl. `strategyColors`), `proto/*` (single generated copy), and
`stores/strategies.ts` (the reference extraction — clients + `getTenantContext`
from `../net`, zero platform deps).

`configure()` already injects `getToken`, `getTenantContext`, `onUnauthenticated`,
`refreshTokens`, `fetch`, `extraInterceptors`. **Everything platform-specific is
already injectable EXCEPT persistence.**

### New injection: a storage adapter (the only new plumbing)
Add `storage?: StateStorage` (zustand's `StateStorage`) to `ConfigureOptions`.
Core keeps `let _storage: StateStorage | undefined`; export `getStorage()`.
Persisted core stores use `persist(..., { storage: createJSONStorage(() => getStorage() ?? noopStorage) })`.
- Mobile passes `storage: secureStorage` (the existing `expo-secure-store` adapter).
- Web passes `storage: window.localStorage` (or omit → localStorage default).
- Keep the `hasHydrated` / `onRehydrateStorage` async-rehydration pattern in the
  core auth store (SecureStore is async; screens gate routing on it).
- `configure()` must run before any persisted store rehydrates — both apps already
  call it once at startup (`src/net/clients.ts` side-effect import).

---

## 2. Target core layout

```
apps/core/src/
├── index.ts
├── format.ts            (+ fmtCompact, timeAgo — net-new, hand-rolled)
├── errors.ts            NEW — errorMessage(), transformError()/AppError, isConnectivityError()
├── theme/tokens.ts      (strategyColors already here; web repoints to it)
├── net/                 (+ storage injection in configure; + getStorage())
├── proto/*              (single generated copy — done)
├── strategy/            NEW — the DSL + block-tree stack (zero platform deps)
│   ├── types.ts         ← web types/strategy-builder.ts (block model + guards)
│   ├── serializer.ts    ← web services/strategy-serializer.ts (toDSL/fromDSL/tokenizer)
│   ├── validator.ts     ← web services/validation/* (tree validation rules)
│   └── row.ts           ← web strategyRow.ts DERIVATIONS (buildRow/pillFor/positionAllocations)
├── agent/
│   └── artifact.ts      ← web PendingArtifactCard helpers (parsePreview/formatDSL/buildMeta)
├── chart.ts             NEW ← web dashboard/chart.ts (CurvePoint, sliceByPeriod, buildPath, boundsOf)
└── stores/              (add all shared stores below)
    ├── strategies.ts    (done — dedupe its local decimalToNumber → format.num)
    ├── auth.ts          (factory + injected storage)
    ├── agent.ts         (stream reducer + proto msgs + ChatMessage selector)
    ├── billing.ts       ├ portfolio.ts ├ dashboard.ts ├ activity.ts
    ├── backtest.ts      ├ trading.ts   ├ markets.ts   ├ funding.ts
    ├── deploy.ts        └ strategy-builder.ts (factory + storage + nav adapters)
```

Add exports to `package.json`: `./errors`, `./strategy/*`, `./agent/*`, `./chart`
(`./stores/*` and `./proto/*` already wildcard).

---

## 3. Cross-cutting dedup (do FIRST — unblocks clean moves)

These primitives already exist in core but are re-implemented across both apps.
Collapse every copy to the core version; this shrinks the diff of every later move.

| Duplicated thing | Copies | Canonical |
|---|---|---|
| `Decimal → number` (`toNumber`/`decimalToNumber`/`toNum`) | ~7 (web activity/markets/dashboard/portfolio/backtest/funding + core strategies) | `format.num` |
| `Timestamp → Date/ms/ISO` | ~6 (web activity/markets/dashboard/portfolio/backtest) | `format.toDate` / `format.toMs` |
| money/`%` via `Intl` | web activity/backtest/strategyRow + dashboard/format.ts | `format.money`/`moneyShort`/`signedMoney`/`pct` |
| `strategyColors` palette (6 hex, hard-coded) | 3 (web portfolio.ts, dashboard.ts, strategyRow.ts) | `theme.strategyColors` |
| `ConnectError → message` | ~5 inline (web trading/backtest + 3 mobile stores) + core strategies | new `errors.errorMessage` |
| connectivity / `serviceUnavailable` (`message.includes('fetch')`) | web agent + mobile agent | new `errors.isConnectivityError` |
| `isTokenExpired` (JWT exp via atob) | verbatim web `auth.ts` == mobile `auth.ts` | core (with the auth store) |
| Net-new to add to core `format.ts` | `fmtCompact`, `timeAgo` (from web dashboard/format) | hand-rolled (no Intl) |

---

## 4. Store-by-store plan

### 4a. Fully movable — import-swap only (`../services/grpc-client`|`../net/clients` → `@llamatrade/core/net`; `getTenantContext` from core net)
- **billing** — web (full: plans/sub/create/update/cancel/resume + usage) & mobile (read subset). → one core store; see decision D1 (usage source).
- **portfolio** — web (rich) & mobile (simple Σ-curve). → core; see decision D2.
- **backtest** — web only. Swap `formatCurrency`→`money`, error-map→`errors`.
- **dashboard** — web only. Co-move `chart.ts` (`CurvePoint`) + reconcile formatters; use `strategyColors`.
- **activity** — web only. Swap `fmtUsd`→`money`, converters→core.
- **trading** — web only. Reuse `errors.errorMessage`.
- **markets** — web only. Converters→core.
- **funding** — web only. Converters→core.
- **deploy** — web only. Pure (reads funding store).

### 4b. Movable with injection
- **auth** → `createAuthStore({ storage })` factory in core. Move `isTokenExpired` +
  `getTenantContext` accessor. Mobile injects `secureStorage` + keeps `hasHydrated`;
  web injects `localStorage`. Reconcile method names (`setSession/updateTokens` vs
  `login/setTokens` → unify) and the `roles`-in-tenant-context divergence (core
  `TenantCtx.roles` already optional — widen the user shape, keep roles optional).
  The app still passes its `auth`-backed `getToken/getTenantContext/refreshTokens`
  into `configure()`.
- **agent** (Copilot) → core store owning the **stream reducer**
  (`CONTENT_DELTA/TOOL_CALL_*/ARTIFACT_CREATED/TOOL_CONFIRMATION_REQUIRED/ERROR/COMPLETE`),
  the `createSession`-on-first-message flow, artifacts, suggested prompts. Expose BOTH
  proto `AgentMessage[]` (source of truth) AND a derived `ChatMessage` selector
  (decision D3). Streaming `fetch` already injected; drop the no-op `persist` (web
  partializes `{}`) or make it storage-injected. Web keeps its extras
  (`deleteSession`, `confirmToolCall`/`pendingConfirmation`, `seedPrompt`, panel state)
  — move the shared core, keep web-only panel UI state app-side.
- **strategy-builder** (~1610 lines, largest) → move the neutral core: tree model,
  undo/redo, DSL round-trip (uses the moved `strategy/serializer`+`validator`),
  autosave debounce, and the save/load actions (`getStrategy/getTemplate/updateStrategy/createStrategy`,
  `agentClient.getArtifact`). Inject: (a) a **persistence adapter** for the two
  `localStorage` key-stores (view-mode + collapsed blocks); (b) a **navigation
  callback** to replace `window.location.href` / `window.history.replaceState`. The
  zustand `createStore` factory is neutral and moves; the **React-context
  provider** (`StrategyBuilderStoreContext`, `useStore`) stays per-app (web keeps its
  provider; mobile writes its own thin binding if/when it builds an editor).

### 4c. Stays per-app (do NOT move)
- web `theme.ts` (DOM `document.classList`, superseded by core `theme/tokens`),
  `ui.ts` (transient web-dialog visibility), the Tailwind half of `strategyRow`
  (`pillClass`/`PILL_CLASS`).
- mobile `src/net/secure-storage.ts` (the injected adapter), `src/net/clients.ts`+`config.ts`
  (the `configure()` call site w/ `expo/fetch`), `src/spike/*` (dev harness), and
  everything under `src/ui`/`src/charts`/`src/copilot/*.tsx`/`src/auth/ui.tsx`/`app/**`
  (RN components). Web's `services/grpc-client.ts` stays as its `configure()` site.

---

## 5. Reconciliation decisions (recommended)

- **D1 — Billing usage source.** Mobile uses one `billingClient.getUsage`; web derives
  counts from 4 product RPCs (predates GetUsage). **Recommend: GetUsage as canonical**
  (server-computed, single RPC — the servicer already returns the same counts). Web
  switches its usage meters to `getUsage`; drop the 4-RPC derivation.
- **D2 — Portfolio vs dashboard.** **Recommend:** core owns `portfolio` (web's richer
  derivations: per-period returns, positions, account KPIs) + `dashboard` (composition:
  KPIs, blended curves, market clock) + `activity`, with **one shared `buildPortfolioCurve`**
  (dedupe web portfolio↔dashboard copies). Mobile's folded Home+Portfolio screens
  consume the shared stores' subset; retire mobile's bespoke Σ-curve.
- **D3 — Agent message shape.** **Recommend:** core store holds proto `AgentMessage[]`
  as source of truth + exports a `toChatMessages()` selector (the mobile VM). Web keeps
  proto access; mobile uses the selector. Shared stream reducer feeds both.

---

## 6. Execution phases (each phase: gate on web `tsc` + vitest, mobile `tsc`, both web builds; commit as its own unit)

- **Phase 0 — dedup + pure logic (no injection, highest ROI).**
  Add `core/errors.ts`, extend `format.ts` (`fmtCompact`/`timeAgo`), collapse the §3
  duplication (num/toDate/money/strategyColors/error/connectivity) in-place across both
  apps and the shipped `strategies` store. Move the DSL stack →
  `core/strategy/{types,serializer,validator}`, `core/strategy/row.ts` (derivations
  only), `core/agent/artifact.ts`, `core/chart.ts`. Repoint web imports; mobile gains
  the DSL tooling it lacks. Add the new export subpaths.
- **Phase 1 — import-swap client stores (§4a).** Move billing, portfolio, backtest,
  dashboard, activity, trading, markets, funding, deploy → `core/stores/*`; repoint both
  apps. Apply D1/D2 while moving billing + portfolio/dashboard/activity.
- **Phase 2 — storage adapter + auth.** Add `storage` to `configure()` + `getStorage()`;
  move `auth` as `createAuthStore({storage})`; wire mobile `secureStorage` / web
  `localStorage`; unify method names + tenant-context `roles`.
- **Phase 3 — agent store.** Move the reducer + proto msgs + `toChatMessages` selector
  (D3); keep web panel UI state + mobile `ChatMessage` consumption app-side.
- **Phase 4 — strategy-builder.** Move the neutral core store + `createStore` factory;
  inject persistence + navigation adapters; keep the React-context provider in web.

**Rollback:** each phase is a `git revert` of its commit; no schema/data involved.
Proto/`make proto` untouched. The only new runtime surface is the storage injection.

---

## 7. End state

`apps/core` holds: proto, net (+storage), format, errors, theme, the strategy DSL
stack (types/serializer/validator/row), agent artifact helpers, chart geometry, and
**every shared store** (strategies, auth, agent, billing, portfolio, dashboard,
activity, backtest, trading, markets, funding, deploy, strategy-builder). Each app
keeps only its UI, its `configure()` site + injected adapters (storage/nav/fetch),
and genuinely platform-specific view state (`theme`/`ui` dialogs on web; RN screens
on mobile). No sharable feature is implemented twice.
