/**
 * Trades Table Component
 * Displays backtest trade history with sorting and filtering.
 */

import { ArrowUpDown, ChevronDown, ChevronLeft, ChevronRight, Download } from 'lucide-react';
import { useMemo, useState } from 'react';

import type { BacktestTrade } from '../../generated/proto/backtest_pb';
import { toDate, toNumber } from '../../store/backtest';

interface TradesTableProps {
  trades: BacktestTrade[];
}

type SortField = 'entryTime' | 'symbol' | 'pnl' | 'pnlPercent' | 'holdingPeriod';
type SortDirection = 'asc' | 'desc';

const PAGE_SIZE = 10;

function formatCurrency(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)}`;
}

function formatPercent(value: number): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(2)}%`;
}

function formatDateTime(date: Date | null): string {
  if (!date) return '-';
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function TradesTable({ trades }: TradesTableProps) {
  const [sortField, setSortField] = useState<SortField>('entryTime');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const [symbolFilter, setSymbolFilter] = useState<string>('all');
  const [page, setPage] = useState(1);

  // Get unique symbols for filter
  const symbols = useMemo(() => {
    const unique = new Set(trades.map((t) => t.symbol));
    return Array.from(unique).sort();
  }, [trades]);

  // Process trades with sorting and filtering
  const processedTrades = useMemo(() => {
    let result = trades.map((trade) => ({
      ...trade,
      entryTimeDate: toDate(trade.entryTime),
      exitTimeDate: toDate(trade.exitTime),
      pnlValue: toNumber(trade.pnl),
      pnlPercentValue: toNumber(trade.pnlPercent),
      quantityValue: toNumber(trade.quantity),
      entryPriceValue: toNumber(trade.entryPrice),
      exitPriceValue: toNumber(trade.exitPrice),
      commissionValue: toNumber(trade.commission),
    }));

    // Filter by symbol
    if (symbolFilter !== 'all') {
      result = result.filter((t) => t.symbol === symbolFilter);
    }

    // Sort
    result.sort((a, b) => {
      let comparison = 0;
      switch (sortField) {
        case 'entryTime':
          comparison = (a.entryTimeDate?.getTime() ?? 0) - (b.entryTimeDate?.getTime() ?? 0);
          break;
        case 'symbol':
          comparison = a.symbol.localeCompare(b.symbol);
          break;
        case 'pnl':
          comparison = a.pnlValue - b.pnlValue;
          break;
        case 'pnlPercent':
          comparison = a.pnlPercentValue - b.pnlPercentValue;
          break;
        case 'holdingPeriod':
          comparison = a.holdingPeriodBars - b.holdingPeriodBars;
          break;
      }
      return sortDirection === 'asc' ? comparison : -comparison;
    });

    return result;
  }, [trades, sortField, sortDirection, symbolFilter]);

  // Pagination
  const totalPages = Math.ceil(processedTrades.length / PAGE_SIZE);
  const paginatedTrades = processedTrades.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  // Calculate summary
  const summary = useMemo(() => {
    const filtered = symbolFilter === 'all' ? trades : trades.filter((t) => t.symbol === symbolFilter);
    return {
      totalPnl: filtered.reduce((sum, t) => sum + toNumber(t.pnl), 0),
      totalCommission: filtered.reduce((sum, t) => sum + toNumber(t.commission), 0),
      count: filtered.length,
    };
  }, [trades, symbolFilter]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  const handleExport = () => {
    const headers = [
      'Symbol',
      'Side',
      'Quantity',
      'Entry Price',
      'Exit Price',
      'Entry Time',
      'Exit Time',
      'P&L',
      'P&L %',
      'Commission',
      'Holding Period (bars)',
    ];
    const rows = processedTrades.map((t) => [
      t.symbol,
      t.side === 1 ? 'BUY' : 'SELL',
      t.quantityValue.toFixed(4),
      t.entryPriceValue.toFixed(2),
      t.exitPriceValue.toFixed(2),
      t.entryTimeDate?.toISOString() ?? '',
      t.exitTimeDate?.toISOString() ?? '',
      t.pnlValue.toFixed(2),
      (t.pnlPercentValue * 100).toFixed(2) + '%',
      t.commissionValue.toFixed(2),
      t.holdingPeriodBars.toString(),
    ]);

    const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'backtest-trades.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const SortHeader = ({ field, children }: { field: SortField; children: React.ReactNode }) => (
    <button
      onClick={() => handleSort(field)}
      className="flex items-center gap-1 font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300"
    >
      {children}
      <ArrowUpDown
        className={`w-3 h-3 ${sortField === field ? 'text-primary-500' : 'opacity-50'}`}
      />
    </button>
  );

  if (trades.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
        <div className="flex items-center justify-center h-32 text-gray-400 dark:text-gray-500">
          No trades executed during backtest
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 dark:border-gray-800">
        <div className="flex items-center gap-4">
          <h3 className="font-medium text-gray-900 dark:text-gray-100">Trades</h3>
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {processedTrades.length} trades
          </span>
        </div>
        <div className="flex items-center gap-3">
          {/* Symbol Filter */}
          <div className="relative">
            <select
              value={symbolFilter}
              onChange={(e) => {
                setSymbolFilter(e.target.value);
                setPage(1);
              }}
              className="appearance-none pl-3 pr-8 py-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 outline-none"
            >
              <option value="all">All Symbols</option>
              {symbols.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          </div>

          {/* Export Button */}
          <button
            onClick={handleExport}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
          >
            <Download className="w-4 h-4" />
            Export
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50">
              <th className="text-left px-6 py-3">
                <SortHeader field="symbol">Symbol</SortHeader>
              </th>
              <th className="text-left px-4 py-3">Side</th>
              <th className="text-right px-4 py-3">Qty</th>
              <th className="text-right px-4 py-3">Entry</th>
              <th className="text-right px-4 py-3">Exit</th>
              <th className="text-left px-4 py-3">
                <SortHeader field="entryTime">Time</SortHeader>
              </th>
              <th className="text-right px-4 py-3">
                <SortHeader field="pnl">P&L</SortHeader>
              </th>
              <th className="text-right px-4 py-3">
                <SortHeader field="pnlPercent">P&L %</SortHeader>
              </th>
              <th className="text-right px-6 py-3">
                <SortHeader field="holdingPeriod">Bars</SortHeader>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {paginatedTrades.map((trade, idx) => (
              <tr
                key={`${trade.symbol}-${idx}`}
                className="hover:bg-gray-50 dark:hover:bg-gray-800/50"
              >
                <td className="px-6 py-3 font-medium text-gray-900 dark:text-gray-100">
                  {trade.symbol}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`px-2 py-0.5 text-xs font-medium rounded ${
                      trade.side === 1
                        ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
                        : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'
                    }`}
                  >
                    {trade.side === 1 ? 'BUY' : 'SELL'}
                  </span>
                </td>
                <td className="px-4 py-3 text-right font-mono text-gray-600 dark:text-gray-400">
                  {trade.quantityValue.toFixed(2)}
                </td>
                <td className="px-4 py-3 text-right font-mono text-gray-600 dark:text-gray-400">
                  ${trade.entryPriceValue.toFixed(2)}
                </td>
                <td className="px-4 py-3 text-right font-mono text-gray-600 dark:text-gray-400">
                  ${trade.exitPriceValue.toFixed(2)}
                </td>
                <td className="px-4 py-3 text-gray-500 dark:text-gray-400">
                  {formatDateTime(trade.entryTimeDate)}
                </td>
                <td
                  className={`px-4 py-3 text-right font-mono ${
                    trade.pnlValue >= 0
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-red-600 dark:text-red-400'
                  }`}
                >
                  {formatCurrency(trade.pnlValue)}
                </td>
                <td
                  className={`px-4 py-3 text-right font-mono ${
                    trade.pnlPercentValue >= 0
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-red-600 dark:text-red-400'
                  }`}
                >
                  {formatPercent(trade.pnlPercentValue)}
                </td>
                <td className="px-6 py-3 text-right font-mono text-gray-600 dark:text-gray-400">
                  {trade.holdingPeriodBars}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Summary Row */}
      <div className="flex items-center justify-between px-6 py-3 bg-gray-50 dark:bg-gray-800/50 border-t border-gray-100 dark:border-gray-800">
        <div className="flex items-center gap-6 text-sm">
          <span className="text-gray-500 dark:text-gray-400">
            Total P&L:{' '}
            <span
              className={`font-mono font-medium ${
                summary.totalPnl >= 0
                  ? 'text-green-600 dark:text-green-400'
                  : 'text-red-600 dark:text-red-400'
              }`}
            >
              {formatCurrency(summary.totalPnl)}
            </span>
          </span>
          <span className="text-gray-500 dark:text-gray-400">
            Commission:{' '}
            <span className="font-mono font-medium text-gray-900 dark:text-gray-100">
              ${summary.totalCommission.toFixed(2)}
            </span>
          </span>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="text-sm text-gray-600 dark:text-gray-400">
              {page} / {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
