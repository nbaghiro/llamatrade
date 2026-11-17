# Port brief: building the chosen designs into apps/web

You are porting chosen design options from the scratchpad explorations into the real web app at `/Users/naib/Documents/code/llamatrade/apps/web` (React 18, TypeScript, Vite, Tailwind with semantic tokens in `src/styles/tokens.css` and `src/styles/ui-layer.css`, Zustand stores, Connect RPC clients in `src/services`).

## Read first
- `/Users/naib/Documents/code/llamatrade/CLAUDE.md` and follow it: strict TypeScript with no `any` or `never` casts, tests for real logic, minimal comments, no commits, no worktrees.
- `/Users/naib/Documents/code/llamatrade/.scratchpad/app-explore/build-plan.md`: the option to build for every surface, with the rules for reading it. Your scope is the areas named in your task.
- The mockups themselves: each option lives in `.scratchpad/app-explore/area-<area>.html` or `area-<area>-2.html` (find `data-surface="..."`, then `data-opt="X"`). You can also see them full screen in `.scratchpad/app-explore/app.html#<surface>:<opt>`. Match layout, hierarchy, copy and states closely; the mockups are the spec.
- `/Users/naib/.claude/writing-voice.md` for every user-facing string: no em dashes, plain, precise.
- The existing code for your area before changing it: keep what works (data loading, stores, RPC calls), replace the presentation.

## Design system
Use and extend the existing tokens and `components/ui`, `components/charts`. Primary buttons are ink (`.btn-primary`), accent is for charts, art and highlights, amber only for attention. `PageArt` gives pages the bright chart art. Light and dark must both work. Numbers in mono via the existing `Num` component.

## Shared pieces
The foundation agent builds the shell and shared components first (listed in `.scratchpad/app-explore/port-foundation.md` once it's done). Read that file and use those components; don't fork them. If you need a change to a shared component, make it backwards compatible and mention it in your report.

## Data
Use only data the API provides. Where a design needs data that doesn't exist, build the honest fallback the option's note describes or leave that part out, never invented figures. Don't add backend endpoints or change protos.

## Checks before you finish
In `apps/web`: `npx tsc --noEmit`, `npm run lint`, `npx prettier --check "src/**/*.{ts,tsx,css}"` (fix with `--write` on your files only), `npx vitest run`. All must pass; don't break other areas' tests, and update tests that assert old copy or layout. The local stack is running: the app is at http://localhost:8800 (Vite with hot reload in Docker), demo login `demo@llamatrade.ai` / `demo1234` (a local test account). Look at every page you changed in headless Chrome (playwright-core at `/Users/naib/.npm/_npx/9833c18b2d85bc59/node_modules/playwright-core/index.mjs`, `chromium.launch({channel:'chrome'})`) at 1440 and 390 wide, light and dark (theme lives in localStorage `llamatrade-theme`), and fix what looks wrong next to the mockup. Keep screenshots in `/private/tmp/claude-501/-Users-naib-Documents-code/d0db8b41-ca1b-4be0-8c78-20704eb58cf7/scratchpad/port/`, not in the repo.

Other agents are editing other areas of the same working tree at the same time. Only edit files in your scope plus additive changes to shared files; never revert or reformat files you didn't change. If a check fails in a file outside your scope, report it rather than fixing it.

## Report (under 200 words)
What you built per surface, what you left out and why, data gaps, shared components you changed, and the check results.
