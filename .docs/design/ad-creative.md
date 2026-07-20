# Ad Creative Spec

> The paid + organic ad system: creative directions, the placement matrix (every
> platform × aspect ratio), per-placement copy, and the finance-ad compliance
> rules. All creative uses the [Monolith brand system](./brand-guidelines.md).

Status: **spec + copy locked; production art pending.** Figures are illustrative
(see §5).

---

## 1. Creative directions

Six reusable angles, each mapped to an audience and a product pillar.

| # | Direction | Pillar | Audience | Core line |
|---|---|---|---|---|
| 01 | **Manifesto** | Awareness | Broad | BUILD THE MACHINE. TRADE YOUR OWN ACCOUNT. |
| 02 | **The DSL / Terminal** | Build (code) | Developers | The code you backtest is the code that trades live. |
| 03 | **Proof / Tearsheet** | Backtest | Converters | Prove it against the tape. |
| 04 | **Copilot / Plain English** | Copilot | AI-curious | Say it. Ship the DSL. |
| 05 | **Own It / Trust** | Own it | Skeptics | Your keys. Your account. Your call. |
| 06 | **Three Ways In** | Build (range) | Broad | Three ways in. One machine out. |

---

## 2. Placement matrix

| Placement | Ratio | Pixels | Best direction(s) |
|---|---|---|---|
| LinkedIn Sponsored | 1.91:1 | 1200×628 | 01 Manifesto, 05 Own it |
| Instagram Feed | 1:1 | 1080×1080 | 03 Proof, 04 Copilot, Live |
| Instagram Portrait | 4:5 | 1080×1350 | 04 Copilot |
| Story / Reel (IG, TikTok) | 9:16 | 1080×1920 | 06 Three ways, 05 Own it |
| X Promoted | 1.91:1 | 1200×628 | 02 DSL/Terminal |
| YouTube pre-roll | 16:9 | 1920×1080 | 01 Manifesto, 03 Proof |
| Display leaderboard | 728×90 | 728×90 | Claim-safe only (§5) |
| Display MPU | 300×250 | 300×250 | Claim-safe only (§5) |
| Carousel (IG/LinkedIn) | 1:1 ×N | 1080×1080 | 06 Core loop (Build→Backtest→Deploy) |

---

## 3. Layout grammar (every ad)

Built from the Monolith form language:

- **Eyebrow** — mono, uppercase, letter-spaced, with a small orange square dot.
- **Headline** — Anton, uppercase, one bold word in an ink slab or signal orange.
- **Sub** — Archivo, short, ≤2 lines, ≤64% width.
- **Lockup** — LT mark + `LlamaTrade` wordmark, bottom-left.
- **CTA** — mono, orange fill, ink border: `Request invite →` (or `View on
  GitHub →` for dev placements).
- **Disclaimer** — mono, low-emphasis, on any asset with figures.
- **Optional** — ticker strip, column numbers, DSL block.

Grounds: bone (default), ink (dev/serious), signal-orange (energy/story). Spend
orange once per ad.

---

## 4. Per-placement copy

### 4.1 LinkedIn Sponsored (1.91:1) — Manifesto
- Eyebrow: `CLOSED BETA · INVITE ONLY`
- Headline: **BUILD THE MACHINE. TRADE YOUR OWN ACCOUNT.**
- Sub: *Open-source algorithmic trading for people who want the engine, not the pitch.*
- CTA: `Request invite →`

### 4.2 Instagram Feed (1:1) — Proof
- Eyebrow: `ILLUSTRATIVE BACKTEST`
- Headline: **PROVE IT AGAINST THE TAPE.**
- Media: equity curve + metrics (Sharpe `1.84` · Total `+218%` · Max DD `−14.2%`).
- Disclaimer: *Illustrative demo · Not investment advice.*

### 4.3 Instagram Portrait (4:5) — Copilot
- Eyebrow: `AI COPILOT`
- Headline: **SAY IT. SHIP THE DSL.**
- Body: user bubble → copilot reply → compiled DSL snippet.
- CTA: `Request invite →`

### 4.4 Story / Reel (9:16) — Three Ways In
- Eyebrow: `OPEN SOURCE · $0 TO TEST`
- Headline: **3 WAYS IN. ONE MACHINE OUT.**
- List: `→ 01 No-code blocks` `→ 02 The DSL` `→ 03 Plain English`
- CTA: `Swipe up →`

### 4.5 Story / Reel (9:16) — Own It
- Eyebrow: `WE NEVER HOLD YOUR MONEY`
- Headline: **YOUR KEYS. YOUR ACCOUNT. YOUR CALL.**
- Sub: *Connect your own Alpaca keys. The engine automates your account and never custodies a cent.*

### 4.6 X Promoted (1.91:1) — DSL / Terminal
- Eyebrow: `FOR TRADERS WHO THINK IN CODE`
- Headline: **THE CODE YOU BACKTEST IS THE CODE THAT TRADES LIVE.**
- Media: `strategy.lt` terminal (golden-cross DSL).
- CTA: `View on GitHub →`

### 4.7 Display leaderboard / MPU — claim-safe
- Headline: **BACKTEST YEARS OF HISTORY IN SECONDS.**
- No figures. CTA: `Request invite →`

### 4.8 Carousel (1:1 ×3) — Core Loop
1. **(bone)** `01 / BUILD` — THREE WAYS IN. — *No-code · DSL · plain English.*
2. **(ink)** `02 / BACKTEST` — PROVE IT. — *Sharpe, drawdown, equity curve.*
3. **(bone)** `03 / DEPLOY` — GO LIVE. — *Rehearse in paper, then real money.*

---

## 5. Compliance (see [brand-guidelines §8](./brand-guidelines.md#8-compliance--non-negotiable))

1. **Illustrative figures only** — `+218%`, `1.84`, the heatmap are the product's
   own demo data. Any ad showing them carries **"illustrative / not investment
   advice."**
2. **Claim-safe variant** — Meta & Google restrict finance return claims. Where a
   tearsheet would be rejected (Display, most paid social), use **"Backtest years
   of history in seconds"** with no numbers.
3. **No forward-looking language** — never "expected/guaranteed/will."
4. **Custody** — never imply LlamaTrade holds funds.
5. **CTA** — `Request invite` during closed beta; destination `llamatrade.ai`.

---

## 6. Production notes

- **Fonts:** production art uses real Anton / Archivo / Space Mono. Static mockups
  and CSP-restricted previews fall back to Impact / system grotesque / SF Mono.
- **DSL:** any code shown must be valid `libs/dsl` grammar (see
  [strategy-dsl.md](../strategy-dsl.md)). Use the approved examples in
  [brand-guidelines §9.1](./brand-guidelines.md#91-dsl-for-copy--use-the-real-grammar-only).
- **Export:** PNG for static, MP4/GIF for motion; keep the ink offset-shadow crisp
  (no anti-aliased blur).
