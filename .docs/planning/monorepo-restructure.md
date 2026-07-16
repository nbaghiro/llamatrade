# Monorepo restructure — collapse `/packages`, merge marketing into web

**Goal:** no root-level `/packages`. End state: `/apps/{web, mobile, core}` only, with the
Monolith design system absorbed into web and the marketing landing living inside web
(deployed separately from web's landing route).

**Decisions (locked):**
- Shared core keeps its name — `@llamatrade/core`, folder moves to `apps/core`. Zero import
  churn (npm resolves by package name; only the folder + 3 build paths move).
- Marketing stays a **separate static deploy**, but is **built from web's landing route**
  (a `build:landing` target) rather than a standalone `apps/marketing`. The landing is
  authored once in web and served two ways: embedded at logged-out `/`, and as a
  standalone static bundle for the marketing Render service.

---

## Current wiring (facts)

- `@llamatrade/core` (packages/core) — proto · net · stores · format · theme. Consumed by
  **web (6 files) + mobile (19 files)**. Not marketing, not ui.
- `@llamatrade/ui` (packages/ui) — Tailwind preset (`tailwind-preset.cjs`), CSS
  (`styles.css`, `themes/monolith.css`), and React components (Logo, Button, Card, Badge,
  Input, Label, Marquee, StrategyTree). Consumed by **web + marketing**.
- `apps/marketing` — Vite app, `base: "/m/"`, deps = only `@llamatrade/ui` + react.
  Deployed as its own Render static site (`llamatrade.ai`).
- Caddy (`infrastructure/docker/Caddyfile`, `:8800`) rewrites `/`→`/m/` and proxies `/m/*`
  to `marketing:8811`; everything else to `web:8802`. This split exists ONLY because
  marketing is a separate app.
- Hard-coded path refs to move: `apps/mobile/tsconfig.json` (`@llamatrade/core` alias),
  `libs/proto/buf.gen.core.yaml` (`out:`), `apps/web/tailwind.config.js` +
  `apps/web/Dockerfile` (packages/ui). Mobile Metro watches the workspace root (path-agnostic;
  resolves via the workspace symlink).

---

## Phase A — move `packages/core` → `apps/core`  (low risk, isolated)

1. `git mv packages/core apps/core`.
2. Root `package.json`: `workspaces` → keep `"apps/*"`, remove `"packages/*"` (only once
   packages/ui is also gone — until then keep both globs).
3. `apps/mobile/tsconfig.json`: paths `../../packages/core/...` → `../../apps/core/...`.
4. `libs/proto/buf.gen.core.yaml`: `out: ../../packages/core/src/proto` → `../../apps/core/src/proto`.
5. Grep for any other `packages/core` string (web tsconfig/vite, Dockerfiles) and repoint.
6. `npm install` (relinks the workspace symlink + lockfile), then `make proto` (regenerates
   into apps/core/src/proto).
7. **Gate:** web `tsc` + `vitest` (91), mobile `tsc`, verify a proto import resolves.
   Package name unchanged, so no `@llamatrade/core` import edits anywhere.

## Phase B — merge `apps/marketing` → `apps/web`  [DONE 2026-07-16, uncommitted]

Executed (all "marketing" wording, not "landing", per user):
- Moved `marketing/src/{sections,components,hooks,data}` + `marketing.css` + `MarketingPage.tsx`
  → `apps/web/src/marketing/` (the CSS was already `.marketing-root`-scoped from a prior fold-in).
- Router: `apps/web/src/App.tsx` `PublicHome` — logged-out `/` → `<MarketingPage/>`, signed-in
  `/` → dashboard. `MARKETING_URL` (auth-page logo link) collapsed to `/`.
- Standalone build for the separate marketing deploy: `apps/web/marketing.html` +
  `src/marketing/main.tsx` + `src/marketing/marketing-base.css` + `vite.marketing.config.ts`,
  script `build:marketing` → `dist-marketing/` (renames `marketing.html`→`index.html`). Gitignored.
- Killed the `/m/` split: Caddyfile collapsed to a thin `reverse_proxy web:8802`; removed the
  `marketing` service + `MARKETING_UPSTREAM` from both compose files. Deleted `apps/marketing`.
- Gate green: web tsc, `vite build`, `build:marketing`, 94 vitest. **Deploy TODO (not code):**
  repoint the marketing Render service to build `apps/web` with `npm run build:marketing`,
  publish `dist-marketing/`. **Local TODO:** `make dev` restart for the new Caddyfile/compose.

### Phase B — original plan (for reference)
Merge `apps/marketing` → `apps/web` (marketing page lives in web).

1. Move into `apps/web/src/marketing/`: `src/sections/*`, `src/components/*`
   (CursorAccent, GridOverlay, Marquees, WaitlistForm, CodeBlock, codeTokens),
   `src/hooks/*`, `src/data/editorLevels.ts`, `src/marketing.css`, `MarketingPage.tsx`.
2. Fonts/assets → dedup into `apps/web/public` (marketing embeds fonts as data-URIs to beat
   the CSP on the standalone build — keep that path for `build:landing`).
3. **App route:** web router `/` currently redirects to `/dashboard`. Change to: logged-out
   `/` → `<MarketingPage/>`; logged-in `/` → dashboard. Hash anchors (`#copilot`, …) keep working.
4. **Standalone landing build** (for the separate Render deploy):
   - `apps/web/landing.html` + `apps/web/src/marketing/main.tsx` (mounts only `<MarketingPage/>`,
     no app router/stores).
   - `apps/web/vite.landing.config.ts` (root = landing.html, `outDir: dist-landing`, `base: "/"`).
   - `package.json`: `"build:landing": "vite build --config vite.landing.config.ts"`.
   - Point the marketing Render service at `apps/web` with build `npm run build:landing`,
     publish `dist-landing/`. (No DNS change; `llamatrade.ai` still hits this service.)
5. **Delete the `/m/` split:** simplify the Caddyfile so `:8800` routes everything to
   `web:8802` (drop the marketing upstream + `/`→`/m/` rewrite). Local dev can also just hit
   web directly. Remove the `marketing` docker-compose service.
6. Retire `apps/marketing` (folder + its Dockerfile.dev, tailwind/postcss/vite configs).
7. **Gate:** web `tsc` + tests, `npm run build` (app) and `npm run build:landing` (landing)
   both succeed, visual pass on logged-out `/` (landing) and the app.

## Phase C — eliminate `@llamatrade/ui` (absorb into web)  [NOT STARTED]

After B, web is the only consumer.
1. `packages/ui/src/components/*` → **`apps/web/src/components/`** (the existing components
   folder — user directive, NOT a new `src/ui/`). Repoint `@llamatrade/ui` imports (web +
   the moved marketing page) to local relative paths. NOTE the name collision: web already
   has `src/components/common/Logo.tsx` (which wraps the ui `Logo`) — reconcile on absorb.
2. `tailwind-preset.cjs` → inline its tokens into `apps/web/tailwind.config.js`; drop the
   `packages/ui/src` content-scan glob (add `src/marketing`/`src/ui` globs).
3. `styles.css` + `themes/monolith.css` → `apps/web/src/`, imported by `index.css`.
4. `apps/web/Dockerfile`: drop `COPY packages/ui`.
5. Delete `packages/ui`; root `workspaces` → `["apps/*"]`; delete the now-empty `/packages`.
6. **Mobile untouched** — it never used `ui` (own token copy in core). Palette stays
   represented twice (web CSS vars ↔ core TS tokens), same as today; unifying is an optional
   follow-up (core could emit a generated CSS token file web imports).
7. **Gate:** web `tsc` + tests + both builds, `npm install` clean, visual pass.

---

## Sequencing, risk, rollback

- Order **A → B → C**. A is isolated; B brings all ui-consumers into web so C can localize ui.
- Do this as its **own commit/branch** — a folder-restructure diff should not be tangled with
  the in-flight mobile/app work (per CLAUDE.md "keep unrelated changes separate"). Ideally
  commit the current mobile work first.
- Biggest churn: lockfile (each folder move → `npm install`) and Vite/Tailwind config merges.
- Rollback is a `git revert` of the phase commit; no data/schema involved.
- **Not touched:** backend services, `libs/*`, mobile app behavior, DNS. `make proto` output
  path is the only proto change.
