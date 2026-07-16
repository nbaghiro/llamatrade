/**
 * Trade Log.
 * Paginated fills with side badges and realized P&L, plus an aggregate footer
 * (gross P&L, commission, profit factor, avg win/loss) sourced from metrics.
 */

import { ChevronLeft, ChevronRight, Download, Loader2 } from 'lucide-react';
import { useMemo, useState } from 'react';

import type { BacktestMetrics, BacktestTrade } from '../../generated/proto/backtest_pb';
import { toDate, toNumber } from '../../store/backtest';

interface TradesTableProps {
  trades: BacktestTrade[];
  totalTrades: number;
  metrics?: BacktestMetrics;
  onLoadAll?: () => void;
  loadingAll?: boolean;
}

const PAGE_SIZE = 10;

function formatDate(trade: BacktestTrade): string {
  const date = toDate(trade.exitTime) ?? toDate(trade.entryTime);
  return date ? date.toLocaleDateString('en-CA') : '—';
}

function formatQty(value: number): string {
  return Number.isInteger(value) ? value.toString() : value.toFixed(2);
}

function formatPrice(value: number): string {
  return `$${value.toFixed(2)}`;
}

function signedCurrency(value: number, digits = 0): string {
  const abs = new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: digits,
  }).format(Math.abs(value));
  return `${value >= 0 ? '+' : '−'}${abs}`;
}

export default function TradesTable({ trades, totalTrades, metrics, onLoadAll, loadingAll }: TradesTableProps) {
  const [page, setPage] = useState(1);

  const sorted = useMemo(() => {
    return [...trades].sort((a, b) => {
      const at = (toDate(a.exitTime) ?? toDate(a.entryTime))?.getTime() ?? 0;
      const bt = (toDate(b.exitTime) ?? toDate(b.entryTime))?.getTime() ?? 0;
      return bt - at;
    });
  }, [trades]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const clampedPage = Math.min(page, totalPages);
  const pageTrades = sorted.slice((clampedPage - 1) * PAGE_SIZE, clampedPage * PAGE_SIZE);
  const truncated = trades.length < totalTrades;

  const grossPnl = metrics
    ? toNumber(metrics.endingCapital) - toNumber(metrics.startingCapital) + toNumber(metrics.totalCommission)
    : trades.reduce((sum, t) => sum + toNumber(t.pnl), 0);
  const commission = metrics
    ? toNumber(metrics.totalCommission)
    : trades.reduce((sum, t) => sum + toNumber(t.commission), 0);
  const profitFactor = metrics ? toNumber(metrics.profitFactor) : 0;
  const avgWin = metrics ? toNumber(metrics.averageWin) : 0;
  const avgLoss = metrics ? Math.abs(toNumber(metrics.averageLoss)) : 0;
  const winLoss = avgLoss > 0 ? avgWin / avgLoss : 0;

  const handleExport = () => {
    const headers = ['Date', 'Symbol', 'Side', 'Quantity', 'Entry Price', 'Exit Price', 'PnL', 'PnL %'];
    const rows = sorted.map((t) => [
      formatDate(t),
      t.symbol,
      t.side === 1 ? 'BUY' : 'SELL',
      formatQty(toNumber(t.quantity)),
      toNumber(t.entryPrice).toFixed(2),
      toNumber(t.exitPrice).toFixed(2),
      toNumber(t.pnl).toFixed(2),
      (toNumber(t.pnlPercent) * 100).toFixed(2) + '%',
    ]);
    const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = 'backtest-trades.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const th = 'font-mono text-[9px] font-bold uppercase tracking-[0.09em] text-ink/50 px-4 py-2.5 border-b-2 border-ink';
  const td = 'px-4 py-2.5 border-b border-line font-mono text-[13px] font-bold';

  return (
    <div className="bg-paper border-2 border-ink shadow-[4px_4px_0_#0d0d0d]">
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b-2 border-ink">
        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.1em]">Trade Log</span>
        <div className="flex items-center gap-2.5">
          {truncated && onLoadAll && (
            <button
              onClick={onLoadAll}
              disabled={loadingAll}
              className="flex items-center gap-1 font-mono text-[10px] font-bold uppercase tracking-[0.05em] text-orange-500 hover:text-orange-600 disabled:opacity-50"
            >
              {loadingAll && <Loader2 className="w-3 h-3 animate-spin" />}
              Load all
            </button>
          )}
          {trades.length > 0 && (
            <button
              onClick={handleExport}
              className="flex items-center gap-1 font-mono text-[10px] font-bold uppercase tracking-[0.05em] text-ink/50 hover:text-ink"
            >
              <Download className="w-3 h-3" />
              CSV
            </button>
          )}
          <span className="font-mono text-[10px] font-bold uppercase tracking-[0.04em] border-[1.5px] border-ink px-1.5 py-[3px]">
            {totalTrades} trades · showing {pageTrades.length}
          </span>
        </div>
      </div>

      {sorted.length === 0 ? (
        <div className="px-4 py-8 font-mono text-[11px] uppercase tracking-[0.05em] text-ink/40 text-center">
          No trades executed
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className={`${th} text-left`}>Date</th>
                <th className={`${th} text-left`}>Symbol</th>
                <th className={`${th} text-left`}>Side</th>
                <th className={`${th} text-right`}>Qty</th>
                <th className={`${th} text-right`}>Price</th>
                <th className={`${th} text-right`}>P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {pageTrades.map((trade, idx) => {
                const buy = trade.side === 1;
                const pnl = toNumber(trade.pnl);
                return (
                  <tr key={`${trade.symbol}-${clampedPage}-${idx}`} className="last:[&>td]:border-b-0 hover:bg-bone">
                    <td className={`${td} text-left`}>{formatDate(trade)}</td>
                    <td className={`${td} text-left font-sans text-[13.5px]`}>{trade.symbol}</td>
                    <td className={`${td} text-left`}>
                      <span
                        className={`font-mono text-[9px] font-bold uppercase tracking-[0.04em] border-[1.5px] border-ink px-1.5 py-0.5 text-bone ${
                          buy ? 'bg-green-500' : 'bg-red-500'
                        }`}
                      >
                        {buy ? 'Buy' : 'Sell'}
                      </span>
                    </td>
                    <td className={`${td} text-right tabular-nums`}>{formatQty(toNumber(trade.quantity))}</td>
                    <td className={`${td} text-right tabular-nums`}>{formatPrice(toNumber(trade.entryPrice))}</td>
                    <td className={`${td} text-right tabular-nums ${pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {signedCurrency(pnl)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex items-center justify-between gap-3 flex-wrap px-4 py-3 border-t-2 border-ink font-mono text-[10.5px] font-bold uppercase tracking-[0.05em] text-ink/55">
        <span>
          Gross P&amp;L <span className={grossPnl >= 0 ? 'text-green-600' : 'text-red-600'}>{signedCurrency(grossPnl)}</span>
          {' · '}Commission −{new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(commission)}
        </span>
        <div className="flex items-center gap-3">
          {totalPages > 1 && (
            <span className="flex items-center gap-1.5 text-ink/60">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={clampedPage === 1}
                className="disabled:opacity-30"
                aria-label="Previous page"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
              </button>
              <span className="tabular-nums">{clampedPage}/{totalPages}</span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={clampedPage === totalPages}
                className="disabled:opacity-30"
                aria-label="Next page"
              >
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </span>
          )}
          <span>
            Profit factor {profitFactor.toFixed(2)} · Avg win/loss {winLoss.toFixed(1)}x
          </span>
        </div>
      </div>
    </div>
  );
}
