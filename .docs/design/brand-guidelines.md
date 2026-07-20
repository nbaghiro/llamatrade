# Brand Guidelines — "Monolith"

> Source of truth for the LlamaTrade visual identity and voice. Every marketing
> surface, social asset, ad, and in-app brand element conforms to this document.
> The **implementation** of these tokens lives in
> [`apps/web/src/styles/monolith.css`](../../apps/web/src/styles/monolith.css)
> (the CSS custom-property layer) and
> [`apps/web/src/components/common/Logo.tsx`](../../apps/web/src/components/common/Logo.tsx)
> (the mark). If a value here and in code disagree, **the code is authoritative
> for pixels; this doc is authoritative for meaning and usage** — reconcile them.

Status: **design locked (2026-07-13).** Direction chosen: *Monolith* (brutalist /
Swiss-grid). Runner-up *Mosaic* archived. Light-only for product surfaces;
marketing is light-only.

---

## 1. Brand at a glance

| Attribute | Value |
|---|---|
| **Name** | LlamaTrade |
| **Wordmark** | `LlamaTrade` (one word, camel-cased L/T) |
| **Primary domain** | `llamatrade.ai` |
| **Tagline** | Open · Algorithmic · Your account |
| **One-liner** | The open-source machine for people who automate their own trading account. |
| **Positioning** | Open-source algorithmic trading for individual traders who want the engine, not the pitch. |
| **Design language** | Monolith — brutalist, Swiss-grid, zero-radius, hard offset shadows |
| **Category** | Financial technology · Developer-adjacent fintech |

**What we are:** a machine for building, backtesting, and running your *own*
trading strategies on your *own* brokerage account. **What we are not:** a signals
service, a robo-advisor, a custodial "trading app," or a black box.

---

## 2. Voice & tone

Direct, engineering-first, and anti-hype. We sound like a sharp tool, not a
finance influencer. Slightly technical — comfortable showing a line of DSL — but
never gatekeeping.

**Four voice pillars:**

1. **Plainspoken.** Say the thing. "Trade your own account," not "unlock your
   financial potential."
2. **Proof over promise.** Show the backtest, the code, the ledger. Numbers are
   always framed as illustrative (see §8).
3. **Ownership.** The user holds the keys, the account, and the code. Language
   reinforces control, never dependence.
4. **Transparent.** Open source is the differentiator. "No black box" is a
   recurring, literal claim — so never write copy that undercuts it.

### 2.1 Say / don't say

| ✅ Say | 🚫 Don't say | Why |
|---|---|---|
| Build the machine | Unlock your potential | Concrete, product-true |
| Trade your own account | Let our AI trade for you | We never custody or discretion-trade |
| No black box | Powered by proprietary AI | Open source is the whole pitch |
| Prove it against the tape | Proven to beat the market | Compliance + honesty |
| Rehearse risk-free in paper | Risk-free returns | No return is risk-free |
| Illustrative backtest | Guaranteed / expected returns | Never imply a forecast |
| Your keys, not ours | Deposit funds to get started | We move orders, not dollars |

### 2.2 Canonical copy library

These lines are approved and reusable across channels. Keep them verbatim where
possible so the brand compounds.

**Headlines**
- BUILD THE MACHINE. TRADE YOUR OWN ACCOUNT.
- STOP GUESSING. START TESTING.
- The code you backtest is the code that trades live.
- Your keys. Your account. Your call.
- Say it. Ship the DSL.
- Prove it against the tape.
- Go live. Watch it fill.
- Three ways in. One machine out.

**Support lines**
- Open-source algorithmic trading for people who want the engine, not the pitch.
- No drift. No surprises.
- We never custody your money.
- Rehearse risk-free in paper, then go live with real money.

**CTA** — always `Request invite` / `Join the beta` during closed beta;
destination `llamatrade.ai`.

---

## 3. Logo

The mark is an **ink box with a 3px signal-orange frame containing an "LT"
monogram** — the L in bone, the T in signal orange. It reads as a terminal
window / a building block.

### 3.1 Construction

Reference implementation:
[`apps/web/src/components/common/Logo.tsx`](../../apps/web/src/components/common/Logo.tsx).
The monogram is a `120×120` viewBox drawn from five rects:

```html
<!-- container: bg ink, 3px orange border, square -->
<svg viewBox="0 0 120 120">
  <!-- L — bone -->
  <g fill="#fbf8f1">
    <rect x="30" y="26" width="17" height="52"/>
    <rect x="30" y="61" width="39" height="17"/>
  </g>
  <!-- T — signal orange -->
  <rect x="54" y="26" width="40" height="17" fill="#ff4d1c"/>
  <rect x="68" y="26" width="17" height="52" fill="#ff4d1c"/>
</svg>
```

> **Note:** SVG `fill` attributes do not resolve CSS `var()`. The app sets the
> bone L via inline `style="fill: rgb(var(--lt-bone))"` so it tracks the theme
> token; hardcode `#fbf8f1` only in static exports.

### 3.2 Grounds & lockups

| Ground | Container | Monogram L | Monogram T |
|---|---|---|---|
| Bone / paper | ink box, orange frame | bone | orange |
| Ink (dark) | ink box, orange frame | bone | orange |
| Orange (knockout) | ink box, **white** frame | bone | **white** |

Horizontal lockup: mark + `LlamaTrade` display wordmark, gap ≈ 0.3× mark height.

### 3.3 Clear space, sizes, misuse

- **Clear space:** ≥ the monogram's cap-height on every side.
- **Minimum size:** 16px square (favicon). Border weight steps down: 3px ≥40px,
  2px 20–40px, 1.5px ≤20px.
- **Standard export sizes:** 500² (avatar/social), 300² (LinkedIn), 128², 48²
  (favicon set), 32², 16².
- **Never:** round the corners, add a gradient, rotate, recolor the monogram,
  place on a busy photo, or stretch non-proportionally.

---

## 4. Color

Palette is stored in code as **space-separated RGB channels** (e.g.
`--lt-orange-500: 255 77 28`) so Tailwind opacity modifiers work
(`rgb(var(--lt-x) / <alpha-value>)`). Hex is given here for design tools.

### 4.1 Core surfaces & brand

| Role | Token | Hex | RGB | Usage |
|---|---|---|---|---|
| Primary surface | `--lt-bone` | `#fbf8f1` | 251 248 241 | Page ground, buttons-secondary, badges |
| Ink | `--lt-ink` | `#0d0d0d` | 13 13 13 | Text, borders, hard shadows, inverted panels |
| Paper | `--lt-paper` | `#ffffff` | 255 255 255 | Raised card surface |
| Hairline | `--lt-line` | ink @ 14% | — | Rules, grid lines, dividers |

### 4.2 Signal orange — the **only** bold accent

| Token | Hex | Token | Hex |
|---|---|---|---|
| `--lt-orange-50` | `#fff1ec` | `--lt-orange-500` **(brand)** | `#ff4d1c` |
| `--lt-orange-100` | `#ffddd0` | `--lt-orange-600` | `#e63e10` |
| `--lt-orange-200` | `#ffb59e` | `--lt-orange-700` | `#b8300b` |
| `--lt-orange-300` | `#ff8c6b` | `--lt-orange-800` | `#8f2609` |
| `--lt-orange-400` | `#ff6a3d` | `--lt-orange-900` | `#6b1d08` |

**Rule:** spend orange in exactly one place per surface. If it fights the ground,
drop saturation or shift analogous — never add a second competing accent.

### 4.3 Semantic & secondary

| Role | Token | Hex | Notes |
|---|---|---|---|
| Info / links | `--lt-blue-500` | `#1a1aff` | Sparingly; hashtags, links |
| Success / up | `--lt-green-500` | `#0f7a34` | P&L up, "valid" — **semantic, not decorative** |
| Danger / down | `--lt-red-500` | `#c81e1e` | P&L down, errors, over-limit |
| Warning | `--lt-warning-500` | `#ff8c00` | Amber, partial states |
| Warm neutral | `--lt-gray-500` | `#7a7362` | Muted body text (ink-biased, never pure grey) |

Full 11-step ramps for every hue live in `monolith.css`. The neutral ramp is
warm/ink-biased (`#f7f5ef` → `#0d0d0d`) — never a cool grey.

### 4.4 Contrast

Ink `#0d0d0d` on bone `#fbf8f1` ≈ 18:1 (AAA). White on orange `#ff4d1c` ≈ 3.3:1
— **use white-on-orange for large/bold text and UI only, not body copy.** For
small text on orange, use ink.

---

## 5. Typography

Three faces, three jobs. Production loads them via one Google Fonts link
(Anton / Archivo / Space Mono). **Static exports and the CSP-restricted artifact
fall back** to the stacks below.

| Role | Face | Token | Fallback stack | Treatment |
|---|---|---|---|---|
| Display | **Anton** | `--lt-font-display` | `'Haettenschweiler','Arial Narrow',Impact,sans-serif` | UPPERCASE, tracking `.01em`, line-height `.9` |
| Body | **Archivo** (500/700/900) | `--lt-font-sans` | `system-ui,-apple-system,'Helvetica Neue',Arial` | Sentence case, 1.5–1.6 leading, ~65ch measure |
| Utility / data / code | **Space Mono** (400/700) | `--lt-font-mono` | `ui-monospace,'SF Mono',Menlo,Consolas` | UPPERCASE labels w/ tracking `.1–.22em`; DSL/code as-is |

**Scale (marketing / editorial):** display clamps `30 → 58px+` for H2, larger for
heroes; body `14–18px`; eyebrows/labels `10–12px` mono, letter-spaced. Give
headings `text-wrap: balance`. Use `font-variant-numeric: tabular-nums` for any
aligned figures (metrics, prices, counters).

---

## 6. Form language

The brutalist rules that make everything feel like one system:

| Element | Rule | Token |
|---|---|---|
| **Radius** | `0` everywhere | `--lt-radius: 0px` |
| **Borders** | 2–3px solid ink | — |
| **Shadows** | hard offset, no blur, ink | `--lt-shadow-sm/base/lg/xl` = `2/4/8/12px` `0` ink |
| **Grid** | exposed 12-column hairline scaffold | `.bg-grid`, `--lt-grid-line` |
| **Hover** | invert (ink ⇄ orange / ⇄ bone) | — |
| **Motifs** | ticker marquees, column numbers (`01–08`), `;;` DSL comments | — |

`--lt-block-*` tokens style the strategy tree/block editor (else-branch fill
`#e6e0d2`, weight-branch fill `#d4eddb`).

---

## 7. Motion

Restrained and purposeful. Approved motions: ticker marquee (linear, ~38s loop),
scroll-triggered reveals, hover inverts, and progress-bar fills on backtest UI.
**Always** honor `prefers-reduced-motion: reduce` — disable marquees and reveals,
snap fills to 100%. No parallax, no bouncing, no gratuitous entrance animation.

---

## 8. Compliance — non-negotiable

LlamaTrade is pre-launch and never gives investment advice. Every external asset
follows these rules:

1. **Illustrative data only.** All performance figures (`+218%`, Sharpe `1.84`,
   the monthly heatmap, etc.) are the product's **own demo data**, not real
   client results. Any asset showing them carries a visible **"illustrative"** /
   **"not investment advice"** line.
2. **No forward-looking claims.** Never "expected," "guaranteed," "will return."
3. **Claim-safe variant.** Meta & Google restrict finance return claims. Where a
   tearsheet would be rejected, use the figure-free line
   **"Backtest years of history in seconds."**
4. **Custody honesty.** Never imply LlamaTrade holds customer funds. The user
   connects their own Alpaca keys; we send orders, not dollars.
5. **Risk line.** Live trading involves risk of loss. Standard disclaimer:
   *"LlamaTrade automates your own brokerage account — you hold the funds, not us.
   Live trading involves risk of loss. Not investment advice."*

### 8.1 Approved illustrative figures

From the marketing backtest panel (`momentum-rotation`, Jan 2019 – Jan 2026):

| Metric | Value | Metric | Value |
|---|---|---|---|
| Total return | +218% (vs +96% SPY) | Max drawdown | −14.2% |
| Sharpe | 1.84 | Sortino | 2.41 |
| CAGR | +18.0% | Win rate | 63% |
| Trades | 146 | Rebalances | 84 |

Always paired with "illustrative · fees + slippage modeled · not investment advice."

---

## 9. Product facts for copy (canonical)

Use these when writing any asset so claims stay accurate:

- **Three ways to build:** visual no-code blocks · S-expression DSL · plain-English AI copilot.
- **Backtest:** Sharpe/Sortino/CAGR/drawdown/equity curve/monthly heatmap;
  fees + slippage modeled; multi-symbol; **16+ indicators** wired
  (SMA, EMA, RSI, MACD, Bollinger, ATR, ADX, Stoch, CCI, OBV, VWAP, MFI, +5).
- **Deploy:** paper (risk-free rehearsal) → live (real money) with **the same
  compiled strategy** — no rewrite, no drift.
- **Live:** real-time fills; market / limit / stop / stop-limit; partial fills;
  broker fills are the source of truth for position state.
- **Own it:** bring-your-own Alpaca keys (encrypted at rest, scoped per session);
  double-entry portfolio ledger with sleeves + FIFO lots, reconciled every fill;
  fully open source / self-hostable.
- **The core loop:** Build → Backtest → Deploy → Monitor.

### 9.1 DSL for copy — use the real grammar only

Strategy code shown in any asset MUST be valid `libs/dsl` grammar (see
[`strategy-dsl.md`](../strategy-dsl.md)). Never invent tokens. Approved examples:

```lisp
;; momentum rotation
(strategy "Tech Momentum Rotation"
  :rebalance monthly :benchmark QQQ
  (filter :by momentum :select (top 2) :lookback 90
    (weight :method equal
      (asset QQQ) (asset XLK) (asset SMH))))

;; golden cross
(strategy "Golden Cross" :rebalance daily
  (if (crosses-above (ema SPY 50) (ema SPY 200))
    (weight :method equal (asset SPY))
    (else (asset BIL))))
```

Forbidden invented tokens (from other DSLs): `universe`, `rank`, `roc`, `hold`,
`defsymphony`, `when`, `buy`, `close`-as-symbol.

---

## 10. Related docs

- [Social account set-up sheet](./social-accounts.md) — handles, bios, per-platform fields
- [Launch campaign](./social-campaign.md) — content library + cadence
- [Ad creative spec](./ad-creative.md) — placements & directions
- Implementation: [`monolith.css`](../../apps/web/src/styles/monolith.css) · [`Logo.tsx`](../../apps/web/src/components/common/Logo.tsx) · [`apps/web/src/marketing/`](../../apps/web/src/marketing/)
