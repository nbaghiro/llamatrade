import { formatMoney, formatNumber } from '../../lib/format';
import { statementFlow, type FlowKind } from '../../lib/portfolioView';

import { fillFor, type SleeveFill } from './history';

export const UNALLOCATED_LANE = 'unallocated';
export const OTHER_LANE = 'other';

export interface ActivityInput {
  id: string;
  kind: FlowKind;
  label: string;
  sublabel: string;
  symbol: string;
  qty: number;
  price: number;
  amount: number;
  at: Date;
}

export interface StatementRow<T extends ActivityInput = ActivityInput> {
  row: T;
  /** A ledger sleeve id, or the unallocated or other lane. */
  lane: string;
  /** What the row did, in a few words. */
  entry: string;
  /** BUY, SELL, IN, OUT or DIV. */
  tag: string;
  paidIn: number;
  paidOut: number;
}

const shares = (q: number) => formatNumber(q, { dp: q % 1 ? 2 : 0 });

/**
 * Puts each ledger row on a lane: fills on the sleeve whose order made them, allocations on the
 * sleeve the ledger names, deposits and releases on unallocated cash, and the rest on "other".
 */
export function statementRows<T extends ActivityInput>(
  rows: readonly T[],
  fills: readonly SleeveFill[],
  sleeves: readonly { sleeveId: string | null; name: string }[]
): StatementRow<T>[] {
  const byName = new Map(
    sleeves.filter((s) => s.sleeveId).map((s) => [s.name, s.sleeveId as string])
  );
  return rows.map((row) => {
    const flow = statementFlow(row);
    const base = { row, paidIn: flow.paidIn, paidOut: flow.paidOut };
    switch (row.kind) {
      case 'buy':
      case 'sell': {
        const fill = fillFor(row, fills);
        return {
          ...base,
          lane: fill?.sleeveId ?? OTHER_LANE,
          tag: row.kind.toUpperCase(),
          entry: row.qty
            ? `${shares(row.qty)} ${row.symbol} at ${formatMoney(row.price)}`
            : row.label,
        };
      }
      case 'allocation':
        return {
          ...base,
          lane: byName.get(row.sublabel) ?? OTHER_LANE,
          tag: 'IN',
          entry: `Allocated from unallocated${byName.has(row.sublabel) ? '' : ` to ${row.sublabel}`}`,
        };
      case 'release':
        return { ...base, lane: UNALLOCATED_LANE, tag: 'IN', entry: 'Released from a sleeve' };
      case 'deposit':
        return {
          ...base,
          lane: UNALLOCATED_LANE,
          tag: 'IN',
          entry: 'Paper deposit to unallocated',
        };
      case 'withdrawal':
        return { ...base, lane: UNALLOCATED_LANE, tag: 'OUT', entry: 'Withdrawn from unallocated' };
      case 'dividend':
        return {
          ...base,
          lane: OTHER_LANE,
          tag: 'DIV',
          entry: `Dividend${row.symbol ? ` from ${row.symbol}` : ''}`,
        };
      default:
        return {
          ...base,
          lane: OTHER_LANE,
          tag: row.kind === 'fee' ? 'FEE' : row.kind === 'interest' ? 'INT' : '·',
          entry: [row.label, row.sublabel].filter(Boolean).join(' · '),
        };
    }
  });
}

/** "2026-11": a row's calendar month in local time. */
export function monthKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

/** The months that have entries, newest first. */
export function monthsWithEntries(rows: readonly { at: Date }[]): string[] {
  return [...new Set(rows.map((r) => monthKey(r.at)))].sort().reverse();
}

/** The first and last moment of a "2026-11" month. */
export function monthBounds(key: string): { start: Date; end: Date } {
  const [y, m] = key.split('-').map(Number);
  return { start: new Date(y, m - 1, 1), end: new Date(y, m, 0, 23, 59, 59, 999) };
}

export function totals(rows: readonly { paidIn: number; paidOut: number }[]): {
  paidIn: number;
  paidOut: number;
} {
  return rows.reduce((s, r) => ({ paidIn: s.paidIn + r.paidIn, paidOut: s.paidOut + r.paidOut }), {
    paidIn: 0,
    paidOut: 0,
  });
}
