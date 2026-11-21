import {
  ACCOUNT,
  BACKTESTS,
  MARKET,
  SAMPLE_SPY_200D,
  SESSIONS,
  STRATEGIES,
  strategyById,
  usd,
  type Session,
  type Strategy,
} from '../data';

import {
  accountWindow,
  activeSession,
  lastBacktest,
  RANGE_WORDS,
  sessionActivity,
  type Range,
} from './model';

export const DATELINE = 'Friday, November 20, 2026';
export const TIME = '12:04 ET';

export const todayPct = ACCOUNT.today / (ACCOUNT.total - ACCOUNT.today);

const RANGE_SHORT: Record<Range, string> = {
  '1M': 'over the past month',
  '3M': 'over three months',
  YTD: 'this year',
  '1Y': 'over the past year',
};

const pctWord = (v: number, d = 1) => `${Math.abs(v * 100).toFixed(d)}%`;

/** The front page headline, written from the account's numbers for the chosen range. */
export function frontHeadline(range: Range): string {
  const w = accountWindow(range);
  const n = w.main.length;
  const gap = w.main[n - 1] - w.bench[n - 1];
  const day = `${todayPct < 0 ? 'Down' : 'Up'} ${pctWord(todayPct)} today`;
  const vs = `${Math.abs(gap).toFixed(1)} points ${gap < 0 ? 'behind' : 'ahead of'} SPY ${RANGE_SHORT[range]}`;
  return `${day}, ${vs}`;
}

export const rangeWords = (r: Range) => RANGE_WORDS[r];

export const RUNNING_SESSIONS = SESSIONS.filter((s) => !s.stoppedOn);

/** The running session that lost or gained the most today. */
export const biggestMover = [...RUNNING_SESSIONS].sort(
  (a, b) => Math.abs(b.today / b.value) - Math.abs(a.today / a.value)
)[0];

export function frontDeck(): string {
  const fell = RUNNING_SESSIONS.filter((s) => s.today < 0).length;
  const mover = strategyById(biggestMover.strategyId)?.name ?? '';
  const all =
    fell === RUNNING_SESSIONS.length
      ? `All ${RUNNING_SESSIONS.length} running sessions fell`
      : `${fell} of ${RUNNING_SESSIONS.length} sessions fell`;
  return `${all}. ${mover} moved the most.`;
}

/* ---------- Drift against target weights ---------- */

const pctOf = (w: string) => Number.parseFloat(w.replace(/[^\d.]/g, '')) || 0;

export interface Drift {
  symbol: string;
  held: number;
  target: number;
  off: number;
}

export function driftOf(s: Session): Drift[] {
  const st = strategyById(s.strategyId);
  if (!st || !s.holds.length) return [];
  const held = new Set(s.holds.map((h) => h.symbol));
  const rule = st.rules.find((r) => r.funds?.some((f) => held.has(f.symbol) && !f.ifPicked));
  if (!rule?.funds) return [];
  return s.holds
    .map((h) => {
      const f = rule.funds?.find((x) => x.symbol === h.symbol);
      const target = f ? pctOf(f.weight) : 0;
      return { symbol: h.symbol, held: h.weight, target, off: h.weight - target };
    })
    .sort((a, b) => Math.abs(b.off) - Math.abs(a.off));
}

export const maxDrift = (s: Session) => driftOf(s)[0];

/* ---------- Stories ---------- */

const SPY_200 = SAMPLE_SPY_200D[SAMPLE_SPY_200D.length - 1][1];
export const spyVs200 = MARKET.quotes[0].price / SPY_200 - 1;

/** One short status line per strategy, written from its session, drift or backtest. */
export function statusLine(st: Strategy): string {
  const ses = activeSession(st.id);
  const b = lastBacktest(st.id);
  if (st.id === 'recession-radar' && ses)
    return `In bonds and gold since SPY closed under its 200-day average on Nov 13.`;
  if (ses) {
    const d = maxDrift(ses);
    if (d && Math.abs(d.off) >= 1)
      return `${d.symbol} is ${Math.abs(d.off).toFixed(1)} points ${d.off > 0 ? 'over' : 'under'} target. ${ses.next ?? ''}.`;
    return `Holds ${ses.holds.map((h) => h.symbol).join(', ')}. ${ses.next ?? ''}.`;
  }
  if (st.state === 'stopped') {
    const last = SESSIONS.find((x) => x.strategyId === st.id);
    return `Stopped ${st.stoppedOn} with ${last ? usd(last.value) : 'its value'} in cash.`;
  }
  if (st.state === 'draft') return 'Draft. Not backtested yet.';
  if (b) {
    const best = Math.max(...BACKTESTS.map((x) => x.sharpe));
    return b.sharpe === best
      ? `Never run. Sharpe ${b.sharpe.toFixed(2)}, the best of any backtest.`
      : `Never run. Last backtest trailed SPY by ${((b.spy - b.ret) * 100).toFixed(1)} points.`;
  }
  return 'Never run.';
}

export const RESTING_STRATEGIES = STRATEGIES.filter((s) => s.state !== 'running');

/* ---------- Briefs ---------- */

export interface Brief {
  when: string;
  title: string;
  detail: string;
  to?: string;
  tone?: 'gain' | 'loss';
}

const nameOf = (s: Session) => strategyById(s.strategyId)?.name ?? '';

export function fillBriefs(): Brief[] {
  return RUNNING_SESSIONS.flatMap((s) =>
    sessionActivity(s)
      .filter((a) => /^(Sold|Bought)/.test(a.what))
      .map((a) => ({
        when: a.when,
        title: `${a.what}`,
        detail: `${nameOf(s)} · ${a.detail}`,
        to: `/h/sessions/${s.id}`,
      }))
  );
}

export function rebalanceBriefs(): Brief[] {
  return SESSIONS.flatMap((s) =>
    sessionActivity(s)
      .filter((a) => a.what === 'Rebalanced')
      .map((a) => ({
        when: a.when,
        title: nameOf(s),
        detail: a.detail,
        to: `/h/sessions/${s.id}`,
      }))
  ).sort((a, b) => dateKey(b.when) - dateKey(a.when));
}

export function driftBriefs(): Brief[] {
  return RUNNING_SESSIONS.map((s) => ({ s, d: maxDrift(s) }))
    .filter((x): x is { s: Session; d: Drift } => !!x.d && Math.abs(x.d.off) >= 0.2)
    .sort((a, b) => Math.abs(b.d.off) - Math.abs(a.d.off))
    .map(({ s, d }) => ({
      when: s.mode,
      title: `${d.symbol} ${d.off > 0 ? '+' : '−'}${Math.abs(d.off).toFixed(1)} pts`,
      detail: `${nameOf(s)} · ${d.held.toFixed(1)}% against ${d.target}% target`,
      to: `/h/sessions/${s.id}`,
    }));
}

export function comingBriefs(): Brief[] {
  return RUNNING_SESSIONS.filter((s) => s.next).map((s) => ({
    when: s.next?.match(/\w{3} \d+/)?.[0] ?? 'Daily',
    title: nameOf(s),
    detail: s.next ?? '',
    to: `/h/sessions/${s.id}`,
  }));
}

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
function dateKey(s: string): number {
  const [m, d] = s.split(' ');
  return MON.indexOf(m) * 40 + Number(d || 0);
}

export const allActivity = () =>
  SESSIONS.flatMap((s) =>
    sessionActivity(s).map((a) => ({ ...a, session: s, name: nameOf(s) }))
  ).sort((a, b) => dateKey(b.when) - dateKey(a.when));

export function stateKicker(s: Strategy): string {
  if (s.state === 'running') return `${s.mode} · v${s.version}`;
  if (s.state === 'stopped') return `Stopped ${s.stoppedOn} · v${s.version}`;
  if (s.state === 'never-run') return `Never run · v${s.version}`;
  return 'Draft';
}
