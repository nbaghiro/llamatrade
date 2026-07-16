# @llamatrade/mobile

Expo (React Native) app — the mobile client for LlamaTrade. Companion to the
two design docs:

- **Product & design plan** — functionality → mobile matrix, IA, screen gallery.
- **Architecture & streaming spike** — the plan this scaffold implements.

It reuses the web app's brain via **`@llamatrade/core`** (Connect transport
factory + Monolith design tokens) and renders in the same **Monolith** theme
(bone / ink / signal-orange · Anton · Archivo · Space Mono · zero radius · hard
offset shadows).

> **Status: scaffold.** This branch was authored but **not yet installed or run
> in a simulator** (no npm install / Metro / device in the authoring env). Treat
> it as a reviewable starting point — expect to reconcile dep versions with
> `npx expo install` on first run.

## What's here

```
app/                     Expo Router screens
  _layout.tsx            root: fonts + splash + Stack
  (tabs)/_layout.tsx     5-tab bar (Home · Book · Copilot · Strats · You)
  (tabs)/index.tsx       Home — KPI hero, equity chart, strategies, activity
  (tabs)/portfolio.tsx   Portfolio — KPIs, equity, positions
  (tabs)/strategies.tsx  Strategies — sortable card list + sparklines
  (tabs)/copilot.tsx     Copilot — chat preview → launches the spike
  (tabs)/account.tsx     Account — profile, broker connect, plan, usage
  spike.tsx              ★ the runnable Connect-streaming spike harness
src/
  net/                   clients (expo/fetch!), service config, secure storage
  stores/auth.ts         zustand persisted to the device Keychain
  spike/streamingSpike.ts   Copilot + backtest server-streaming probes
  charts/                pure SVG path math + react-native-svg LineChart
  ui/                    Monolith primitives (Card, KpiTile, Badge, text, icons)
  data/demo.ts           demo values so screens render before the backend is wired
```

## Run it

```bash
# from the repo root
npm install                       # installs the new workspaces too

# generate proto (writes src/generated/proto — gitignored)
npm run proto --workspace=@llamatrade/mobile
```

### Development build (recommended — no Expo Go chrome)

```bash
cd apps/mobile && npx expo run:ios --device "iPhone 16 Pro"
```

Builds a real native app straight into the simulator — **no Expo Go, no floating
dev-tools button**. Open the dev menu with the **shake gesture** (Simulator ▸
Device ▸ Shake, or ⌃⌘Z). Verified working on Xcode 26.2 / iOS 26.3 / RN 0.86.

### Expo Go (quicker, but shows Expo Go's floating dev button)

```bash
npm run start --workspace=@llamatrade/mobile   # press i / a, or scan
```

### ⚠️ Xcode 26 patch (temporary)

`expo run:ios` needs a one-line fix to `expo-modules-jsi` — under Xcode 26's Swift
compiler `abs(_:)` in `JavaScriptCodable+Date.swift` is ambiguous. It's applied
automatically by `scripts/patch-expo-xcode26.mjs` (wired as `postinstall`, idempotent).
If a root `npm install` doesn't trigger the workspace postinstall, run it manually:
`node apps/mobile/scripts/patch-expo-xcode26.mjs`. **Delete the script + hook once
Expo ships Xcode-26 support.**

### Pointing at your dev backend

On a device/emulator `localhost` is the device itself, so set your machine's LAN
IP via env (or an `.env` consumed by `app.config`):

```bash
EXPO_PUBLIC_AGENT_URL=http://192.168.1.20:8990 \
EXPO_PUBLIC_BACKTEST_URL=http://192.168.1.20:8830 \
npm run start --workspace=@llamatrade/mobile
```

Cleartext HTTP is allowed in dev via the iOS ATS exception in `app.json` and
Android `usesCleartextTraffic` — **remove both for production** (HTTPS behind a
gateway).

## ★ The streaming spike

The one thing to prove before building the Copilot phase: **does Connect
server-streaming deliver incrementally in React Native?** RN's built-in `fetch`
buffers the whole body; `expo/fetch` (wired in `src/net/clients.ts`) exposes a
streaming `response.body`.

1. Open the app → **Account** or **Copilot** tab → **Run streaming spike**.
2. Paste an access token + tenant/user id from a logged-in web session.
3. Tap **▶ Copilot stream**. **PASS** = ≥2 `CONTENT_DELTA` events arrive before
   `COMPLETE`, first event < 1.5s. The log shows each delta with its timestamp —
   if they tick up over time, streaming works; if they all land at once, it's
   buffering (fall back to the `react-native-fetch-api` polyfill, then a
   WebSocket bridge — see the architecture spec).
4. **▶ Backtest progress** does the same for `streamBacktestProgress`.

## Fonts

`assets/fonts/` holds the OFL-licensed faces (Anton, Archivo, Space Mono). See
`assets/fonts/NOTICE.md`.

## Not yet done (by design)

- No visual block builder / DSL editor — read-only viewer + Copilot only (desktop
  owns authoring).
- Real Zustand read-stores (portfolio/dashboard/…) not yet migrated into
  `@llamatrade/core` — screens use `src/data/demo.ts`. That migration is Phase 1.
- NativeWind not wired — styling is plain `StyleSheet` on the shared tokens.
