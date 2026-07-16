/**
 * Wallet activity drawer — a right slide-over holding the account's full
 * economic history: funding (deposits/withdrawals), strategy allocations, and
 * in-sleeve trades/dividends/fees. Amounts are framed from the free-cash
 * perspective (see the store).
 */

import {
  ArrowDownLeft,
  ArrowUpRight,
  Coins,
  Loader2,
  MoveLeft,
  MoveRight,
  Percent,
  Receipt,
  TrendingDown,
  TrendingUp,
  X,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { type ActivityGroup, type ActivityKind, type ActivityRow, useActivityStore } from '../../store/activity';

type Filter = 'all' | ActivityGroup;

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'funding', label: 'Funding' },
  { key: 'allocations', label: 'Allocations' },
  { key: 'trades', label: 'Trades' },
];

const ICONS: Record<ActivityKind, LucideIcon> = {
  deposit: ArrowDownLeft,
  withdrawal: ArrowUpRight,
  allocation: MoveRight,
  release: MoveLeft,
  buy: TrendingUp,
  sell: TrendingDown,
  dividend: Coins,
  interest: Percent,
  fee: Receipt,
  other: Receipt,
};

function fmtAmount(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(Math.abs(value));
}

function fmtDate(at: Date): string {
  if (!at.getTime()) return '—';
  const day = at.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  const time = at.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  return `${day} · ${time}`;
}

function ActivityLine({ row }: { row: ActivityRow }) {
  const Icon = ICONS[row.kind];
  const inflow = row.signed > 0;
  const outflow = row.signed < 0;
  const iconTone = inflow
    ? 'border-green-700 text-green-700'
    : row.kind === 'allocation'
      ? 'border-orange-500 text-orange-600'
      : 'border-ink/25 text-ink/60';
  const amountTone = inflow ? 'text-green-700' : outflow ? 'text-ink' : 'text-ink/45';
  const sign = inflow ? '+' : outflow ? '−' : '';

  return (
    <div className="flex items-center gap-3 border-b border-ink/10 px-5 py-2.5">
      <span className={`grid h-7 w-7 shrink-0 place-items-center border-2 ${iconTone}`}>
        <Icon className="h-[14px] w-[14px]" strokeWidth={2.25} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-medium text-ink">{row.label}</div>
        <div className="truncate font-mono text-[11px] text-ink/50">{row.sublabel}</div>
      </div>
      <div className="shrink-0 text-right">
        <div className={`font-mono text-[13px] font-bold tabular-nums ${amountTone}`}>
          {sign}
          {fmtAmount(row.amount)}
        </div>
        <div className="font-mono text-[10px] uppercase tracking-wide text-ink/40">
          {fmtDate(row.at)}
        </div>
      </div>
    </div>
  );
}

interface Props {
  open: boolean;
  onClose: () => void;
}

export function WalletActivityDrawer({ open, onClose }: Props) {
  const { rows, loading, loadingMore, error, hasMore, loadMore } = useActivityStore();
  const [filter, setFilter] = useState<Filter>('all');

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const visible = useMemo(
    () => (filter === 'all' ? rows : rows.filter((r) => r.group === filter)),
    [rows, filter],
  );

  return (
    <>
      <div
        aria-hidden="true"
        onClick={onClose}
        className={`fixed inset-0 z-40 bg-ink/40 transition-opacity duration-200 ${
          open ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Wallet activity"
        className={`fixed right-0 top-0 z-50 flex h-full w-full max-w-[460px] flex-col border-l-2 border-ink bg-paper shadow-[-6px_0_0_rgb(var(--lt-ink))] transition-transform duration-200 ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="flex items-center justify-between border-b-2 border-ink px-5 py-3.5">
          <div>
            <h2 className="font-display text-xl uppercase tracking-tight text-ink">Activity</h2>
            <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.1em] text-ink/45">
              Deposits · allocations · trades
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close activity"
            className="grid h-8 w-8 place-items-center border-2 border-ink text-ink transition-colors hover:bg-ink hover:text-bone"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex items-center gap-1.5 border-b-2 border-ink px-5 py-2.5">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              className={`border-2 px-2 py-0.5 font-mono text-[9.5px] font-bold uppercase tracking-[0.07em] transition-colors ${
                filter === f.key
                  ? 'border-ink bg-ink text-bone'
                  : 'border-ink/20 text-ink/55 hover:border-ink hover:text-ink'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-4 w-4 animate-spin text-ink/40" />
            </div>
          ) : visible.length === 0 ? (
            <p className="px-5 py-12 text-center text-[13px] text-ink/50">
              {rows.length === 0
                ? 'No activity yet — fund your wallet and deploy a strategy to get started.'
                : 'Nothing in this view.'}
            </p>
          ) : (
            <>
              {visible.map((row) => (
                <ActivityLine key={row.id} row={row} />
              ))}
              {hasMore && (
                <div className="px-5 py-3">
                  <button
                    type="button"
                    onClick={() => void loadMore()}
                    disabled={loadingMore}
                    className="flex w-full items-center justify-center gap-2 border-2 border-ink/20 py-2 font-mono text-[11px] font-bold uppercase tracking-[0.07em] text-ink/60 transition-colors hover:border-ink hover:text-ink disabled:opacity-50"
                  >
                    {loadingMore && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    {loadingMore ? 'Loading' : 'Load more'}
                  </button>
                </div>
              )}
            </>
          )}
        </div>

        {error && (
          <div className="border-t-2 border-red-600 bg-red-50 px-5 py-2 font-mono text-[11px] font-bold text-red-700">
            {error}
          </div>
        )}
      </aside>
    </>
  );
}
