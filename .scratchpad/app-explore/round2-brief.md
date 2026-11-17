# Round two brief (all areas)

You are designing a second, deeper round of options for one area of LlamaTrade (strategy building, backtesting, and paper and live trading on the user's own Alpaca account), as HTML mockups in `/Users/naib/Documents/code/llamatrade/.scratchpad/app-explore/`. Don't touch app code, don't commit, don't edit other areas' files.

## Read first
- `_template.html` (page contract: `<section class="ax-surface" id data-surface data-area data-title data-why>`, `<div class="ax-opt" data-opt data-name data-note>`, `data-frame="desktop"` (with `data-path`) / `data-frame="phone"`, `data-chart`, `data-logo`, `data-icon`, `data-tabs`).
- `kit.css` and `kit.js` fully. Use only classes, chart types and icons that exist.
- Your area's round-one page `area-<area>.html`: its demo data, look and every option. Don't repeat its ideas; round two must be genuinely new and more finished.
- `area-home-2.html` for round two's level of finish. The user chose home/layout2 A "The curve, annotated" (a big curve with one lane per session underneath, rebalances, starts and fills marked on their dates, continuing past Now into what's scheduled). Carry that visual language where it fits.
- `home-decisions.md` for what is decided so far.
- `/Users/naib/.claude/writing-voice.md` for every word of copy: no em dashes, plain, precise, no invented claims. Backtest figures are always labelled as backtests. When a design needs data the API lacks, say so plainly in the note.
- Visual bar, the marketing site: `/Users/naib/Documents/code/llamatrade/apps/web/src/marketing/marketing.css` and `sections/` (bright accent chart art behind headings, rim-lit windows, ink pill primary buttons, Overhang caps logo, Geist, mono numbers). Primary buttons are ink, accent blue is for charts, art and highlights, amber only for attention. Both light and dark must work.

## Demo data (keep consistent)
Total equity $128,406.12, +$612.40 today. Live $48,210.55, paper $80,195.57, cash $31,820.15. Sessions: All-Weather Portfolio (live, running, +0.31%), Recession Radar (paper, running, +0.62%, rebalances 15:50 ET today, TLT 60% / GLD 40% targets), Momentum Sectors (paper, running, +$266.66 today; in attention states it is frozen: Alpaca shows 43 SMH shares, the ledger 31), Tech Momentum Rotation (paper, stopped Nov 12). Today is Tuesday, November 17, 10:42 ET.

## What to produce
For every surface on your round-one page, a round-two surface (`data-surface="<area>/<name>2"`) with 4-6 NEW options, plus any important surface round one missed (edge cases, the phone-first view of the area). Each option: one desktop frame (full page in context, 1440 wide, real density) and one phone frame, and an honest `data-note` in round one's tone (what it's good at, what it costs). One option per surface is recommended: add `data-rec` and start its note with "Recommended.".

Top bar: `<div data-tb="<Area name>"></div>` renders the app bar (script below). Use it inside desktop frames.

## Output
A complete page `area-<area>-2.html`: copy the `<head>` of your round-one page (title "<Area>, round two", keep its styles, add yours prefixed with a short area prefix), a `<body data-title="<Area>, round two" data-desc="...">`, your sections, then the `[data-tb]` top-bar `<script>` block copied verbatim from the end of `area-home.html` (the `<script>` just before `kit.js`), then `<script src="kit.js"></script>`.

Render-check it in headless Chrome (playwright-core at `/Users/naib/.npm/_npx/9833c18b2d85bc59/node_modules/playwright-core/index.mjs`, `chromium.launch({channel:'chrome'})`) in light (`localStorage['ax-mode']='light'`) and dark: no console errors, no overflowing frames, charts render. Fix what you find.

Report in under 150 words: per surface, each option's letter and name in a few words, which is recommended and why, and any data gaps.
