/**
 * Open-positions detail shown when a strategy row is expanded.
 */

import type { Position } from '@llamatrade/core/stores/portfolio';

import { STRAT_GRID_COLS } from './StrategyRow';

interface StrategyRowExpandedProps {
  strategyValue: number;
  positions: Position[];
}

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

export default function StrategyRowExpanded({ strategyValue, positions }: StrategyRowExpandedProps) {
  const costBasis = positions.reduce((sum, p) => sum + p.avgEntryPrice * p.qty, 0);
  const unrealized = positions.reduce((sum, p) => sum + p.unrealizedPnl, 0);

  return (
    <div className="bg-bone border-t-2 border-ink border-b border-line pt-1 pb-2">
      <div className="flex items-center gap-3.5 px-[18px] pt-1.5 pb-1 font-mono text-[10px] text-ink/55 uppercase tracking-wide flex-wrap">
        Open positions
        <span className="border-[1.5px] border-ink px-2 py-0.5 font-bold bg-paper tabular-nums">{positions.length}</span>
        · Cost basis
        <span className="border-[1.5px] border-ink px-2 py-0.5 font-bold bg-paper tabular-nums">{currency(costBasis)}</span>
        · Unrealized
        <span
          className={`border-[1.5px] border-ink px-2 py-0.5 font-bold bg-paper tabular-nums ${
            unrealized >= 0 ? 'text-green-600' : 'text-red-600'
          }`}
        >
          {signedCurrency(unrealized)}
        </span>
      </div>

      {positions.length === 0 ? (
        <div className="px-[18px] py-3 font-mono text-xs text-ink/40 italic">No open positions</div>
      ) : (
        <>
          <div
            className="grid items-center gap-2.5 px-[18px] py-2"
            style={{ gridTemplateColumns: STRAT_GRID_COLS }}
          >
            <span />
            <span className="font-mono text-[8.5px] font-bold uppercase tracking-[0.08em] text-ink/40">Symbol · Asset</span>
            <span className="font-mono text-[8.5px] font-bold uppercase tracking-[0.08em] text-ink/40 text-right">Weight</span>
            <span className="font-mono text-[8.5px] font-bold uppercase tracking-[0.08em] text-ink/40 text-right">Qty</span>
            <span className="font-mono text-[8.5px] font-bold uppercase tracking-[0.08em] text-ink/40 text-right">Avg Cost</span>
            <span className="font-mono text-[8.5px] font-bold uppercase tracking-[0.08em] text-ink/40 text-right">Last</span>
            <span className="font-mono text-[8.5px] font-bold uppercase tracking-[0.08em] text-ink/40 text-right">Mkt Value</span>
            <span className="font-mono text-[8.5px] font-bold uppercase tracking-[0.08em] text-ink/40 text-right">Total P&L</span>
          </div>

          {positions.map((p) => {
            const weight = strategyValue > 0 ? (p.marketValue / strategyValue) * 100 : 0;
            return (
              <div
                key={p.symbol}
                className="grid items-center gap-2.5 px-[18px] py-2"
                style={{ gridTemplateColumns: STRAT_GRID_COLS }}
              >
                <span />
                <div className="flex items-baseline gap-2.5 min-w-0">
                  <span className="font-mono font-bold text-[13px] text-ink">{p.symbol}</span>
                  {p.name && (
                    <span className="font-mono text-[9.5px] text-ink/50 truncate">{p.name}</span>
                  )}
                </div>
                <div className="font-mono font-bold text-[13px] text-right tabular-nums">{weight.toFixed(0)}%</div>
                <div className="font-mono font-bold text-[13px] text-right tabular-nums">{p.qty}</div>
                <div className="font-mono font-bold text-[13px] text-right tabular-nums">{currency(p.avgEntryPrice, 2)}</div>
                <div className="font-mono font-bold text-[13px] text-right tabular-nums">{currency(p.currentPrice, 2)}</div>
                <div className="font-mono font-bold text-[13px] text-right tabular-nums">{currency(p.marketValue)}</div>
                <div
                  className={`font-mono font-bold text-[13px] text-right tabular-nums ${
                    p.unrealizedPnl >= 0 ? 'text-green-600' : 'text-red-600'
                  }`}
                >
                  {signedCurrency(p.unrealizedPnl)}
                </div>
              </div>
            );
          })}
        </>
      )}
    </div>
  );
}
