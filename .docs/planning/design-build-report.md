# Design build report

This covers the build of the chosen B Session design into the web app (`apps/web`): the
marketing site in Light and Dark, the theme system, and the recommended option of every
product surface from the choose pages in `.docs/.scratchpad/design-languages/`. The native app in
`apps/mobile` isn't part of it.

Nothing is committed yet. The changes sit in the working tree alongside other uncommitted
work.

## What was built

**Theme system**

- `src/styles/tokens.css` holds every colour as RGB channels, so Tailwind's `/alpha`
  modifiers keep working. It defines Dark (Slate, Black) and Light (Warm, White), with 12
  accents per mode, listed once in `src/theme/accents.ts`.
- The Tailwind preset uses semantic keys (`bg-canvas`, `text-fg-2`, `bg-accent-fill`,
  `bg-risk-soft`, `chart-1` to `chart-5`). The old keys (`ink`, `bone`, `paper`, `orange` and
  the rest) are temporary aliases onto the new tokens.
- `src/store/theme.ts` stores mode (default: follow the system), surface and accent per mode
  under `llamatrade-theme`. `public/theme-init.js` applies them before first paint, and a test
  checks that it agrees with the store.
- Appearance lives in Settings (`/settings/appearance`) and in the account menu. It's saved
  per browser, because there's no server-side preference yet.
- Geist and Geist Mono, the Candlesticks logo and a favicon that works on light and dark tabs.

**App shell**

- A top bar with the six destinations, ⌘K search, a market-status chip, notifications, the
  Paper pill and an account menu. Below 768px a five-tab bar replaces the nav.
- The command palette finds strategies, pages and actions, with Ask Copilot last.
- A skip-to-content link, and attention items (frozen, rejected, failed) in amber.

**Shared kit**

`components/ui` (skeletons, errors, empty states, figures, status marks, weight bars, tabs
and segmented controls, dialogs, sheets, popovers, menus) and `components/charts` (line,
sparkline, drawdown band, monthly grid), with the maths in `src/lib/chart`. Illustrative
data is seeded and always labelled as illustrative or as an example.

**Areas**

- Marketing site (`/` logged out and `build:marketing`), the same content in Light and Dark.
- Sign in, onboarding, Connect Alpaca and Home.
- Account: settings, broker, notifications, plan and usage, appearance, offline states.
- Strategies, templates, detail, the builder outline and code, versions.
- Backtests (setup, run, results, history, compare) and paper sessions (list, session,
  order check).
- Portfolio (overview, sleeve, activity, add funds) and Copilot.

## Fixes from QA worth knowing about

QA found and fixed several real bugs, not just layout problems:

- **Lookback data loss.** A filter's exact `:lookback` was rounded to a period bucket when
  parsed, so saving any edit rewrote it (90 became 126). `FilterConfig` now keeps
  `lookbackDays` and writes it back.
- **Momentum parsed as SMA.** `(momentum SYMBOL N)` was read as an SMA and saved as one. It's
  now a real indicator. Donchian has the same class of bug and is still open (below).
- **Funding race.** Two concurrent loads asked the funding store for the paper account, and
  the second got nothing, so a frozen session could look healthy. `resolveAccount` now shares
  one in-flight promise.
- **Add a card never worked.** It used a checkout session with an empty plan id. It now uses
  `CreateSetupIntent`. Stripe loads only when `VITE_STRIPE_PUBLISHABLE_KEY` is set.
- **Empty drafts saved a placeholder strategy.** Save is now disabled until there's a rule.
- **Deploy from the Session tab** passed version 0. It now passes the saved version.

## Checks

Run after the final fixes, on the host:

- `apps/web`: `tsc --noEmit`, lint (max-warnings 0), `format:check`, `vitest run` (63 files,
  945 tests), `build` and `build:marketing` all pass. The build keeps Vite's usual warning
  that the main chunk is over 500 kB.
- `apps/core`: `tsc --noEmit` passes.
- `./scripts/ci-local.sh` (lint and tests for every service, lib and the frontend): all
  checks pass.

QA ran each area in headless Chrome at 1440 and 390 px, across the four surfaces and two
accents. Signed-in pages were checked against mocked API responses, because Docker couldn't
start while the disk was full. Nothing here has been checked against the seeded backend yet.

## Data gaps and fallbacks

These parts of the design need data the API doesn't provide. Each screen shows an honest
fallback instead of inventing it.

- **"Would hold today" and the next rebalance's trades** need an evaluation RPC in
  `strategy.proto`. The strategy rail shows the rules as written; preview sentences are
  omitted.
- **Target weights and drift** aren't in the portfolio or ledger responses. Targets are
  computed client-side only when the DSL fixes them (`fixedTargets` in
  `apps/core/src/agent/structure.ts`); otherwise no ticks are drawn.
- **Reconciliation** has no RPC and no broker-side counts, so the panel shows ledger counts
  and says Alpaca's aren't available. No history.
- **Deploy dry run and the seven per-order risk checks** need a dry-run endpoint and
  per-check results on `Order`. The order check marks only the check that stopped it.
- **Session states** like "waiting for data", and a reason field, aren't exposed.
- **Broker check times** have no endpoint; the page offers "Check now" from the browser.
- **Default card** can't be changed: `AddPaymentMethod` ignores `set_as_default`. Needs a
  `SetDefaultPaymentMethod` RPC.
- **Copilot history during an outage** is served by the same agent service as the model.
- **Onboarding progress** has no API; dismissals are kept per browser.
- **Marketing**: the ticker tape uses invented prices (see `marketing-ticker-data.md`). The
  invite form joins the auth service's waitlist (`JoinWaitlist`); the standalone build keeps it
  closed until `VITE_AUTH_URL` is set.

## Open items

- **Donchian operands** still parse as an SMA placeholder in
  `apps/core/src/strategy/serializer.ts`, so they're rewritten on save. A proper fix needs an
  output field (upper, lower, middle) on `IndicatorRef`.
- **Accent close to amber.** Dark Orange and Light Rust are near the amber used for attention
  states, so a primary button can read as a warning. Consider dropping or shifting them.
- **Phone headers.** Phones keep the global top bar; the design's phone frames show a per-page
  title. That needs a mobile header per page.
- **Figure labels** (`.kicker`) render in mono, and uppercase in Light, where the strategy
  designs use 12px sans. A design-system call.
- **Home "today" figure** reads "+$x since <date>" from snapshots, where the design shows the
  day's P&L. The store already loads `dayPnl`, so this could switch over.
- **Reconciliation with no sleeves** says "Not available" rather than "No sleeves yet",
  because the ledger read returns `[]` both on failure and when empty.
- **Mobile app typecheck** has three errors from before this work: the `Strategy` type has no
  `timeframe` or `compiledJson` (`apps/mobile/app/(tabs)/strategies.tsx`,
  `app/strategy/[id].tsx`).
- **Film strip arrows** on the marketing site are an addition to the design, kept so keyboard
  and pointer users can move through the strip.
- An MIT `LICENSE` was added at the repo root, matching the README, so the site's "open
  source" wording is accurate.

## Running it locally

- App: `npm run dev --workspace=apps/web` serves on http://localhost:8802. Signed-in pages
  need the backend: `make dev-up`, then `make seed-demo` for realistic data.
- Marketing only: `npm run build:marketing` in `apps/web`, then `npx vite preview` with the
  marketing config on 8803.

## Next steps

1. A QA pass against the seeded backend, now that Docker can run, to check real figures,
   frozen sleeves, rejected orders and Copilot.
2. Backend RPCs in the order the screens benefit most: strategy evaluation, target weights,
   reconciliation, deploy dry run.
3. Remove the legacy Tailwind aliases once no page uses them.
