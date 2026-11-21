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
  /** The account the ledger booked the row on; null or missing when it doesn't say. */
  account?: AccountKind | null;
  /** The sleeve whose cash or positions the row moves; empty or missing when unknown. */
  sleeveId?: string;
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
 * Puts each ledger row on a lane: the sleeve the ledger books it to when that sleeve is known,
 * else fills on the sleeve whose order made them and allocations on the sleeve the description
 * names. Deposits, withdrawals and releases go on unallocated cash, and the rest on "other".
 */
export function statementRows<T extends ActivityInput>(
  rows: readonly T[],
  fills: readonly SleeveFill[],
  sleeves: readonly { sleeveId: string | null; name: string; live?: boolean }[],
  byLedgerId: ReadonlyMap<string, SleeveFill> = new Map()
): StatementRow<T>[] {
  const byName = new Map(
    sleeves.filter((s) => s.sleeveId).map((s) => [s.name, s.sleeveId as string])
  );
  const known = new Set(sleeves.map((s) => s.sleeveId).filter((id): id is string => !!id));
  const accounts = accountsByRow(rows, sleeves);
  return rows.map((row) => {
    const flow = statementFlow(row);
    const base = { row, paidIn: flow.paidIn, paidOut: flow.paidOut };
    const own = row.sleeveId && known.has(row.sleeveId) ? row.sleeveId : null;
    switch (row.kind) {
      case 'buy':
      case 'sell': {
        const fill = byLedgerId.get(row.id) ?? fillFor(row, fills);
        return {
          ...base,
          lane: own ?? fill?.sleeveId ?? OTHER_LANE,
          tag: row.kind.toUpperCase(),
          entry: row.qty
            ? `${shares(row.qty)} ${row.symbol} at ${formatMoney(row.price)}`
            : row.label,
        };
      }
      case 'allocation': {
        const lane = own ?? byName.get(row.sublabel) ?? OTHER_LANE;
        return {
          ...base,
          lane,
          tag: 'IN',
          entry: `Allocated from unallocated${lane !== OTHER_LANE ? '' : ` to ${row.sublabel}`}`,
        };
      }
      case 'release':
        return { ...base, lane: UNALLOCATED_LANE, tag: 'IN', entry: 'Released from a sleeve' };
      case 'deposit':
        return {
          ...base,
          lane: UNALLOCATED_LANE,
          tag: 'IN',
          entry: depositEntry(accounts.get(row.id)),
        };
      case 'withdrawal':
        return {
          ...base,
          lane: UNALLOCATED_LANE,
          tag: 'OUT',
          entry: withdrawalEntry(accounts.get(row.id)),
        };
      case 'dividend':
        return {
          ...base,
          lane: own ?? OTHER_LANE,
          tag: 'DIV',
          entry: `Dividend${row.symbol ? ` from ${row.symbol}` : ''}`,
        };
      default:
        return {
          ...base,
          lane: own ?? OTHER_LANE,
          tag: row.kind === 'fee' ? 'FEE' : row.kind === 'interest' ? 'INT' : '·',
          entry: [row.label, row.sublabel].filter(Boolean).join(' · '),
        };
    }
  });
}

export type AccountKind = 'live' | 'paper';

/** Allocations follow their deposit within this window when money is added for a new sleeve. */
const DEPOSIT_PAIR_MS = 30 * 60_000;

/**
 * The account each row was booked on. The ledger names it on each transaction; for an older row
 * that doesn't, a deposit followed within half an hour by an allocation of exactly the same
 * amount to a known sleeve belongs to that sleeve's account. Rows still unknown are left out.
 */
export function accountsByRow(
  rows: readonly Pick<ActivityInput, 'id' | 'kind' | 'sublabel' | 'amount' | 'at' | 'account'>[],
  sleeves: readonly { name: string; live?: boolean }[]
): Map<string, AccountKind> {
  const out = new Map<string, AccountKind>();
  for (const r of rows) if (r.account) out.set(r.id, r.account);
  const liveOf = new Map(
    sleeves.filter((s) => s.live !== undefined).map((s) => [s.name, s.live as boolean])
  );
  const allocations = rows
    .filter((r) => r.kind === 'allocation' && liveOf.has(r.sublabel))
    .sort((a, b) => a.at.getTime() - b.at.getTime());
  const used = new Set<string>();
  const deposits = rows
    .filter((r) => r.kind === 'deposit' && !out.has(r.id))
    .sort((a, b) => a.at.getTime() - b.at.getTime());
  for (const d of deposits) {
    const t = d.at.getTime();
    const pair = allocations.find(
      (a) =>
        !used.has(a.id) &&
        a.at.getTime() >= t &&
        a.at.getTime() - t <= DEPOSIT_PAIR_MS &&
        Math.abs(a.amount - d.amount) < 0.005
    );
    if (!pair) continue;
    used.add(pair.id);
    out.set(d.id, liveOf.get(pair.sublabel) ? 'live' : 'paper');
  }
  return out;
}

/** The statement line for a deposit, naming the account when it is known. */
export function depositEntry(account: AccountKind | undefined): string {
  if (account === 'live') return 'Live deposit, to unallocated';
  if (account === 'paper') return 'Paper funds, to unallocated';
  return 'Deposit to unallocated';
}

/** The statement line for a withdrawal, naming the account when it is known. */
export function withdrawalEntry(account: AccountKind | undefined): string {
  if (account === 'live') return 'Live withdrawal, from unallocated';
  if (account === 'paper') return 'Paper withdrawal, from unallocated';
  return 'Withdrawn from unallocated';
}

/**
 * The account a statement row belongs to: the one `accountsByRow` found, else its sleeve's.
 * Null when the ledger doesn't say.
 */
export function rowAccount(
  row: StatementRow,
  sleeves: readonly { sleeveId: string | null; live?: boolean }[],
  accounts: ReadonlyMap<string, AccountKind>
): AccountKind | null {
  const booked = accounts.get(row.row.id);
  if (booked) return booked;
  const sleeve = sleeves.find((s) => s.sleeveId !== null && s.sleeveId === row.lane);
  if (sleeve && sleeve.live !== undefined) return sleeve.live ? 'live' : 'paper';
  return null;
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
