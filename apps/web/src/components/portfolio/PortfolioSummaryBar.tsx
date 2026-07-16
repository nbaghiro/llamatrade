/**
 * Five-tile KPI rail: total equity (hero ink tile), day P&L, total return,
 * free cash, and deployed capital.
 */

import { Plus } from 'lucide-react';

interface PortfolioSummaryBarProps {
  totalEquity: number;
  dayPnl: number;
  dayPnlPercent: number;
  totalReturn: number;
  totalReturnPercent: number;
  freeCash: number;
  freeCashPercent: number;
  deployedValue: number;
  liveStrategiesCount: number;
  /** Opens the add-funds flow; omit to hide the action. */
  onAddFunds?: () => void;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

function signedCurrency(value: number): string {
  return `${value >= 0 ? '+' : '-'}${formatCurrency(Math.abs(value))}`;
}

function signedPercent(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function tone(value: number): string {
  return value >= 0 ? 'text-green-600' : 'text-red-600';
}

export default function PortfolioSummaryBar({
  totalEquity,
  dayPnl,
  dayPnlPercent,
  totalReturn,
  totalReturnPercent,
  freeCash,
  freeCashPercent,
  deployedValue,
  liveStrategiesCount,
  onAddFunds,
}: PortfolioSummaryBarProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr_1fr] gap-3.5">
      {/* Total Equity — ink hero tile with orange offset shadow. */}
      <div className="bg-ink text-bone border-2 border-ink shadow-[4px_4px_0_#ff4d1c] p-4">
        <div className="font-mono text-[9.5px] font-bold uppercase tracking-[0.13em] text-bone/55">
          Total Equity
        </div>
        <div className="font-mono font-bold text-[34px] mt-2 tracking-tight tabular-nums">
          {formatCurrency(totalEquity)}
        </div>
        <div className={`font-mono text-xs mt-1.5 font-bold tabular-nums ${tone(totalReturn)}`}>
          {totalReturn >= 0 ? '↗' : '↘'} {signedCurrency(totalReturn)} lifetime
        </div>
      </div>

      <div className="bg-paper border-2 border-ink shadow p-4">
        <div className="font-mono text-[9.5px] font-bold uppercase tracking-[0.13em] text-ink/50">
          Day P&L
        </div>
        <div className={`font-mono font-bold text-[23px] mt-2 tracking-tight tabular-nums ${tone(dayPnl)}`}>
          {signedCurrency(dayPnl)}
        </div>
        <div className={`font-mono text-xs mt-1 font-bold tabular-nums ${tone(dayPnl)}`}>
          {signedPercent(dayPnlPercent)}
        </div>
      </div>

      <div className="bg-paper border-2 border-ink shadow p-4">
        <div className="font-mono text-[9.5px] font-bold uppercase tracking-[0.13em] text-ink/50">
          Total Return
        </div>
        <div
          className={`font-mono font-bold text-[23px] mt-2 tracking-tight tabular-nums ${tone(totalReturnPercent)}`}
        >
          {signedPercent(totalReturnPercent)}
        </div>
        <div className={`font-mono text-xs mt-1 font-bold tabular-nums ${tone(totalReturn)}`}>
          {signedCurrency(totalReturn)}
        </div>
      </div>

      <div className="bg-paper border-2 border-ink shadow p-4 flex flex-col">
        <div className="font-mono text-[9.5px] font-bold uppercase tracking-[0.13em] text-ink/50">
          Free Cash
        </div>
        <div className="font-mono font-bold text-[23px] mt-2 tracking-tight tabular-nums text-ink">
          {formatCurrency(freeCash)}
        </div>
        <div className="font-mono text-xs mt-1 font-bold text-ink/50 tabular-nums">
          {freeCashPercent.toFixed(1)}% of book
        </div>
        {onAddFunds && (
          <button
            onClick={onAddFunds}
            className="mt-2.5 flex items-center justify-center gap-1 border-2 border-ink bg-orange-500 py-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.05em] text-ink shadow-[2px_2px_0_rgb(var(--lt-ink))] transition-transform hover:-translate-y-0.5"
          >
            <Plus className="h-3 w-3" strokeWidth={3} /> Add funds
          </button>
        )}
      </div>

      <div className="bg-paper border-2 border-ink shadow p-4">
        <div className="font-mono text-[9.5px] font-bold uppercase tracking-[0.13em] text-ink/50">
          Deployed
        </div>
        <div className="font-mono font-bold text-[23px] mt-2 tracking-tight tabular-nums text-ink">
          {formatCurrency(deployedValue)}
        </div>
        <div className="font-mono text-xs mt-1 font-bold text-ink/50">
          {liveStrategiesCount} active {liveStrategiesCount === 1 ? 'strategy' : 'strategies'}
        </div>
      </div>
    </div>
  );
}
