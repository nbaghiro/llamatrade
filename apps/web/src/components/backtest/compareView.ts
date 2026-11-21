import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toNumber } from '@llamatrade/core/stores/backtest';

import { longDate, monthKey, monthLabel, type TradeInput } from '../../lib/backtestView';
import { formatMoney, formatNumber, formatPct } from '../../lib/format';
import { diffCode, type CodeLine } from '../../lib/strategyDiff';

import { heldSymbolsOn, type HoldingLane } from './annotations';
import { runMeta } from './runData';

/** Simulated orders: each trade's entry and, once closed, its exit. */
export function orderCount(trades: readonly TradeInput[]): number {
  return trades.reduce((n, t) => n + (t.entryTime ? 1 : 0) + (t.exitTime ? 1 : 0), 0);
}

export interface SettingsComparison {
  /** Every setting matched. */
  identical: boolean;
  /** "Jan 4, 2021 → Oct 30, 2026", "$25,000", … for the first run. */
  shared: string[];
  /** "Capital $25,000 and $10,000", one per setting that differs. */
  differences: string[];
}

interface Setting {
  name: string;
  value: (run: BacktestRun) => string;
}

const fee = (v: number) => `${formatMoney(v, { dp: 2 })} per fill`;

const SETTINGS: readonly Setting[] = [
  {
    name: 'Range',
    value: (r) => {
      const m = runMeta(r);
      return m.start && m.end ? `${longDate(m.start)} → ${longDate(m.end)}` : '';
    },
  },
  { name: 'Capital', value: (r) => formatMoney(runMeta(r).capital, { dp: 0 }) },
  { name: 'Costs', value: (r) => fee(toNumber(r.config?.commission)) },
  {
    name: 'Slippage',
    value: (r) => `${formatNumber(toNumber(r.config?.slippagePercent), { dp: 2 })}% slippage`,
  },
  {
    name: 'Benchmark',
    value: (r) => {
      const b = runMeta(r).benchmark;
      return b ? `against ${b}` : 'no benchmark';
    },
  },
];

/** Whether two runs used the same settings, and what differs when they didn't. */
export function compareSettings(a: BacktestRun, b: BacktestRun): SettingsComparison {
  const shared: string[] = [];
  const differences: string[] = [];
  for (const s of SETTINGS) {
    const va = s.value(a);
    const vb = s.value(b);
    if (va === vb) {
      if (va) shared.push(va);
    } else {
      differences.push(`${s.name} ${va || 'unset'} and ${vb || 'unset'}`);
    }
  }
  return { identical: differences.length === 0, shared, differences };
}

/** Months in the range, and how many had at least one day the runs held different symbols. */
export function monthsHeldDifferently(
  dates: readonly Date[],
  aLanes: readonly HoldingLane[],
  bLanes: readonly HoldingLane[]
): { differing: number; total: number } {
  const all = new Set<string>();
  const differing = new Set<string>();
  for (const d of dates) {
    const m = monthKey(d);
    all.add(m);
    if (differing.has(m)) continue;
    if (heldSymbolsOn(aLanes, d).join(',') !== heldSymbolsOn(bLanes, d).join(',')) differing.add(m);
  }
  return { differing: differing.size, total: all.size };
}

/** "Feb to May 2023", or "Nov 2022 to Feb 2023" across a year end; one month reads alone. */
export function stretchMonths(from: Date, to: Date): string {
  const a = monthLabel(monthKey(from));
  const b = monthLabel(monthKey(to));
  if (a === b) return a;
  if (from.getUTCFullYear() === to.getUTCFullYear()) return `${a.split(' ')[0]} to ${b}`;
  return `${a} to ${b}`;
}

/** The lines that changed between two versions' code; null when either text is missing. */
export function changedLines(before: string | null, after: string | null): CodeLine[] | null {
  if (before === null || after === null) return null;
  return diffCode(before.trim(), after.trim()).filter(
    (l) => l.kind !== 'same' && l.text.trim() !== ''
  );
}

/** Gaps smaller than this round to 0.0% and read as level. */
const LEVEL = 0.0005;

/** Where the first run ended against the second: "4.7% ahead", "1.2% behind" or level. */
export function endGap(ratio: number): { text: string; tone?: 'gain' | 'loss' } {
  if (!Number.isFinite(ratio) || Math.abs(ratio) < LEVEL) return { text: 'level' };
  return ratio > 0
    ? { text: `${formatPct(ratio, { dp: 1 })} ahead`, tone: 'gain' }
    : { text: `${formatPct(-ratio, { dp: 1 })} behind`, tone: 'loss' };
}

/** "QQQ", "QQQ and VTI", "GLD, IWM and QQQ". */
export function symbolList(symbols: readonly string[]): string {
  if (symbols.length <= 1) return symbols.join('');
  return `${symbols.slice(0, -1).join(', ')} and ${symbols[symbols.length - 1]}`;
}
