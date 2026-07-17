/**
 * Flat blotter of every open position across strategies, colored by sleeve.
 */

import type { StrategyPerformance } from '@llamatrade/core/stores/portfolio';
import { Link } from 'react-router-dom';


interface PositionsBlotterProps {
  strategies: StrategyPerformance[];
}

const BLOTTER_COLS = 'minmax(0,1.3fr) 0.7fr 0.8fr 0.8fr 1fr 0.9fr 1fr';
const HEAD = 'font-mono text-[9px] font-bold uppercase tracking-[0.08em] text-ink/50';

function currency(value: number, digits = 0): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function signedCurrency(value: number): string {
  return `${value >= 0 ? '+' : '-'}${currency(Math.abs(value))}`;
}

export default function PositionsBlotter({ strategies }: PositionsBlotterProps) {
  const rows = strategies.flatMap((s) =>
    s.positions.map((p) => ({ ...p, strategyName: s.name, color: s.color }))
  );

  return (
    <div className="bg-paper border-2 border-ink shadow">
      <div className="flex items-center justify-between px-[18px] py-3.5 border-b-2 border-ink gap-3">
        <span className="font-mono text-[11.5px] font-bold uppercase tracking-[0.1em] text-ink">
          Open Positions · <span className="tabular-nums">{rows.length}</span>
        </span>
        <Link
          to="/trading"
          className="font-mono text-[10.5px] font-bold uppercase tracking-wide text-orange-500 hover:text-orange-600"
        >
          Trade blotter →
        </Link>
      </div>

      <div className="grid items-center gap-2 px-[18px] py-2.5 border-b-2 border-ink" style={{ gridTemplateColumns: BLOTTER_COLS }}>
        <span className={HEAD}>Symbol</span>
        <span className={HEAD}>Strategy</span>
        <span className={`${HEAD} text-right`}>Qty</span>
        <span className={`${HEAD} text-right`}>Avg</span>
        <span className={`${HEAD} text-right`}>Last</span>
        <span className={`${HEAD} text-right`}>Mkt Value</span>
        <span className={`${HEAD} text-right`}>Total P&L</span>
      </div>

      {rows.length === 0 ? (
        <div className="px-[18px] py-6 font-mono text-xs text-ink/40 italic">No open positions</div>
      ) : (
        rows.map((r) => (
          <div
            key={`${r.strategyName}-${r.symbol}`}
            className="grid items-center gap-2 px-[18px] py-2.5 border-b border-line last:border-b-0"
            style={{ gridTemplateColumns: BLOTTER_COLS }}
          >
            <span className="font-mono font-bold text-[13px] text-ink flex items-center">
              <span className="w-2 h-2 border-[1.5px] border-ink mr-2 inline-block" style={{ backgroundColor: r.color }} />
              {r.symbol}
            </span>
            <span className="font-mono text-xs text-ink/55 truncate">{r.strategyName}</span>
            <span className="font-mono text-xs text-right tabular-nums">{r.qty}</span>
            <span className="font-mono text-xs text-right tabular-nums">{currency(r.avgEntryPrice, 2)}</span>
            <span className="font-mono text-xs text-right tabular-nums">{currency(r.currentPrice, 2)}</span>
            <span className="font-mono font-bold text-xs text-right tabular-nums">{currency(r.marketValue)}</span>
            <span
              className={`font-mono font-bold text-xs text-right tabular-nums ${
                r.unrealizedPnl >= 0 ? 'text-green-600' : 'text-red-600'
              }`}
            >
              {signedCurrency(r.unrealizedPnl)}
            </span>
          </div>
        ))
      )}
    </div>
  );
}
