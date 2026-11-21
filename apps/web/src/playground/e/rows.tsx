/* eslint-disable react-refresh/only-export-components -- row builders, not components */
import { LiveMarker, Ticker } from '../../components/ui/TreeRow';
import {
  ACCOUNT,
  BACKTESTS,
  SESSIONS,
  STRATEGIES,
  stateLabel,
  strategyById,
  type Backtest,
  type Session,
  type Strategy,
  type Value,
} from '../data';

import type { ProposalState } from './askContext';
import {
  accountWindow,
  activeSession,
  backtestWindow,
  FUND_CLASS,
  FUND_NAME,
  fundSpark,
  lastBacktest,
  PROPOSALS,
  pts,
  sessionValues,
  tone,
} from './model';
import { Phrase } from './outline';
import { diffItems, itemsOf, liveSet, type Item, type Kind } from './outlineModel';
import {
  ACCOUNT_SCOPE,
  backtestScope,
  fundScope,
  fundsWindow,
  mixScope,
  modeScope,
  sessionScope,
  type Scope,
} from './scope';
import { Change, Money, Pct, Trend, Weight, type Col, type LRow } from './tree';
import { Button, ModeTag, Spark } from './ui';

export const TYPE: Record<Kind, string> = {
  strategy: 'Strategy',
  if: 'If',
  else: 'Else',
  filter: 'Filter',
  weight: 'Weight',
  group: 'Group',
  asset: 'Asset',
};

const textOf = (parts: (string | Value)[]) =>
  parts
    .map((p) => (typeof p === 'string' ? p : p.text))
    .join(' ')
    .replace(/^\w/, (c) => c.toUpperCase());

export interface ProposalApi {
  proposals: Record<string, ProposalState>;
  setProposal: (id: string, s: ProposalState) => void;
}

export const proposalState = (id: string, api: ProposalApi): ProposalState | undefined =>
  PROPOSALS[id] ? (api.proposals[id] ?? 'open') : undefined;

/** The strategy's outline under a parent row, with a proposed edit merged in as + and − rows. */
export function outlineItems(st: Strategy, api: ProposalApi): Item[] {
  const state = proposalState(st.id, api);
  const prop = PROPOSALS[st.id];
  const cur = itemsOf(st.name, st.cadence, st.rules);
  if (state === 'open' && prop)
    return diffItems(cur, itemsOf(st.name, st.cadence, prop.rules)).filter(
      (i) => !i.id.startsWith('root')
    );
  if (state === 'applied' && prop) return itemsOf(st.name, st.cadence, prop.rules).slice(1);
  return cur.slice(1);
}

function copilotRow(st: Strategy, depth: number, id: string, api: ProposalApi): LRow | null {
  const state = proposalState(st.id, api);
  const prop = PROPOSALS[st.id];
  if (!prop || !state || state === 'dismissed') return null;
  const stop = (fn: () => void) => (e: { stopPropagation: () => void }) => {
    e.stopPropagation();
    fn();
  };
  const b = lastBacktest(st.id);
  return {
    id,
    depth,
    type: 'Copilot',
    label:
      state === 'open' ? (
        <span>
          {prop.note}
          <span className="ml-2 font-mono text-[12px] text-fg-3">
            backtest <span className={tone(prop.effect.ret)}>{pts(prop.effect.ret * 100)}</span>
            {b ? ` against ${pts(b.ret * 100)}` : ''} · worst {pts(prop.effect.worst * 100)}
          </span>
        </span>
      ) : (
        <span>
          Version {prop.version} applied, not saved yet
          <span className="ml-2 text-fg-3">{prop.note}</span>
        </span>
      ),
    end:
      state === 'open' ? (
        <span className="flex items-center gap-1.5">
          <Button variant="primary" onClick={stop(() => api.setProposal(st.id, 'applied'))}>
            Apply
          </Button>
          <Button onClick={stop(() => api.setProposal(st.id, 'dismissed'))}>Discard</Button>
        </span>
      ) : (
        <Button variant="quiet" onClick={stop(() => api.setProposal(st.id, 'open'))}>
          Undo
        </Button>
      ),
  };
}

/** Splits a session's change today across its funds by their weight and their move. */
export function todayBySymbol(s: Session): Record<string, number> {
  const moves: Record<string, number> = {
    VGLT: -0.31,
    TLT: -0.42,
    IEF: -0.12,
    VTI: -1.71,
    XLC: -1.12,
    XLF: -0.88,
    XLI: -0.95,
    GLD: -0.64,
    DBC: -0.21,
  };
  const raw = s.holds.map((h) => ({ sym: h.symbol, k: h.weight * (moves[h.symbol] ?? -0.5) }));
  const sum = raw.reduce((a, r) => a + r.k, 0) || 1;
  return Object.fromEntries(raw.map((r) => [r.sym, (s.today * r.k) / sum]));
}

const modeOf = (s: Session) => (s.mode === 'live' ? 'Live' : 'Paper');

/** A session and its outline, with value, today, weight and the path it holds today. */
export function sessionRows(
  s: Session,
  depth: number,
  parentValue: number,
  api: ProposalApi,
  withNext: boolean
): LRow[] {
  const st = strategyById(s.strategyId);
  if (!st) return [];
  const { w } = sessionValues(s);
  const running = !s.stoppedOn;
  const scope = sessionScope(s);
  const path = scope.path;
  const head: LRow = {
    id: s.id,
    depth,
    type: 'Session',
    strong: true,
    live: running && s.holds.length > 0,
    muted: !running,
    label: (
      <>
        {st.name}
        <span className="ml-2 font-normal text-fg-3">
          v{s.version}
          {running ? (withNext ? '' : ` · ${s.next}`) : ` · stopped ${s.stoppedOn}, in cash`}
        </span>
      </>
    ),
    scope,
    to: `/e/sessions/${s.id}`,
    cells: {
      value: <Money v={s.value} muted={!running} />,
      today: <Change v={running ? s.today : undefined} />,
      since: <Trend values={w.main} bench={w.bench} />,
      weight: <Weight pct={(s.value / parentValue) * 100} muted={!running} live={running} />,
      next: <span className="truncate text-fg-2">{s.next ?? 'Stopped'}</span>,
    },
  };
  if (!running) return [head];
  const items = outlineItems(st, api);
  const held = new Map(s.holds.map((h) => [h.symbol, h.weight]));
  const swapped = items.map((it) => ({
    ...it,
    mark: it.mark === 'add' ? ('del' as const) : undefined,
  }));
  const live = liveSet(swapped, new Set(held.keys()));
  const tBy = todayBySymbol(s);
  const valueOf = (it: Item) =>
    it.kind === 'asset' && it.symbol && it.mark !== 'add' && held.has(it.symbol)
      ? { v: (s.value * (held.get(it.symbol) ?? 0)) / 100, w: held.get(it.symbol) ?? 0 }
      : null;
  const out: LRow[] = [head];
  const cop = copilotRow(st, depth + 1, `${s.id}:copilot`, api);
  if (cop) out.push(cop);
  items.forEach((it, i) => {
    const d = depth + it.depth;
    const isLive = live.has(it.id);
    if (it.kind === 'asset' && it.symbol) {
      const val = valueOf(it);
      const t = val ? tBy[it.symbol] : undefined;
      out.push({
        id: `${s.id}:${it.id}`,
        depth: d,
        type: 'Asset',
        mark: it.mark,
        live: isLive,
        label: (
          <>
            <Ticker symbol={it.symbol} on={isLive && !it.mark} />
            <span className="ml-2 text-fg-3">{FUND_NAME[it.symbol] ?? ''}</span>
          </>
        ),
        scope: fundScope(it.symbol, [...path, it.symbol], val?.v, t, st.id),
        cells: {
          value: val ? <Money v={val.v} /> : undefined,
          today: val ? <Change v={t} /> : undefined,
          since: <Trend values={fundSpark(it.symbol).slice(-14)} />,
          weight:
            it.mark === 'add' ? (
              <Weight pct={it.pct} pick={it.pick} text={`→ ${it.weight}`} />
            ) : val ? (
              <Weight pct={val.w} live={isLive} />
            ) : (
              <Weight pct={it.pct} pick={it.pick} muted text={it.pick ? 'pick' : it.weight} />
            ),
        },
      });
      return;
    }
    let v = 0;
    let wt = 0;
    let t = 0;
    const parts: { symbol: string; weight: number }[] = [];
    for (let j = i + 1; j < items.length && items[j].depth > it.depth; j++) {
      const val = valueOf(items[j]);
      const sym = items[j].symbol;
      if (val && sym) {
        v += val.v;
        wt += val.w;
        t += tBy[sym] ?? 0;
        parts.push({ symbol: sym, weight: val.w });
      }
    }
    const title = textOf(it.parts);
    out.push({
      id: `${s.id}:${it.id}`,
      depth: d,
      type: TYPE[it.kind],
      mark: it.mark,
      live: isLive,
      muted: !isLive && it.mark !== 'add',
      label: <Phrase parts={it.parts} />,
      scope: mixScope(`${s.id}:${it.id}`, title, [...path, title], parts, v || undefined, t, st.id),
      cells: wt
        ? {
            value: <Money v={v} />,
            today: <Change v={t} />,
            weight: <Weight pct={wt} live={isLive} />,
          }
        : { value: <span className="text-[12px] text-fg-3">not held</span> },
    });
  });
  return out;
}

export const ACCOUNT_COLS: Col[] = [
  { key: 'value', label: 'Value', width: 104, align: 'right', keep: true },
  { key: 'today', label: 'Today', width: 80, align: 'right' },
  { key: 'since', label: 'Since start', width: 116 },
  { key: 'weight', label: 'Weight', width: 124 },
];

export const SESSION_COLS: Col[] = [...ACCOUNT_COLS, { key: 'next', label: 'Next', width: 128 }];

const PAPER_CASH =
  ACCOUNT.paper - SESSIONS.filter((s) => s.mode === 'paper').reduce((a, s) => a + s.value, 0);

/** ACCOUNT → LIVE / PAPER → SESSION → rules → ASSET. */
export function accountRows(api: ProposalApi, opts: { root: boolean; next?: boolean }): LRow[] {
  const base = opts.root ? 1 : 0;
  const rows: LRow[] = [];
  const acc = accountWindow('1Y');
  if (opts.root)
    rows.push({
      id: 'account',
      depth: 0,
      type: 'Account',
      strong: true,
      live: true,
      label: (
        <>
          Whole account
          <span className="ml-2 font-normal text-fg-3">live and paper on Alpaca</span>
        </>
      ),
      scope: ACCOUNT_SCOPE,
      cells: {
        value: <Money v={ACCOUNT.total} />,
        today: <Change v={ACCOUNT.today} />,
        since: <Trend values={acc.main} bench={acc.bench} />,
        weight: <Weight pct={100} live />,
      },
    });
  for (const mode of ['live', 'paper'] as const) {
    const ses = SESSIONS.filter((s) => s.mode === mode);
    const value = mode === 'live' ? ACCOUNT.live : ACCOUNT.paper;
    const sc = modeScope(mode);
    const mw = sc.window('3M');
    rows.push({
      id: mode,
      depth: base,
      type: mode === 'live' ? 'Live' : 'Paper',
      strong: true,
      live: true,
      label: (
        <>
          {mode === 'live' ? 'Real money' : 'Paper money'}
          <span className="ml-2 font-normal text-fg-3">
            {ses.filter((s) => !s.stoppedOn).length} running
          </span>
        </>
      ),
      scope: sc,
      cells: {
        value: <Money v={value} />,
        today: <Change v={ses.reduce((a, s) => a + s.today, 0)} />,
        since: <Trend values={mw.main} bench={mw.bench} />,
        weight: <Weight pct={(value / ACCOUNT.total) * 100} live />,
      },
    });
    for (const s of ses) rows.push(...sessionRows(s, base + 1, value, api, !!opts.next));
    if (mode === 'paper' && PAPER_CASH > 1)
      rows.push({
        id: 'paper-cash',
        depth: base + 1,
        type: 'Cash',
        muted: true,
        label: 'Not in a session',
        scope: mixScope('paper-cash', 'Cash', ['Account', 'Paper', 'Cash'], [], PAPER_CASH, 0),
        cells: {
          value: <Money v={PAPER_CASH} muted />,
          weight: <Weight pct={(PAPER_CASH / value) * 100} muted />,
        },
      });
  }
  return rows;
}

/* ---------- Strategies ---------- */

export const STRATEGY_COLS: Col[] = [
  { key: 'backtest', label: 'Last backtest', width: 136, keep: true },
  { key: 'recent', label: 'Recent', width: 68 },
  { key: 'holds', label: 'Holds now', width: 72, align: 'right' },
  { key: 'weight', label: 'Weight', width: 124 },
  { key: 'state', label: 'State', width: 104 },
];

const ORDER: Record<Strategy['state'], number> = {
  running: 0,
  stopped: 1,
  'never-run': 2,
  draft: 3,
};

export const SORTED_STRATEGIES = [...STRATEGIES].sort((a, b) => ORDER[a.state] - ORDER[b.state]);

export function strategyScope(st: Strategy): Scope {
  const b = lastBacktest(st.id);
  if (b) return { ...backtestScope(b, ['Strategies', st.name]), key: st.id, title: st.name };
  return {
    ...mixScope(st.id, st.name, ['Strategies', st.name], [{ symbol: 'SPY', weight: 1 }]),
    note: 'Not backtested yet. The line is SPY itself.',
    ask: { context: st.id, placeholder: `Ask about ${st.name}` },
  };
}

/** One strategy and its outline, with the live path and target weights. */
export function strategyRows(
  st: Strategy,
  api: ProposalApi,
  depth = 0,
  edits: Record<string, number> = {}
): LRow[] {
  const ses = activeSession(st.id);
  const b = lastBacktest(st.id);
  const held = new Map(ses?.holds.map((h) => [h.symbol, h.weight]) ?? []);
  const items = outlineItems(st, api).map((it) =>
    edits[it.id] !== undefined
      ? { ...it, pct: edits[it.id], weight: `${edits[it.id]}%`, mark: 'add' as const }
      : it
  );
  const live = liveSet(
    items.map((it) => ({ ...it, mark: it.mark === 'add' ? ('del' as const) : undefined })),
    new Set(held.keys())
  );
  const markerAt =
    items.find(
      (it) => live.has(it.id) && (it.kind === 'if' || it.kind === 'else' || it.kind === 'filter')
    )?.id ?? items.find((it) => it.depth === 1 && live.has(it.id))?.id;
  const sc = strategyScope(st);
  const bw = b ? backtestWindow(b) : null;
  const out: LRow[] = [
    {
      id: st.id,
      depth,
      type: 'Strategy',
      strong: true,
      live: live.size > 0,
      label: (
        <>
          {st.name}
          <span className="ml-2 font-normal text-fg-3">
            v{st.version} · {st.cadence}
          </span>
        </>
      ),
      scope: sc,
      to: `/e/strategies/${st.id}`,
      cells: {
        backtest: b ? (
          <span className="flex items-baseline gap-2 whitespace-nowrap">
            <Pct v={b.ret * 100} />
            <span className="font-mono text-[11px] tabular-nums text-fg-3">
              SPY {pts(b.spy * 100)}
            </span>
          </span>
        ) : (
          <span className="text-fg-3">None yet</span>
        ),
        recent: bw ? <Trend values={bw.main.slice(-30)} /> : undefined,
        state: st.mode ? (
          st.state === 'running' ? (
            <ModeTag mode={st.mode} />
          ) : (
            <span className="text-fg-3">{stateLabel(st)}</span>
          )
        ) : (
          <span className="text-fg-3">{stateLabel(st)}</span>
        ),
      },
    },
  ];
  const cop = copilotRow(st, depth + 1, `${st.id}:copilot`, api);
  if (cop) out.push(cop);
  items.forEach((it) => {
    const isLive = live.has(it.id);
    const title = it.kind === 'asset' ? (it.symbol ?? '') : textOf(it.parts);
    const path = ['Strategies', st.name, title];
    const h = it.symbol ? held.get(it.symbol) : undefined;
    out.push({
      id: `${st.id}:${it.id}`,
      depth: depth + it.depth,
      type: TYPE[it.kind],
      mark: it.mark,
      live: isLive,
      label:
        it.kind === 'asset' && it.symbol ? (
          <>
            <Ticker symbol={it.symbol} on={isLive && !it.mark} />
            <span className="ml-2 text-fg-3">{FUND_NAME[it.symbol] ?? ''}</span>
          </>
        ) : (
          <Phrase parts={it.parts} />
        ),
      scope:
        it.kind === 'asset' && it.symbol
          ? fundScope(it.symbol, path, undefined, undefined, st.id)
          : { ...sc, key: `${st.id}:${it.id}`, path, title },
      cells: {
        recent: it.symbol ? <Trend values={fundSpark(it.symbol).slice(-14)} /> : undefined,
        holds:
          h !== undefined && it.mark !== 'del' ? (
            <span className="font-mono tabular-nums text-fg">{h.toFixed(1)}%</span>
          ) : undefined,
        weight:
          it.kind === 'asset' ? (
            <Weight
              pct={it.pct}
              pick={it.pick}
              live={isLive}
              muted={it.mark === 'del'}
              text={it.pick ? 'if picked' : it.weight}
            />
          ) : undefined,
        state: it.id === markerAt ? <LiveMarker /> : undefined,
      },
    });
  });
  return out;
}

/* ---------- Backtests ---------- */

/** Earlier runs kept for the playground, so a strategy shows its history of runs. Sample. */
const EARLIER: Backtest[] = [
  {
    id: 'b1a',
    strategyId: 'momentum-sectors',
    version: 4,
    ran: 'Oct 21',
    range: 'Oct 2024 to Oct 2026',
    ret: 0.151,
    spy: 0.205,
    worst: -0.181,
    sharpe: 0.42,
    seed: 38,
  },
  {
    id: 'b1b',
    strategyId: 'momentum-sectors',
    version: 3,
    ran: 'Oct 2',
    range: 'Oct 2024 to Oct 2026',
    ret: 0.133,
    spy: 0.198,
    worst: -0.19,
    sharpe: 0.37,
    seed: 39,
  },
  {
    id: 'b2a',
    strategyId: 'recession-radar',
    version: 2,
    ran: 'Oct 12',
    range: 'Oct 2024 to Oct 2026',
    ret: 0.196,
    spy: 0.205,
    worst: -0.161,
    sharpe: 0.52,
    seed: 24,
  },
];

export const RUNS: Backtest[] = [...BACKTESTS, ...EARLIER];

export const BACKTEST_COLS: Col[] = [
  { key: 'ret', label: 'Return', width: 64, align: 'right', keep: true },
  { key: 'spy', label: 'SPY', width: 60, align: 'right' },
  { key: 'worst', label: 'Max drop', width: 70, align: 'right' },
  { key: 'sharpe', label: 'Sharpe', width: 52, align: 'right' },
  { key: 'curve', label: 'Against SPY', width: 84 },
];

function runCells(b: Backtest) {
  const w = backtestWindow(b);
  return {
    ret: <Pct v={b.ret * 100} />,
    spy: <Pct v={b.spy * 100} toned={false} />,
    worst: <span className="font-mono tabular-nums text-fg-2">{pts(b.worst * 100)}</span>,
    sharpe: <span className="font-mono tabular-nums text-fg-2">{b.sharpe.toFixed(2)}</span>,
    curve: <Spark values={w.main} bench={w.bench} width={84} height={18} />,
  };
}

/** STRATEGY → RUN → the outline it ran. */
export function backtestRows(): LRow[] {
  const out: LRow[] = [];
  const ids = [...new Set(RUNS.map((r) => r.strategyId))];
  for (const id of ids) {
    const st = strategyById(id);
    if (!st) continue;
    const runs = RUNS.filter((r) => r.strategyId === id);
    out.push({
      id: `s:${id}`,
      depth: 0,
      type: 'Strategy',
      strong: true,
      label: (
        <>
          {st.name}
          <span className="ml-2 font-normal text-fg-3">
            {runs.length} {runs.length === 1 ? 'run' : 'runs'}
          </span>
        </>
      ),
      scope: { ...backtestScope(runs[0], ['Backtests', st.name]), key: `s:${id}` },
      to: `/e/strategies/${id}`,
      cells: runCells(runs[0]),
    });
    runs.forEach((b, k) => {
      out.push({
        id: `bt:${b.id}`,
        depth: 1,
        type: 'Run',
        muted: k > 0,
        label: (
          <>
            Version {b.version}
            <span className="ml-2 text-fg-3">
              ran {b.ran} · {b.range}
            </span>
          </>
        ),
        scope: backtestScope(b, ['Backtests', st.name, `v${b.version}, ran ${b.ran}`]),
        to: `/e/backtests/${b.id}`,
        cells: runCells(b),
      });
      if (b.version !== st.version) return;
      itemsOf(st.name, st.cadence, st.rules)
        .slice(1)
        .forEach((it) =>
          out.push({
            id: `bt:${b.id}:${it.id}`,
            depth: 1 + it.depth,
            type: TYPE[it.kind],
            label:
              it.kind === 'asset' && it.symbol ? (
                <>
                  <Ticker symbol={it.symbol} />
                  <span className="ml-2 text-fg-3">{FUND_NAME[it.symbol] ?? ''}</span>
                </>
              ) : (
                <Phrase parts={it.parts} />
              ),
            scope: it.symbol
              ? fundScope(it.symbol, ['Backtests', st.name, it.symbol], undefined, undefined, id)
              : undefined,
            cells: {
              curve: it.symbol ? (
                <Weight pct={it.pct} pick={it.pick} text={it.pick ? 'pick' : it.weight} />
              ) : undefined,
            },
          })
        );
    });
  }
  return out;
}

/* ---------- Portfolio ---------- */

export const PORTFOLIO_COLS: Col[] = [
  { key: 'value', label: 'Value', width: 104, align: 'right', keep: true },
  { key: 'today', label: 'Today', width: 80, align: 'right' },
  { key: 'year', label: 'Past year', width: 116 },
  { key: 'weight', label: 'Weight', width: 124 },
];

interface Hold {
  symbol: string;
  value: number;
  today: number;
  by: { s: Session; value: number; today: number }[];
}

export const HOLDS: Hold[] = (() => {
  const map = new Map<string, Hold>();
  for (const s of SESSIONS) {
    if (s.stoppedOn) continue;
    const t = todayBySymbol(s);
    for (const h of s.holds) {
      const v = (s.value * h.weight) / 100;
      const cur = map.get(h.symbol) ?? { symbol: h.symbol, value: 0, today: 0, by: [] };
      cur.value += v;
      cur.today += t[h.symbol] ?? 0;
      cur.by.push({ s, value: v, today: t[h.symbol] ?? 0 });
      map.set(h.symbol, cur);
    }
  }
  return [...map.values()].sort((a, b) => b.value - a.value);
})();

export const CLASSES = (() => {
  const map = new Map<string, Hold[]>();
  for (const h of HOLDS) {
    const k = FUND_CLASS[h.symbol] ?? 'Other';
    map.set(k, [...(map.get(k) ?? []), h]);
  }
  return [...map.entries()]
    .map(([name, funds]) => ({
      name,
      funds,
      value: funds.reduce((a, f) => a + f.value, 0),
      today: funds.reduce((a, f) => a + f.today, 0),
    }))
    .sort((a, b) => b.value - a.value);
})();

export const CASH_TOTAL = ACCOUNT.total - HOLDS.reduce((a, h) => a + h.value, 0);

/** CLASS → FUND → the sessions that hold it; the live path is money held on live. */
export function portfolioRows(): LRow[] {
  const out: LRow[] = [];
  for (const c of CLASSES) {
    const liveClass = c.funds.some((f) => f.by.some((b) => b.s.mode === 'live'));
    const year = fundsWindow(
      c.funds.map((f) => ({ symbol: f.symbol, weight: f.value })),
      '1Y'
    ).main;
    out.push({
      id: `c:${c.name}`,
      depth: 0,
      type: 'Class',
      strong: true,
      live: liveClass,
      label: c.name,
      scope: mixScope(
        `c:${c.name}`,
        c.name,
        ['Portfolio', c.name],
        c.funds.map((f) => ({ symbol: f.symbol, weight: f.value })),
        c.value,
        c.today
      ),
      cells: {
        value: <Money v={c.value} />,
        today: <Change v={c.today} />,
        year: <Trend values={year} />,
        weight: <Weight pct={(c.value / ACCOUNT.total) * 100} live={liveClass} />,
      },
    });
    for (const f of c.funds) {
      const liveFund = f.by.some((b) => b.s.mode === 'live');
      out.push({
        id: `f:${f.symbol}`,
        depth: 1,
        type: 'Fund',
        live: liveFund,
        label: (
          <>
            <Ticker symbol={f.symbol} on={liveFund} />
            <span className="ml-2 text-fg-3">{FUND_NAME[f.symbol] ?? ''}</span>
          </>
        ),
        scope: fundScope(f.symbol, ['Portfolio', c.name, f.symbol], f.value, f.today),
        cells: {
          value: <Money v={f.value} />,
          today: <Change v={f.today} />,
          year: <Trend values={fundSpark(f.symbol)} />,
          weight: <Weight pct={(f.value / c.value) * 100} live={liveFund} />,
        },
      });
      for (const b of f.by) {
        const st = strategyById(b.s.strategyId);
        out.push({
          id: `h:${f.symbol}:${b.s.id}`,
          depth: 2,
          type: 'Session',
          live: b.s.mode === 'live',
          muted: b.s.mode !== 'live',
          label: (
            <>
              {st?.name}
              <span className="ml-2 text-fg-3">{modeOf(b.s).toLowerCase()}</span>
            </>
          ),
          scope: sessionScope(b.s),
          to: `/e/sessions/${b.s.id}`,
          cells: {
            value: <Money v={b.value} />,
            today: <Change v={b.today} />,
            weight: <Weight pct={(b.value / f.value) * 100} live={b.s.mode === 'live'} />,
          },
        });
      }
    }
  }
  out.push({
    id: 'c:cash',
    depth: 0,
    type: 'Cash',
    muted: true,
    label: (
      <>
        Cash
        <span className="ml-2 text-fg-3">stopped session and unused paper money</span>
      </>
    ),
    scope: mixScope('c:cash', 'Cash', ['Portfolio', 'Cash'], [], CASH_TOTAL, 0),
    cells: {
      value: <Money v={CASH_TOTAL} muted />,
      weight: <Weight pct={(CASH_TOTAL / ACCOUNT.total) * 100} muted />,
    },
  });
  return out;
}
