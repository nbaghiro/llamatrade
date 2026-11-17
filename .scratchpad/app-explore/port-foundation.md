# Port foundation: shared components and shell extension points

Built by the foundation agent. Use these; don't fork them. If you need a change, make it backwards compatible and say so in your report. Paths are from `apps/web/src`.

## The annotated curve

`import { AnnotatedCurve } from '../../components/charts';` (types: `CurveLane`, `LaneEvent`, `LaneSpan`, `CurvePin`, `CurveBand`, `CurveFuture`, `CurveNow`, `AnnotatedCurveProps`)

One large equity curve on a **time** axis (marks sit on dates, not indexes), with pins above, lanes below, an optional Now line and a fixed-width future column. Layout is a three-column grid: label column (`labelWidth`, default 212px), past (fills), future (`futureWidth`, default 210px). Under 640px wide it goes compact: the label column disappears, lane names sit on top of each lane, neutral pins and event text are hidden, the future column narrows to 56px and the legend moves under the chart.

Props:

| prop | type | notes |
|---|---|---|
| `label` | string | aria label, required |
| `dates`, `values` | `Date[]`, `number[]` | the main line, one date per value |
| `benchmark` | `number[]` | dashed line on the same dates (scale it to the same start yourself) |
| `start`, `end` | Date | window; default first and last date. `end` is where Now sits |
| `now` | `{ label: 'Now 10:42', stale?: boolean }` | ink pill and line at `end`; `stale` makes them hollow/dashed (offline: `'Last update 10:38'`) |
| `future` | `{ end: Date; title?; content?; ticks?: Date[] }` | sunk column after Now; `content` is free JSX (the "Next two weeks" rows) |
| `pins` | `{ at, label, tone?: 'neutral'\|'accent'\|'loss', count?, row?: 0\|1, guide? }[]` | pills above with a dashed guide through the curve; `row: 1` for a second line; auto-aligned inward near edges |
| `bands` | `{ from, to, tone?: 'held'\|'loss'\|'accent', through? }[]` | shaded stretches; `through` extends into the lanes (backtest held periods, worst drawdown) |
| `lanes` | `CurveLane[]` | see below |
| `side` | ReactNode | label-column content beside the curve, usually a `StatList` |
| `legend` | `{ shape, label, tone?, count? }[]` | glyph key in the axis row of the label column |
| `height` | number | curve height only, default 196 |
| `ticks`, `tickFormat` | | default: month starts ("Sep 1"), years for spans over ~2.5 years |
| `tooltip` | `(index) => ReactNode` | hover readout with crosshair |
| `area` | boolean | gradient under the main line, default on |

`CurveLane`: `{ id, label, sub?, badge?, value?, tone?: 'default'|'muted'|'risk', href?, spans?, events?, future? }`
- `sub` makes the lane taller and adds a second line ("205 shares · 58.2%", "Which side of the rule").
- `value` sits at the right of the label column ("$0.22", "58.2/60").
- `tone: 'risk'` paints the label, line and marks amber (a frozen session on Home). `muted` greys a stopped lane's label.
- `spans`: `{ from, to?, style?: 'on'|'off'|'plan'|'bar', tone?, label? }`. Default is one `on` line across the window. `bar` is a filled box, with optional text inside (strategy branch "Top 2 of VTI, QQQ, IWM", backtest held symbol).
- `events`: `{ at, shape, tone?, count?, title?, text? }`. `count` puts a number in a `dot`; `text` is a note right of the mark ("+$3,000", "v3 saved Nov 3").
- `future`: `{ events?, line?, note? }` for the future column: planned marks positioned between Now and `future.end`, a dashed line (on by default when there are events), or a note ("Stopped, holding cash", "Restart to run v3", "buy about 5").

Marker shapes (`MarkerShape`): `ring` (rebalance, or buy), `dot` (fill or sell; numbered with `count`), `planned` (dashed), `start` (tick), `stop` (grey square), `diamond` / `diamondFilled` (version, deposit, dividend), `muted` (grey dot, e.g. the backtest-of-v2 reference lane). Tones: `accent` (default), `risk`, `muted`. The page decides what each shape means and says so in `legend` (Sessions uses dot = Buy, ring = Sell; Portfolio the other way round).

Example (Home):

```tsx
<div className="panel-rim px-5 pb-1.5 pt-4">
  <AnnotatedCurve label="Account equity, three months" dates={dates} values={equity} benchmark={spy}
    end={now} now={{ label: `Now ${etClock(now)}` }}
    future={{ end: inTwoWeeks, title: 'Next two weeks', content: <NextRows />, ticks }}
    pins={[{ at: started, label: 'Momentum Sectors started' }, { at: now, label: 'Fills today', tone: 'accent', count: 3, guide: false }]}
    side={<StatList items={stats} />}
    lanes={sessions.map((s) => ({ id: s.id, label: s.name, badge: <ModeBadge mode="paper" size="sm" />, events: s.rebalances.map((at) => ({ at, shape: 'ring' })), future: { events: [{ at: s.next, shape: 'planned' }] } }))}
    legend={[{ shape: 'ring', label: 'Rebalance' }, { shape: 'planned', label: 'Planned' }]} />
</div>
```

Backtests: no `now`/`future`; use `bands` for held periods and the worst drawdown, `bar` spans per symbol. Strategy overview: lanes with `sub`, a `bar` span for the branch, a diamond event with `text` for the saved version.

Next rebalance dates: `nextRebalanceDate(rebalance, today)` in `lib/sessionState.ts`. There is no time-of-day for rebalances in the API.

## Other chart pieces

- `LaneMarker` (`components/charts`): one glyph. `<LaneMarker shape="dot" count={2} />`; `positioned` centres it on a point inside a relative box.
- `LaneLegend` (`components/charts`): `<LaneLegend items={[{ shape: 'ring', label: 'Rebalance' }]} />`.
- Time helpers in `lib/chart/timeScale.ts`: `timeFraction`, `pctAt`, `timePath`, `timeArea`, `monthTicks`, `tickLabel`, `nearestDateIndex`, `pinAlign`.

## UI pieces (`components/ui`)

- `PageHead`: `{ title, documentTitle?, sub?, crumbs?: {label, to?}[], badges?, scope?, actions?, attention? }`. The top of every page; also sets the browser tab to "Title · LlamaTrade". `<PageHead crumbs={[{ label: 'Sessions', to: '/trading' }, { label: 'Paper' }]} title="Recession Radar" badges={<ModeBadge mode="paper" />} sub="Version 4 · ..." actions={<button className="btn btn-primary">Go live</button>} />`
- `ScopeControl`: `{ options: ScopeOption[], value, onChange }`. A radio group of All accounts / Live ••4821 / Paper ••PA92 with balances; with one option it renders a plain label. Get the props from `usePageScope` (below).
- `ModeBadge`: `{ mode: 'live'|'paper', size?: 'sm'|'md' }`. Live is solid ink, paper a dashed outline. `<ModeBadge mode="live" size="sm" />`. (The older `PaperPill` in `components/shell` still exists for the places that use it.)
- `PaperLiveSplit`: `{ live, paper, liveDetail?, paperDetail?, variant?: 'figures'|'bar' }`. `figures` is Home's two small figures beside the total; `bar` adds shares and the ink/hatched split bar (home/hero B). `<PaperLiveSplit live={48210.55} paper={80195.57} />`
- `StatList`: `{ items: { label, value, tone?: 'gain'|'loss' }[] }`. Label and figure rows with hairlines (the curve's side column, "Today by session"). `<StatList items={[{ label: 'Max drawdown', value: '−2.31%', tone: 'loss' }]} />`
- `WebOnlyNote`: `{ what? }`. Phone-only callout for read-only screens: "Editing strategies is on the web, on a wider screen." `<WebOnlyNote what="Editing backtests" />`
- CSS `.panel-rim` (in `styles/ui-layer.css`): the accent-rimmed hero panel around an annotated curve.
- Existing and still current: `Num`/`Money`/`Pct`, `Skeleton*`, `PanelError` (fail in place), `EmptyState`, `AttentionLine` (Home's amber line), `Segmented`, `Tabs`, `Popover`, `Menu`, `PageArt`.

## Shell extension points

**Areas.** `lib/navigation.ts`: `DESKTOP_NAV` has seven areas in order Home, Markets, Strategies, Backtests, Sessions, Portfolio, Copilot. Markets is `/markets` (placeholder `pages/markets/MarketsPage.tsx`, for the Portfolio agent to replace). `MOBILE_TABS` is Home, Sessions, Markets, Activity (`/notifications`), Account (`/settings`). Strategies, Backtests, Portfolio and Copilot have no phone tab; reach them from a session or search, and show `WebOnlyNote` on read-only phone screens. Every old route still works.

**Title.** Render `PageHead` at the top of the page; it sets `document.title`. For a non-string title pass `documentTitle`. Or call `useDocumentTitle('…')` from `hooks/useDocumentTitle`.

**Scope (mode2 A).** Each page keeps its own scope, in `?scope=all|live|paper` and in localStorage per page key:

```tsx
import { usePageScope } from '../../components/shell/usePageScope';
import { inScope } from '../../lib/scope';
const { scope, setScope, options } = usePageScope('home', { all: total, live: liveTotal, paper: paperTotal });
<PageHead title="…" scope={<ScopeControl options={options} value={scope} onChange={setScope} />} />
const shown = sessions.filter((s) => inScope(scope, s.mode === ExecutionMode.LIVE));
```

Options come from the connected Alpaca credentials (`useBrokerStore`): "All accounts" only when both kinds are connected. Balances are optional and only shown when you pass them. The demo account has one paper credential, so the control shows a single label there.

**Attention in the bar (attention2 A).** The bar puts an amber dot (with a count over one) on the area where an item is resolved. The shell reads these itself from what has loaded: Home's `aggregateAttention` entries (frozen sleeves and recent rejected orders go to Sessions; notices go to the area their link points at) and frozen sleeves in the trading store. A page can add marks:

```tsx
import { useReportAttention } from '../../components/shell/attention';
useReportAttention('backtests', failed.map((r) => ({ id: `bt-${r.id}`, area: 'backtests', title: `${r.name} failed.`, href: `/backtest/${r.id}` })));
```

The last report from a source stays until the source reports again (report `[]` to clear). `useAreaMarks()` returns the merged marks by area if you need them.

**Shell data.** The layout loads the trading blotter (`useTradingStore().loadBlotter`) once per app load, so sessions, orders, sleeves and performance are usually there on any page. `components/shell/useSessionRows()` gives every session as a `SessionRow` (name without "(paper)", state, figures).

**Bell (notifications2 A)**: today's lanes per session from the open to the close with fills where they happened (fills within ten minutes merge into a count) and frozen lanes in amber, then Needs you, then Earlier. **Account menu (account2 A)**: Alpaca accounts first, then plan, settings, appearance, sign out. **Palette (palette2 A)**: Today, Sessions and Recent before typing; typing narrows; `>` limits to actions; Tab asks Copilot. **Offline (offline2 B)**: grey strip, clock stops at the last update, retries every ten seconds.

## Known gaps and notes

- No last-checked time per Alpaca connection and no per-account balance in the API; the account menu shows Connected/Not active and the value of running sessions in that mode.
- The masked key is the last four characters of the stored key prefix (the API keeps only the first eight characters of a key).
- No rebalance time of day and no signal that Alpaca itself is unreachable, so the bell has no planned 15:50 dot and the offline strip has no Alpaca variant (offline2 C).
- The portfolio service reports `returns.return1d` in percent. `sessionFigures` in `components/sessions/sessionRows.ts` treats it as a fraction, so `todayPct` and `today` there are 100x too large. The palette works around it; the Sessions agent should fix it at the source.
- `.page` keeps its existing max width; the mockups run wider. That's a page-level choice for each area.
