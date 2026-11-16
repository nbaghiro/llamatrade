/** View-model maths for the Portfolio pages: weights, account totals, before and after, months. */

export interface Holding {
  symbol: string;
  marketValue: number;
}

export interface WeightRow<T extends Holding> {
  holding: T;
  /** Share of the sleeve's value, 0 to 1. */
  weight: number;
  /** Target share when the strategy publishes one. */
  target?: number;
  /** weight − target, when a target is known. */
  drift?: number;
}

const finite = (v: number) => (Number.isFinite(v) ? v : 0);
const cents = (v: number) => Math.round(v * 100) / 100;

/** Each holding's share of the sleeve, largest first. Sleeve cash is part of the base. */
export function weightRows<T extends Holding>(
  holdings: readonly T[],
  sleeveValue: number,
  targets: Readonly<Record<string, number>> = {}
): WeightRow<T>[] {
  const base = finite(sleeveValue);
  return holdings
    .map((holding) => {
      const weight = base > 0 ? Math.max(0, finite(holding.marketValue)) / base : 0;
      const target = targets[holding.symbol];
      return target === undefined
        ? { holding, weight }
        : { holding, weight, target, drift: weight - target };
    })
    .sort((a, b) => b.weight - a.weight || a.holding.symbol.localeCompare(b.holding.symbol));
}

/** Whether any row carries a target, which decides the "Weight · target" column header. */
export function hasTargets(rows: readonly WeightRow<Holding>[]): boolean {
  return rows.some((r) => r.target !== undefined);
}

/** The bar scale for a set of weight rows, so the largest weight or target fills most of the track. */
export function weightScale(rows: readonly WeightRow<Holding>[]): number {
  const top = rows.reduce((m, r) => Math.max(m, r.weight, r.target ?? 0), 0);
  if (top <= 0) return 1;
  return Math.min(1, Math.ceil((top * 100) / 10) / 10 + 0.1);
}

export interface AccountTotals {
  sleeves: number;
  unallocated: number;
  total: number;
}

/**
 * Sleeves plus unallocated cash, so the ruled total always adds up. When the ledger's unallocated
 * figure is missing, the account summary's total stands in and unallocated is the remainder.
 */
export function accountTotals(
  sleeveValues: readonly number[],
  unallocated: number | null,
  summaryTotal = 0
): AccountTotals {
  const sleeves = cents(sleeveValues.reduce((s, v) => s + Math.max(0, finite(v)), 0));
  if (unallocated !== null && Number.isFinite(unallocated)) {
    const cash = cents(Math.max(0, unallocated));
    return { sleeves, unallocated: cash, total: cents(sleeves + cash) };
  }
  const total = cents(Math.max(sleeves, finite(summaryTotal)));
  return { sleeves, unallocated: cents(total - sleeves), total };
}

export interface Segment {
  id: string;
  value: number;
  /** Share of the account, 0 to 1. */
  share: number;
}

/** One allocation bar: each sleeve, then unallocated cash, as shares of the total. */
export function allocationSegments(
  sleeves: readonly { id: string; value: number }[],
  unallocated: number
): { sleeves: Segment[]; unallocated: Segment } {
  const cash = Math.max(0, finite(unallocated));
  const values = sleeves.map((s) => ({ id: s.id, value: Math.max(0, finite(s.value)) }));
  const total = values.reduce((sum, s) => sum + s.value, cash);
  const share = (v: number) => (total > 0 ? v / total : 0);
  return {
    sleeves: values.map((s) => ({ ...s, share: share(s.value) })),
    unallocated: { id: 'unallocated', value: cash, share: share(cash) },
  };
}

/** Today's change in dollars from a value that already includes it and today's return in percent. */
export function dayChange(value: number, returnPct: number): number {
  const r = finite(returnPct) / 100;
  if (r <= -1) return 0;
  return (finite(value) * r) / (1 + r);
}

/** Today's change as a fraction of yesterday's value. */
export function dayChangeFraction(total: number, change: number): number {
  const before = finite(total) - finite(change);
  return before > 0 ? finite(change) / before : 0;
}

export interface FundsPreviewRow {
  key: 'unallocated' | 'sleeves' | 'total';
  label: string;
  now: number;
  after: number;
}

/** Paper funds land in unallocated cash only, so sleeves stay the same and the total grows. */
export function fundsPreview(totals: AccountTotals, amount: number): FundsPreviewRow[] {
  const add = Number.isFinite(amount) && amount > 0 ? amount : 0;
  return [
    {
      key: 'unallocated',
      label: 'Unallocated cash',
      now: totals.unallocated,
      after: cents(totals.unallocated + add),
    },
    { key: 'sleeves', label: 'Sleeves', now: totals.sleeves, after: totals.sleeves },
    { key: 'total', label: 'Total equity', now: totals.total, after: cents(totals.total + add) },
  ];
}

export const QUICK_AMOUNTS = [10_000, 25_000, 50_000, 100_000] as const;
export const MAX_PAPER_DEPOSIT = 10_000_000;

/** "+25K" for a quick-amount button. */
export function quickLabel(amount: number): string {
  return amount >= 1_000_000 ? `+${amount / 1_000_000}M` : `+${amount / 1_000}K`;
}

/** Reads a typed dollar amount ("25,000", "$1,250.50"); null when it isn't a usable amount. */
export function parseAmount(input: string): number | null {
  const cleaned = input.replace(/[$,\s]/g, '');
  if (!/^\d+(\.\d{0,2})?$/.test(cleaned)) return null;
  const value = Number(cleaned);
  return value > 0 ? value : null;
}

/** Why an amount can't be deposited, or null when it can. */
export function amountProblem(amount: number | null): string | null {
  if (amount === null) return 'Enter an amount in dollars, for example 25,000.';
  if (amount > MAX_PAPER_DEPOSIT) return 'Add up to $10,000,000 at a time.';
  return null;
}

export interface MonthGroup<T> {
  key: string;
  label: string;
  rows: T[];
  paidIn: number;
  paidOut: number;
}

const MONTH = new Intl.DateTimeFormat('en-US', { month: 'long' });
const MONTH_YEAR = new Intl.DateTimeFormat('en-US', { month: 'long', year: 'numeric' });

/**
 * Groups newest-first rows by calendar month in local time, keeping their order. The year is
 * shown only for months outside the current year.
 */
export function groupByMonth<T extends { at: Date }>(
  rows: readonly T[],
  flow: (row: T) => { paidIn: number; paidOut: number },
  now: Date = new Date()
): MonthGroup<T>[] {
  const groups: MonthGroup<T>[] = [];
  const byKey = new Map<string, MonthGroup<T>>();
  for (const row of rows) {
    const d = row.at;
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
    let g = byKey.get(key);
    if (!g) {
      const label = d.getFullYear() === now.getFullYear() ? MONTH.format(d) : MONTH_YEAR.format(d);
      g = { key, label, rows: [], paidIn: 0, paidOut: 0 };
      byKey.set(key, g);
      groups.push(g);
    }
    const f = flow(row);
    g.rows.push(row);
    g.paidIn += f.paidIn;
    g.paidOut += f.paidOut;
  }
  return groups;
}

export type ActivityFilter = 'all' | 'funding' | 'allocations' | 'trades' | 'income';

export const ACTIVITY_FILTERS: readonly { key: ActivityFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'funding', label: 'Funding' },
  { key: 'allocations', label: 'Allocations' },
  { key: 'trades', label: 'Trades' },
  { key: 'income', label: 'Income' },
];

export type FlowKind =
  | 'deposit'
  | 'withdrawal'
  | 'allocation'
  | 'release'
  | 'buy'
  | 'sell'
  | 'dividend'
  | 'interest'
  | 'fee'
  | 'other';

const PAID_IN: ReadonlySet<FlowKind> = new Set([
  'deposit',
  'release',
  'sell',
  'dividend',
  'interest',
]);
const PAID_OUT: ReadonlySet<FlowKind> = new Set(['withdrawal', 'allocation', 'buy', 'fee']);

/** Statement columns: which side of the ledger each entry's amount lands on. */
export function statementFlow(row: { kind: FlowKind; amount: number }): {
  paidIn: number;
  paidOut: number;
} {
  const amount = Math.abs(finite(row.amount));
  if (PAID_IN.has(row.kind)) return { paidIn: amount, paidOut: 0 };
  if (PAID_OUT.has(row.kind)) return { paidIn: 0, paidOut: amount };
  return { paidIn: 0, paidOut: 0 };
}

const CSV_HEADER = ['Date', 'Entry', 'Detail', 'Type', 'Paid in', 'Paid out'];

function csvCell(v: string): string {
  return /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
}

/** The activity table as CSV, one line per entry, amounts in plain decimals. */
export function activityCsv(
  rows: readonly { at: Date; label: string; sublabel: string; kind: FlowKind; amount: number }[],
  typeLabel: (kind: FlowKind) => string
): string {
  const lines = rows.map((r) => {
    const f = statementFlow(r);
    return [
      r.at.toISOString(),
      r.label,
      r.sublabel,
      typeLabel(r.kind),
      f.paidIn ? f.paidIn.toFixed(2) : '',
      f.paidOut ? f.paidOut.toFixed(2) : '',
    ]
      .map(csvCell)
      .join(',');
  });
  return [CSV_HEADER.join(','), ...lines].join('\n');
}

/** An RPC error message as a sentence: no "[code]" prefix, capitalised, ending in a full stop. */
export function causeSentence(message: string): string {
  const text = message.replace(/^\[[a-z_]+\]\s*/i, '').trim();
  if (!text) return '';
  const capped = text[0].toUpperCase() + text.slice(1);
  return /[.!?]$/.test(capped) ? capped : `${capped}.`;
}
