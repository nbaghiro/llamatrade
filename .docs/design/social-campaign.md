# Launch Campaign — Content Library

> The closed-beta launch campaign: ready-to-post copy and media direction across
> IG Stories, LinkedIn, X/Twitter, and the blog, plus a posting cadence and
> hashtag bank. Every piece maps to a product pillar and follows the
> [brand voice & compliance rules](./brand-guidelines.md).

Status: **drafted, awaiting sign-off.** Copy is final-draft quality; media is
specced against the [ad-creative](./ad-creative.md) system.

---

## 1. Campaign frame

| Attribute | Value |
|---|---|
| **Goal** | Closed-beta signups (waitlist → invite) |
| **Primary CTA** | `Request invite` → `llamatrade.ai` |
| **Duration** | 4-week rolling launch |
| **Tone** | Storytelling-first, lightly technical (real DSL, never faked) |
| **Compliance** | Illustrative figures only; "not investment advice" on any proof asset |

**Audiences:** (A) retail traders burned by black-box bots · (B) developers /
quant-curious · (C) AI-curious builders · (D) open-source enthusiasts.

**Content pillars → product truth:** Build (3 ways) · Backtest (prove it) ·
Deploy (paper→live, same code) · Own it (your keys, open source) · Copilot
(plain English → DSL).

---

## 2. IG Stories

Format · `9:16 · 1080×1920` · ~15s/frame · link sticker to `llamatrade.ai` ·
tappable sequences.

### ST-01 · 60-second build *(Copilot · Audience C)*
3 frames. **Goal:** show the describe → compile → prove loop.

1. **(ink)** eyebrow `60-SECOND BUILD` · headline **"SAY IT."** · user bubble:
   *"momentum rotation across tech ETFs, rebalance monthly."*
2. **(bone)** eyebrow `COPILOT ✦ COMPILING` · DSL block compiling · `✓ VALID
   ✓ BACKTESTABLE`.
3. **(orange)** eyebrow `BACKTEST · RESULT` · **"+218%\*"** · `vs +96% SPY ·
   *illustrative*` · CTA **"Swipe up ↑"**.

Stickers: poll *"would you run this? YES / show me the code"* (frame 3) + link.
Hook: **"Say it."**

### ST-02 · Anatomy of a strategy *(DSL · Audience B)*
2 frames, educational.

1. **(bone)** **"READ EVERY LINE IT RUNS."** · DSL with the `(filter :by
   momentum :select (top 2))` line highlighted · annotation *"← ranks by 90-day
   momentum, holds top 2."*
2. **(ink)** **"NO PYTHON. NO GLUE."** · *"The same S-expression you read is the
   artifact that backtests and trades live."* · CTA "Learn the DSL →".

Sticker: annotation callout + "Learn more" link. Hook: **"Read every line it runs."**

### ST-03 · Paper → Live *(Deploy · Audience A)*
2 frames.

1. **(bone)** badge `◷ Paper mode` · **"REHEARSE RISK-FREE."**
2. **(orange)** badge `◉ Live · real money` · **"THEN GO LIVE. SAME CODE."**

Sticker: emoji slider *"how ready are you? 🔥"*. Hook: **"Same code."**

### ST-04 · Who holds your money? *(Own it · Audience A)*
2 frames, trust.

1. **(ink)** **"WHO HOLDS YOUR MONEY?"**
2. **(bone)** **"NOT US."** · *"You bring your own Alpaca keys — encrypted,
   per-session. We move orders, never dollars."*

Sticker: Q&A box *"ask us anything about custody."* Hook: **"Not us."**

---

## 3. LinkedIn

Format · text-led, hook in first two lines · `1200×628` or carousel · 3–5 hashtags.

### LI-01 · Founder manifesto *(Awareness · Audience A/D)*
> Every "AI trading bot" I tried had the same flaw: I couldn't see what it was
> doing with my money.
>
> So we built the opposite.
>
> **LlamaTrade is an open-source machine for people who automate their own account:**
>  → Build a strategy three ways — visual blocks, a real DSL, or plain English
>  → Backtest it against years of history, fees and slippage modeled
>  → Deploy it to **your own** Alpaca account — we never hold a cent
>
> The strategy you backtest is the exact strategy that trades live. Same code. No
> drift. No black box.
>
> We're in closed beta. **Request an invite → llamatrade.ai**
>
> \#algotrading #opensource #fintech #quant

**Media:** 1.91:1 ink hero — "BUILD THE MACHINE. TRADE YOUR OWN ACCOUNT."
**Hook:** "I couldn't see what it was doing with my money." **CTA:** request invite.

### LI-02 · Technical deep-dive *(Credibility · Audience B)*
> This is a complete momentum-rotation strategy. Twelve lines.
>
> ```lisp
> (strategy "Tech Momentum Rotation"
>   :rebalance monthly :benchmark QQQ
>   (filter :by momentum :select (top 2) :lookback 90
>     (weight :method equal
>       (asset QQQ) (asset XLK) (asset SMH))))
> ```
>
> No Python glue. No broker SDK. No translation layer between "the thing you
> tested" and "the thing that trades."
>
> You read it, you diff it in git, you backtest it, you deploy it. A small
> S-expression DSL — compact enough to hold in your head, expressive enough for
> rotations, crossovers and regime switches.
>
> It's open source. Fork it → **github.com/llamatrade**
>
> \#quant #dsl #opensource #tradingsystems

**Media:** 16:9 ink terminal card of the DSL. **Hook:** "Twelve lines." **CTA:** fork the repo.

### LI-03 · Value listicle (carousel) *(Category reframe · Audience A)*
> Most retail algo trading fails for 3 boring reasons. We designed around each. ↓
>
> **1 / The backtest lies.** Fees and slippage get ignored, so live never matches
> the curve. We model both — on every fill.
>
> **2 / The bot is a black box.** You can't audit a decision you can't see. So the
> whole engine is open source, end to end.
>
> **3 / Your money lives in someone else's app.** Not here. You bring your own
> keys; we never custody funds.
>
> Honest backtests. Readable strategies. Your own account. That's the pitch.
>
> **Swipe →** then request an invite at llamatrade.ai
>
> \#trading #fintech #opensource

**Media:** 3-slide carousel (01 The backtest lies / 02 Black box / 03 Not your
account). **Hook:** "3 boring reasons retail algo trading fails."

### LI-04 · Contrarian hot take *(Differentiator · broad)*
> Unpopular opinion: your trading bot should never hold your money.
>
> We built LlamaTrade so it literally can't. You connect your own Alpaca API keys
> — encrypted at rest, scoped per session — and the engine automates **your**
> brokerage account. We move orders, not dollars.
>
> If a trading product's first ask is "deposit funds here," ask where the money
> actually goes.
>
> Own your keys. Own your account. Own your call.
> **llamatrade.ai**

**Media:** 1.91:1 bone — "YOUR KEYS. YOUR ACCOUNT. YOUR CALL." **Hook:** "should
never hold your money."

### LI-05 · Build-in-public ship log *(Momentum · Audience D)*
> Shipped this week — all open source:
>
>  ◆ Multi-symbol backtests
>  ◆ Stop, stop-limit + partial fills in the live engine
>  ◆ A double-entry portfolio ledger — sleeves + FIFO lots, reconciled against the
>    broker on **every fill**
>
> That last one sounds boring. It's the difference between "roughly what I own"
> and books that tie out to the penny.
>
> Building the unglamorous parts in the open. ⭐ the repo → **github.com/llamatrade**
>
> \#buildinpublic #fintech #opensource

**Media:** 16:9 live order-stream card. **Hook:** "the boring parts that make P&L
correct." **CTA:** star the repo.

---

## 4. X / Twitter

Format · short + punchy · dev-Twitter voice · lowercase ok · threads for depth ·
16:9 media.

### X-01 · Banger
```
the code you backtest is the code that trades live.

no drift. no translation layer. no black box.

that's the whole product.
```
Media: 16:9 ink "BACKTEST = LIVE. SAME CODE."

### X-02 · Thread (5 tweets)
1. `we rebuilt retail algo trading around one rule:` / `you should be able to read every decision your bot makes.` / `here's how 🧵`
2. `strategies are a tiny S-expression DSL. a full momentum rotation is ~12 lines you can hold in your head 👇` **[+ code image]**
3. `the exact DSL you backtest is what trades live. no python glue, no "now port it to the broker API." one artifact, cradle to grave.`
4. `your money never touches us. bring your own alpaca keys — encrypted, per-session. we send orders, not dollars.`
5. `and it's all open source. fork it, self-host it, audit it.` / `closed beta's open → llamatrade.ai`

### X-03 · Code flex
```
golden cross. 5 lines. compiles, backtests, and trades:
```
Media: 16:9 terminal of the golden-cross DSL.

### X-04 · Poll
```
how do you actually build trading strategies?

◻ drag-and-drop no-code
◻ write code / a DSL
◻ describe it in plain english
◻ i don't — i vibe

(we do the first three — plain english compiles to valid DSL via copilot.)
```

### X-05 · Relatable / humor
```
backtest: +218%
me, an adult: ok let's run it in paper for a month first

(illustrative numbers. not investment advice. we ARE cowards — responsibly.)
```

### X-06 · Ship log
```
open sourced this week:
· multi-symbol backtests
· stop-limit + partial fills
· FIFO lot reconciliation on every fill

boring infra. the kind that makes your P&L actually correct.

⭐ github.com/llamatrade
```

---

## 5. Blog (evergreen backbone)

Long-form pieces every social post links back to. Host on `llamatrade.ai/blog`.

| # | Category | Title | Angle | Read |
|---|---|---|---|---|
| B-01 | Company · Manifesto | Why we open-sourced our trading engine | Trust isn't a badge, it's source code | 7 min |
| B-02 | Engineering | A DSL that reads like English, compiles like code | Why S-expressions; keeping a small grammar readable | 11 min |
| B-03 | Education | Backtesting honestly: fees, slippage & survivorship | The costs that decide whether live matches the curve | 9 min |
| B-04 | Architecture | Paper to live with zero code changes | The execution seam behind same-artifact deploy | 8 min |
| B-05 | Engineering | A double-entry ledger for your portfolio | Sleeves, FIFO lots, per-fill reconciliation | 12 min |
| B-06 | Data story | Golden Cross, dissected: what a 7-year backtest shows | Honest, illustrative, caveated | 6 min |

Each post: brutalist cover (see ad-creative), a lede that states the thesis, real
DSL where relevant, and a closing "not investment advice" line on B-03/B-06.

---

## 6. Suggested first-week cadence

| Day | Channel | Piece |
|---|---|---|
| Mon | LinkedIn + X | LI-01 manifesto · X-01 banger |
| Tue | IG Stories + Blog | ST-01 60-sec build · publish B-01 |
| Wed | X (thread) | X-02 thread |
| Thu | LinkedIn + IG Stories | LI-02 DSL deep-dive · ST-02 anatomy |
| Fri | X + Blog | X-05 humor · publish B-02 |
| Sat | IG Stories | ST-04 custody |
| Sun | X (poll) | X-04 poll (weekend engagement) |

Then rotate LI-03/04/05, X-03/06, ST-03, and B-03…B-06 across weeks 2–4.

---

## 7. Hashtag bank

- **Core:** `#algotrading` `#opensource` `#fintech` `#quant`
- **Dev:** `#dsl` `#tradingsystems` `#buildinpublic` `#python`
- **Reach:** `#trading` `#investing` `#stockmarket` `#automation`

Use 3–5 on LinkedIn, 1–2 on X (or none), a fuller set on Instagram. Never stack
hashtags that imply performance (e.g. `#profits`, `#gains`).
