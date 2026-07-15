# LlamaTrade — Marketing site (`apps/marketing`)

The standalone LlamaTrade marketing landing page. It is a **self-contained
static single-page site** (hash-anchor navigation, no SPA routing) that consumes
the shared **`@llamatrade/ui`** "Monolith" design system. It has **no** router,
auth store, or backend/gRPC dependency — it can be built once and dropped onto
**any** static host.

This app lives in the repo's npm workspace but deploys entirely independently of
the product app (`apps/web`).

---

## What it is / isn't

- **Is:** a Vite + React + TypeScript static build. Output is `dist/` — plain
  `index.html` + hashed JS/CSS assets, fully self-contained.
- **Isn't:** a server. There is nothing to run in production — just serve the
  static files. The one external runtime dependency is the Google Fonts
  `<link>` (Anton / Archivo / Space Mono) in `index.html`, and an optional POST
  to Loops for the waitlist form.
- **Shared:** the design system (`@llamatrade/ui` — `Logo`, `Marquee`,
  `StrategyTree`, the Monolith theme tokens + shared CSS layer + Tailwind
  preset). This is a workspace dependency, compiled into this app's own build.
- **Local, private:** everything under `src/` — the page sections, the bespoke
  `marketing.css` layout, the waitlist form.

---

## Build

From the repo root (workspace-aware):

```bash
npm install                          # once, at the repo root (links @llamatrade/ui)
npm run -w apps/marketing build      # → produces apps/marketing/dist/
```

or from this directory:

```bash
cd apps/marketing
npm run build
```

- **Build command:** `npm run -w apps/marketing build` (runs `tsc && vite build`)
- **Publish / output directory:** `apps/marketing/dist`
- **Node:** 20+
- **Install command (monorepo):** `npm install` at the **repo root** — this app
  depends on the `@llamatrade/ui` workspace package, so a plain `npm install`
  inside `apps/marketing` alone will not resolve it. Point your host's install
  step at the repo root (see per-host notes below).

Preview the production build locally:

```bash
npm run -w apps/marketing preview    # serves dist/ on http://localhost:8801
```

Local dev (hot reload): `npm run -w apps/marketing dev` (Vite on `:8801`), or via
Docker — see "Local dev via Docker" below.

---

## Configure the waitlist (Loops form id)

The "Join the beta" form posts to [Loops](https://loops.so). Until it is
configured it validates input and shows a "not connected yet" message instead of
POSTing. Two equivalent ways to wire it:

1. **Env var (recommended for CI/host builds).** Create a Form in Loops, copy its
   id, and set the build-time env var:

   ```bash
   VITE_LOOPS_FORM_ID=your_loops_form_id npm run -w apps/marketing build
   ```

   or set `VITE_LOOPS_FORM_ID` in your static host's build-environment settings
   (all of Netlify / Cloudflare Pages / Vercel expose env vars to the build). See
   `.env.example`.

2. **Hard-code it.** Replace the `REPLACE_WITH_LOOPS_FORM_ID` fallback literal in
   `src/components/WaitlistForm.tsx`.

> Using Kit/ConvertKit instead of Loops? Point `WAITLIST_ENDPOINT` at
> `https://app.kit.com/forms/FORM_ID/subscriptions` and set `WAITLIST_FIELD` to
> `email_address` in `WaitlistForm.tsx`.

---

## Deploy to any static host

The build output is host-agnostic. Every host needs the same two things: the
**build command** and the **publish directory**. Because this is a monorepo
workspace, the install/build must run from the **repo root** so `@llamatrade/ui`
resolves.

| Setting          | Value                                       |
| ---------------- | ------------------------------------------- |
| Base directory   | repo root (`.`)                             |
| Install command  | `npm install`                               |
| Build command    | `npm run -w apps/marketing build`           |
| Publish / output | `apps/marketing/dist`                       |
| Env (optional)   | `VITE_LOOPS_FORM_ID`                        |

No SPA rewrite rules are needed — navigation is in-page hash anchors (`#build`,
`#join`, …), so there are no client-side routes to rewrite to `index.html`.

### Netlify

`netlify.toml` at the repo root (or set the same fields in the UI):

```toml
[build]
  command = "npm run -w apps/marketing build"
  publish = "apps/marketing/dist"
```

### Cloudflare Pages

In the Pages project settings:

- Build command: `npm run -w apps/marketing build`
- Build output directory: `apps/marketing/dist`
- Root directory: repo root

### Vercel

`vercel.json` at the repo root (or the same fields in the UI):

```json
{
  "buildCommand": "npm run -w apps/marketing build",
  "outputDirectory": "apps/marketing/dist",
  "installCommand": "npm install"
}
```

### GitHub Pages / S3 / nginx / any web server

Run the build, then publish `apps/marketing/dist/` as the document root. Serving
the raw directory is enough (e.g. `npx serve apps/marketing/dist`). No routing
config required.

> These snippets are illustrative only — nothing in the app is tied to a specific
> host. Pick one; there is no lock-in.

---

## Local dev via Docker

A `marketing` service is defined in
`infrastructure/docker/docker-compose.yml` (+ the dev override
`docker-compose.dev.yml`) for local preview, mirroring `apps/web`'s
workspace-linked hot-reload setup. It runs the Vite dev server on internal
`:8811` with Vite `base: '/m/'`. From `infrastructure/docker`:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml \
  up -d --build --renew-anon-volumes proxy web marketing
# Single origin:            → http://localhost:8800   (this site at "/")
# Standalone marketing only → http://localhost:8801   (redirects to /m/)
```

The primary local origin is **`http://localhost:8800`** (the Caddy `proxy`
service — see below), which serves this site at `/` and the web app at every
other path. Host `8801` is still published (→ internal `8811`) for standalone
marketing testing; visiting it redirects to `/m/` (Vite's based root). These
containers are for local preview only; the production artifact is the static
`dist/`.

---

## Single-origin reverse proxy (dev + prod, no subdomains)

Locally **and in production** the marketing site and the web app are served from
**one origin** — there are no subdomains. A small Caddy reverse proxy
(`infrastructure/docker/Caddyfile`) does all the routing:

| Path          | Upstream               | Notes                                            |
| ------------- | ---------------------- | ------------------------------------------------ |
| `/`           | marketing              | root rewritten to `/m/` so this site renders at `/` |
| `/m/*`        | marketing              | this site's namespaced assets + Vite HMR ws      |
| _everything_  | web app                | clean routes (`/login`, `/dashboard`, …), `/assets/*`, web HMR ws |

Because this app is namespaced under `base: '/m/'`, its assets can never collide
with the web app's `/assets/*` — that is what makes one origin possible without
subdomains. The **same `Caddyfile` serves production** on a single domain: set
`SITE_ADDRESS` to the domain (Caddy then handles TLS automatically) and point
`WEB_UPSTREAM` / `MARKETING_UPSTREAM` at the prod containers. `/` → marketing,
everything else → web.

### Standalone static deploy (at a domain root, no proxy)

The default build uses `base: '/m/'` (for the proxy). To instead deploy the
static `dist/` at a bare domain root with **no** proxy, override the base at
build time:

```bash
npm run -w apps/marketing build -- --base=/
```

---

## Structure

```
apps/marketing/
├── index.html            # #root, favicon, Monolith fonts, data-theme="monolith"
├── package.json          # llamatrade-marketing (private); deps: react, react-dom, @llamatrade/ui
├── vite.config.ts        # React plugin; dev server :8801, host: true
├── tsconfig.json         # strict
├── tsconfig.node.json
├── postcss.config.js     # postcss-import FIRST, then tailwindcss, autoprefixer
├── tailwind.config.js    # presets: [@llamatrade/ui/tailwind-preset]; scans packages/ui/src
├── Dockerfile.dev        # local-preview dev image (workspace-aware)
├── .env.example          # VITE_LOOPS_FORM_ID
├── public/
│   └── logo-monolith.svg # favicon
└── src/
    ├── main.tsx          # renders <App/> into #root (no router, no store)
    ├── App.tsx           # renders <MarketingPage/> directly
    ├── index.css         # imports @llamatrade/ui theme + shared layer + @tailwind
    ├── vite-env.d.ts     # types VITE_LOOPS_FORM_ID
    ├── MarketingPage.tsx # composes the sections; imports ./marketing.css
    ├── marketing.css     # bespoke Monolith landing layout (scoped to .marketing-root)
    ├── sections/         # Nav, Hero, Build, Backtest, Copilot, Live, OwnIt, Cta, Footer
    ├── components/       # WaitlistForm, CodeBlock, Marquees, GridOverlay, CursorAccent, …
    ├── hooks/            # useScrollReveal
    └── data/             # editorLevels (Build section demo)
```
