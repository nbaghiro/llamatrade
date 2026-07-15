# @llamatrade/ui

The LlamaTrade **"Monolith"** design system — a brutalist / Swiss-grid, light-only
theme (bone / ink / signal-orange, Anton · Archivo · Space Mono). This package is
the single source of truth for the design tokens, the shared CSS layer, and the
presentational React components.

It is a **private workspace package** that **ships source** (raw `.ts`/`.tsx`/`.css`
— no build step). Consuming Vite apps import the source directly and compile it in
their own pipeline. React is a **peer dependency** (not bundled).

---

## What it exports

`package.json` `exports` map (three entry points):

| Import specifier                     | Resolves to                 | What it is                                              |
| ------------------------------------ | --------------------------- | ------------------------------------------------------- |
| `@llamatrade/ui`                     | `./src/index.ts`            | Barrel of React components + their types                |
| `@llamatrade/ui/themes/monolith.css` | `./src/themes/monolith.css` | The **theme token layer** — CSS custom properties (single source of truth) |
| `@llamatrade/ui/styles.css`          | `./src/styles.css`          | Shared `@layer base/components/utilities` (uses `@apply`)|
| `@llamatrade/ui/tailwind-preset`     | `./tailwind-preset.cjs`     | Tailwind preset that maps theme keys onto the tokens    |

### Components (from `@llamatrade/ui`)

All components are **presentational and prop-driven** — no app state, no data
fetching, no routing.

- **`Logo`** — brand mark (ink box, orange frame, LT monogram). Props: `size`, `showText`.
- **Primitives** (thin wrappers over the shared `.btn*`/`.card`/`.badge*`/`.input`/`.label` classes):
  - `Button` — `variant` (`primary`|`secondary`|`ghost`|`danger`), `size` (`sm`|`md`|`lg`), plus all `<button>` props.
  - `Card` — `shadow?: boolean`, plus `<div>` props.
  - `Badge` — `variant` (`primary`|`accent`|`gray`|`success`|`danger`), plus `<span>` props.
  - `Input` — `error?: boolean`, plus `<input>` props.
  - `Label` — `<label>` props.
- **`StrategyTree`** — the Monolith block/tree renderer (the "strategy builds itself"
  node tree). Props: `node: TreeNode`, `visibleCount?: number` (reveal the first N
  pre-order blocks for a build animation; omit to render fully composed), `className?`.
  Meant to sit on an **ink (dark) ground**. Ships a `prepareTree(raw)` helper that
  assigns pre-order reveal indices and returns `{ tree, count }`. Exported types:
  `TreeNode`, `RawNode`, `BlockKind`, `StrategyTreeProps`.
- **`Marquee`** — a prop-driven ticker. Props: `items: string[]`, `speed?` (seconds
  per loop, default 28), `separator?`, `className?` (outer clip), `trackClassName?`
  (color/opacity). Respects `prefers-reduced-motion`.

> The app's **stateful** strategy-builder (Zustand store, DSL services, editor panels)
> stays in `apps/web` — only the presentational design-system pieces live here.

---

## Theming

The design system is driven by a **CSS custom-property token layer** so the whole
product is trivially reskinnable — a new theme is one file.

### How the token layer works

`src/themes/monolith.css` is the **single source of truth**. It declares every
themeable value as a CSS variable under **both** `:root` and
`[data-theme="monolith"]` (identical values), so:

- `:root` makes the theme work the instant the file is imported (no attribute needed);
- `[data-theme="monolith"]` lets an app switch themes later by toggling the attribute.

Three consumers read from those variables — **nothing else holds a raw color/px**:

1. **`tailwind-preset.cjs`** maps Tailwind's theme keys onto the tokens:
   - Colors → `rgb(var(--lt-<name>) / <alpha-value>)`. This is the **required**
     Tailwind-with-CSS-vars form: the `<alpha-value>` slot is what preserves opacity
     modifiers (`bg-ink/50` → `rgb(var(--lt-ink) / 0.5)`). **Because of it, colors in
     the theme file are stored as space-separated RGB channels** (`--lt-orange-500: 255 77 28;`),
     never as `#ff4d1c` or `rgb(255,77,28)` — a hex/`rgb()` value in that slot would break the modifier.
   - `fontFamily.*` → `var(--lt-font-*)`, `borderRadius.*` → `var(--lt-radius)`,
     `boxShadow.*` → `var(--lt-shadow-*)`, `borderColor.DEFAULT` →
     `rgb(var(--lt-ink) / <alpha-value>)`.
   - The `fontSize` and `borderWidth` scales are intentionally **not** tokenized
     (structural, not theme-swappable).
2. **`styles.css`** references the tokens directly in its raw-CSS spots
   (`::selection`, scrollbars, autofill, the dotted-grid, the hard-offset `.btn*`/`.dropdown`
   shadows, `.nav-link-active`).
3. **Shared components** (`StrategyTree`) use token-backed classes
   (`bg-block-else`, `bg-block-weight`, `shadow-block`) and `currentColor`.

### Tweaking Monolith

- **Change one role fast** — edit the **semantic aliases** at the top of the theme
  file (`--lt-accent`, `--lt-surface`, `--lt-text`, `--lt-success`, `--lt-danger`,
  `--lt-info`). Each points into a ramp.
- **Change the accent hue everywhere** — edit the one line `--lt-orange-500`
  (the accent's source ramp step); every button, badge, ring, selection, and the
  StrategyTree reskin at once.
- **Deep customization** — override individual ramp steps (`--lt-blue-700`, …),
  the font stacks, radius, or the shadow offsets.

### Adding a NEW theme

Two equivalent routes — copy `src/themes/monolith.css` to
`src/themes/<name>.css`, add an `exports` entry for it, and give the tokens new
values. Then either:

- **Swap it in** — import `@llamatrade/ui/themes/<name>.css` *instead of*
  `monolith.css` (keep the `:root` block; drop or rename the `[data-theme]` one).
  Nothing else changes — the preset and components already read the same variables; **or**
- **Make it toggleable** — keep both files imported, change your theme's block from
  `:root, [data-theme="<name>"]` to just `[data-theme="<name>"]`, and set
  `data-theme="<name>"` on `<html>`. Toggling the attribute switches themes live.

> **Two documented exceptions** the token layer cannot reach:
> 1. The `.select` chevron is an SVG **data-URI**, which cannot hold a CSS variable —
>    its ink color (`%230d0d0d`) is fixed; keep it in sync with `--lt-ink` by hand.
> 2. `ringColor.DEFAULT` is a **color function** (not the `<alpha-value>` string form)
>    because Tailwind builds the global `*` ring-reset default via `withAlphaValue`,
>    which parses the color and can't parse a `var()` — the function keeps it tokenized.

---

## How an app consumes this package

There are **four** wiring steps. `apps/web` is the reference implementation.

### 1. Add the workspace dependency

Root `package.json` must include `packages/*` in its `workspaces` array. Then in
the app's `package.json`:

```jsonc
{
  "dependencies": {
    "@llamatrade/ui": "*"
  },
  "devDependencies": {
    "postcss-import": "^15.1.0" // required — see step 3
  }
}
```

Run `npm install` at the repo root to create the `node_modules/@llamatrade/ui`
symlink.

### 2. Tailwind: apply the preset + scan the package source

In the app's `tailwind.config.js`:

```js
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
    // CRITICAL: scan the shared package source so its component classes are generated.
    '../../packages/ui/src/**/*.{ts,tsx}',
  ],
  presets: [require('@llamatrade/ui/tailwind-preset')],
  // Do NOT re-declare the Monolith theme.extend here — it lives in the preset.
  // App-specific `safelist` / `plugins` still go here.
};
```

> The preset is authored as CommonJS (`module.exports`) so `require()` works even
> from an ESM (`export default`) config — Tailwind loads the config in a CJS context.
> `darkMode: 'class'` is set by the preset and inherited.

### 3. PostCSS: inline the shared CSS before Tailwind

The shared `styles.css` uses `@layer` / `@apply`, so it **must be inlined into the
app's entry CSS before Tailwind runs** (a single Tailwind pass that sees both the
`@tailwind` directives and the shared layers). Add `postcss-import` as the **first**
plugin in the app's `postcss.config.js`:

```js
export default {
  plugins: {
    'postcss-import': {}, // MUST be first — inlines @import '@llamatrade/ui/styles.css'
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

### 4. Entry CSS: import the shared layer + keep the `@tailwind` directives

In the app's entry CSS (e.g. `src/index.css`). The `@import`s **must be the first
statements** (CSS spec) so `postcss-import` inlines them. Import the **theme token
layer first** so its `:root` variables are defined before anything references them:

```css
@import '@llamatrade/ui/themes/monolith.css'; /* token layer — MUST be first */
@import '@llamatrade/ui/styles.css';

@tailwind base;
@tailwind components;
@tailwind utilities;

/* app-specific CSS, if any, below */
```

Set the theme as the explicit default on the root element in `index.html`:

```html
<html lang="en" data-theme="monolith">
```

See the **Theming** section above for how to tweak Monolith or add a new theme.

### Fonts

The Monolith type stack needs Anton (display), Archivo (sans), Space Mono (mono).
Add to the app's `index.html` `<head>`:

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link
  href="https://fonts.googleapis.com/css2?family=Anton&family=Archivo:wght@400;500;600;700;900&family=Space+Mono:wght@400;700&display=swap"
  rel="stylesheet"
/>
```

---

## Docker (workspace linking)

Because the package ships source and is resolved via a `node_modules` symlink, a
containerized app must be built **workspace-aware** — install from the repo root so
`node_modules/@llamatrade/ui -> ../packages/ui` is created:

- **Build context = repo root** (not the app dir).
- Copy the root `package.json` + `package-lock.json`, each workspace's
  `package.json`, and the whole `packages/ui` (its source is needed at link time),
  then run a single `npm ci`.
- For dev/hot-reload: bind-mount both `apps/<app>` and `packages/ui` at their
  in-container workspace paths, and use **anonymous volumes** for `node_modules`
  (root + app) so the image's workspace-linked install is preserved rather than the
  host's. When switching a running container to this layout, recreate it with
  **renewed anonymous volumes** (`docker compose up -d --force-recreate
  --renew-anon-volumes <svc>`) so a stale `node_modules` volume doesn't shadow the
  new one.

See `apps/web/Dockerfile.dev`, `apps/web/Dockerfile`, and the `web` service in
`infrastructure/docker/docker-compose.dev.yml` for the reference setup.

---

## Local checks

```bash
cd packages/ui && npm run typecheck   # tsc --noEmit against the package source
```
