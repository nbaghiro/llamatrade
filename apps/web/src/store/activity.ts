/**
 * Wallet activity — the account's economic ledger (deposits, allocations,
 * fills, dividends, fees) rendered as newest-first view rows.
 *
 * Sourced from PortfolioService.ListTransactions, which folds the double-entry
 * ledger event log. `signed` expresses each row's effect on *free cash*: money
 * in (+), money out (−), or neutral (0) when the movement happens inside a
 * strategy sleeve and never touches the allocatable pool.
 */

import { create } from 'zustand';

import { TransactionType, type Transaction } from '../generated/proto/portfolio_pb';
import { portfolioClient } from '../services/grpc-client';

import { getTenantContext } from './auth';

const PAGE_SIZE = 25;

export type ActivityKind =
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

export type ActivityGroup = 'funding' | 'allocations' | 'trades';

export interface ActivityRow {
  id: string;
  kind: ActivityKind;
  group: ActivityGroup;
  label: string;
  sublabel: string;
  amount: number; // absolute magnitude
  signed: number; // effect on free cash: + in, − out, 0 neutral (inside a sleeve)
  at: Date;
}

function toNumber(d?: { value: string }): number {
  return d?.value ? parseFloat(d.value) : 0;
}

function toDate(ts?: { seconds: bigint }): Date {
  return ts?.seconds ? new Date(Number(ts.seconds) * 1000) : new Date(0);
}

function fmtUsd(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(value);
}

function tradeSublabel(t: Transaction): string {
  const qty = toNumber(t.quantity);
  const price = toNumber(t.price);
  if (qty && price) return `${qty} @ ${fmtUsd(price)}`;
  return t.symbol || '—';
}

function mapRow(t: Transaction): ActivityRow {
  const amount = toNumber(t.amount);
  const base = { id: t.id, amount, at: toDate(t.timestamp) };
  switch (t.type) {
    case TransactionType.DEPOSIT:
      return {
        ...base,
        kind: 'deposit',
        group: 'funding',
        label: 'Deposit',
        sublabel: t.description || 'Paper credit',
        signed: amount,
      };
    case TransactionType.WITHDRAWAL:
      return {
        ...base,
        kind: 'withdrawal',
        group: 'funding',
        label: 'Withdrawal',
        sublabel: t.description || 'Paper credit',
        signed: -amount,
      };
    case TransactionType.TRANSFER_IN:
    case TransactionType.TRANSFER_OUT: {
      // An allocation moves free cash into a strategy sleeve; a release returns
      // it. The row is described by the sleeve it concerns — a release names the
      // Unallocated sleeve, an allocation names the strategy.
      const isRelease = /unalloc/i.test(t.description || '');
      return isRelease
        ? {
            ...base,
            kind: 'release',
            group: 'allocations',
            label: 'Released to cash',
            sublabel: 'From strategy sleeve',
            signed: amount,
          }
        : {
            ...base,
            kind: 'allocation',
            group: 'allocations',
            label: 'Allocated',
            sublabel: t.description || 'Strategy sleeve',
            signed: -amount,
          };
    }
    case TransactionType.BUY:
      return {
        ...base,
        kind: 'buy',
        group: 'trades',
        label: `Buy ${t.symbol}`.trim(),
        sublabel: tradeSublabel(t),
        signed: 0,
      };
    case TransactionType.SELL:
      return {
        ...base,
        kind: 'sell',
        group: 'trades',
        label: `Sell ${t.symbol}`.trim(),
        sublabel: tradeSublabel(t),
        signed: 0,
      };
    case TransactionType.DIVIDEND:
      return {
        ...base,
        kind: 'dividend',
        group: 'trades',
        label: 'Dividend',
        sublabel: t.symbol || '—',
        signed: 0,
      };
    case TransactionType.INTEREST:
      return {
        ...base,
        kind: 'interest',
        group: 'trades',
        label: 'Interest',
        sublabel: '—',
        signed: 0,
      };
    case TransactionType.FEE:
      return {
        ...base,
        kind: 'fee',
        group: 'trades',
        label: 'Fee',
        sublabel: t.symbol || '—',
        signed: 0,
      };
    default:
      return {
        ...base,
        kind: 'other',
        group: 'trades',
        label: 'Activity',
        sublabel: '—',
        signed: 0,
      };
  }
}

interface ActivityState {
  rows: ActivityRow[];
  loading: boolean;
  loadingMore: boolean;
  error: string | null;
  page: number;
  hasMore: boolean;
  fetch: () => Promise<void>;
  loadMore: () => Promise<void>;
}

async function fetchPage(page: number): Promise<{ rows: ActivityRow[]; hasMore: boolean }> {
  const context = getTenantContext();
  const res = await portfolioClient.listTransactions({
    context,
    pagination: { page, pageSize: PAGE_SIZE },
  });
  return {
    rows: res.transactions.map(mapRow),
    hasMore: res.pagination?.hasNext ?? false,
  };
}

export const useActivityStore = create<ActivityState>((set, get) => ({
  rows: [],
  loading: false,
  loadingMore: false,
  error: null,
  page: 1,
  hasMore: false,

  fetch: async () => {
    set({ loading: true, error: null });
    try {
      const { rows, hasMore } = await fetchPage(1);
      set({ rows, hasMore, page: 1, loading: false });
    } catch (e) {
      set({ loading: false, error: e instanceof Error ? e.message : 'Failed to load activity' });
    }
  },

  loadMore: async () => {
    const { loadingMore, hasMore, page } = get();
    if (loadingMore || !hasMore) return;
    set({ loadingMore: true, error: null });
    try {
      const next = page + 1;
      const { rows, hasMore: more } = await fetchPage(next);
      set((s) => ({ rows: [...s.rows, ...rows], hasMore: more, page: next, loadingMore: false }));
    } catch (e) {
      set({ loadingMore: false, error: e instanceof Error ? e.message : 'Failed to load activity' });
    }
  },
}));
