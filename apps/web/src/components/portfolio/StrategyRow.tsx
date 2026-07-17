/**
 * One strategy row in the allocation & performance table, expandable to its
 * open positions.
 */

import { ExecutionMode, ExecutionStatus, type StrategyPerformance } from '@llamatrade/core/stores/portfolio';

import StrategyRowExpanded from './StrategyRowExpanded';

// Shared 8-column track, reused by the table's header row so both align.
export const STRAT_GRID_COLS = '26px minmax(0,2.4fr) 1fr 1fr 1fr 1fr 96px 80px';

interface StrategyRowProps {
  strategy: StrategyPerformance;
  totalBook: number;
  isExpanded: boolean;
  isHovered: boolean;
  onToggleExpand: () => void;
  onHover: (hovered: boolean) => void;
}

// Badge reflects the execution MODE (paper vs live) while running; paused/stopped
// are shown as their own state. A running paper strategy is "PAPER", not "LIVE".
type DisplayBadge = 'paper' | 'live' | 'paused' | 'stopped';

function displayBadge(status: ExecutionStatus, mode: ExecutionMode): DisplayBadge {
  if (status === ExecutionStatus.PAUSED) return 'paused';
  if (status === ExecutionStatus.RUNNING) {
    return mode === ExecutionMode.LIVE ? 'live' : 'paper';
  }
  return 'stopped';
}

const BADGE_STYLES: Record<DisplayBadge, string> = {
  paper: 'bg-orange-500 text-ink border-ink',
  live: 'bg-green-600 text-bone border-ink',
  paused: 'bg-bone text-orange-500 border-orange-500',
  stopped: 'bg-bone text-ink/55 border-ink',
};

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

function signedPercent(value: number, digits = 2): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%`;
}

function tone(value: number): string {
  return value >= 0 ? 'text-green-600' : 'text-red-600';
}

// Compact sparkline from the strategy's cumulative-return curve. Down trends
// render red; otherwise the strategy's own series color.
function Sparkline({ curve, color }: { curve: { value: number }[]; color: string }) {
  if (curve.length < 2) {
    return (
      <svg width="90" height="26" viewBox="0 0 90 26" className="justify-self-end">
        <line x1="0" y1="13" x2="90" y2="13" stroke="rgba(13,13,13,.2)" strokeDasharray="4 4" />
      </svg>
    );
  }
  const values = curve.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const stroke = values[values.length - 1] >= 0 ? color : '#c81e1e';
  const d = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * 90;
      const y = 23 - ((v - min) / range) * 20;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg width="90" height="26" viewBox="0 0 90 26" className="justify-self-end">
      <path d={d} fill="none" stroke={stroke} strokeWidth="2" />
    </svg>
  );
}

export default function StrategyRow({
  strategy,
  totalBook,
  isExpanded,
  isHovered,
  onToggleExpand,
  onHover,
}: StrategyRowProps) {
  const badge = displayBadge(strategy.status, strategy.mode);
  const deployed = strategy.currentValue > 0 || strategy.allocatedCapital > 0;
  const allocationPct = totalBook > 0 ? (strategy.allocatedCapital / totalBook) * 100 : 0;
  const dayPnl = strategy.currentValue * strategy.returns['1D'];
  const dayPnlPct = strategy.returns['1D'] * 100;
  const totalReturnPct = strategy.returns['ALL'] * 100;
  const totalReturnValue = strategy.currentValue - strategy.allocatedCapital;
  const modeLabel = strategy.mode === ExecutionMode.LIVE ? 'live' : 'paper';

  return (
    <div
      className={`border-b border-line ${isHovered ? 'bg-bone' : ''} ${!deployed ? 'opacity-60' : ''}`}
      onMouseEnter={() => onHover(true)}
      onMouseLeave={() => onHover(false)}
    >
      <div
        className="grid items-center gap-2.5 px-[18px] py-3 cursor-pointer"
        style={{ gridTemplateColumns: STRAT_GRID_COLS }}
        onClick={onToggleExpand}
      >
        <span className="font-mono text-xs text-ink/50">{isExpanded ? '▾' : '▸'}</span>

        <div className="flex items-center gap-2.5 min-w-0">
          <span className="w-[11px] h-[11px] flex-none border-2 border-ink" style={{ backgroundColor: strategy.color }} />
          <div className="min-w-0">
            <div className="font-bold text-[14.5px] text-ink truncate">{strategy.name}</div>
            <div className="font-mono text-[10px] text-ink/50 uppercase tracking-wide mt-0.5 truncate">
              {modeLabel} · {strategy.positionsCount} pos
            </div>
          </div>
        </div>

        {deployed ? (
          <>
            <div className="text-right">
              <div className="font-mono font-bold text-[13.5px] tabular-nums">{formatCurrency(strategy.allocatedCapital)}</div>
              <div className="font-mono text-[9px] text-ink/40 uppercase tracking-wide mt-0.5">
                {allocationPct.toFixed(0)}% of book
              </div>
            </div>
            <div className="text-right">
              <div className="font-mono font-bold text-[13.5px] tabular-nums">{formatCurrency(strategy.currentValue)}</div>
              <div className="font-mono text-[9px] text-ink/40 uppercase tracking-wide mt-0.5">marked live</div>
            </div>
            <div className="text-right">
              <div className={`font-mono font-bold text-[13.5px] tabular-nums ${tone(dayPnl)}`}>{signedCurrency(dayPnl)}</div>
              <div className={`font-mono text-[9px] tabular-nums mt-0.5 ${tone(dayPnl)}`}>{signedPercent(dayPnlPct)}</div>
            </div>
            <div className="text-right">
              <div className={`font-mono font-bold text-[13.5px] tabular-nums ${tone(totalReturnValue)}`}>
                {signedPercent(totalReturnPct, 1)}
              </div>
              <div className={`font-mono text-[9px] tabular-nums mt-0.5 ${tone(totalReturnValue)}`}>
                {signedCurrency(totalReturnValue)}
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="text-right">
              <div className="font-mono font-bold text-[13.5px] text-ink/50">—</div>
              <div className="font-mono text-[9px] text-ink/40 uppercase tracking-wide mt-0.5">unallocated</div>
            </div>
            <div className="text-right font-mono font-bold text-[13.5px] text-ink/50">—</div>
            <div className="text-right font-mono font-bold text-[13.5px] text-ink/50">—</div>
            <div className="text-right font-mono font-bold text-[13.5px] text-ink/50">—</div>
          </>
        )}

        <Sparkline curve={deployed ? strategy.equityCurve : []} color={strategy.color} />

        <span
          className={`justify-self-end font-mono text-[9px] font-bold uppercase tracking-wide border-[1.5px] px-1.5 py-0.5 ${BADGE_STYLES[badge]}`}
        >
          {badge}
        </span>
      </div>

      {isExpanded && (
        <StrategyRowExpanded strategyValue={strategy.currentValue} positions={strategy.positions} />
      )}
    </div>
  );
}
