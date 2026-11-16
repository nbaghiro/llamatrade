import type { Holding } from '@llamatrade/core/stores/portfolio';

import { hasTargets, weightRows, weightScale } from '../../lib/portfolioView';
import { Money, Num, Pct, WeightBar } from '../ui';

interface WeightRowsProps {
  holdings: readonly Holding[];
  sleeveValue: number;
  /** Target weights by symbol, as fractions, when the strategy publishes them. */
  targets?: Readonly<Record<string, number>>;
  /** Adds value and unrealized gain columns, as on the sleeve page. */
  full?: boolean;
  /** Shows only this many rows below 768px, with a count of the rest. */
  phoneLimit?: number;
  /** Draws the bars in the attention tone for a frozen sleeve. */
  frozen?: boolean;
}

const GRID = {
  brief: 'grid-cols-[48px_minmax(0,1fr)_52px]',
  briefTarget: 'grid-cols-[48px_minmax(0,1fr)_52px_40px]',
  full: 'grid-cols-[48px_minmax(0,1fr)_52px] md:grid-cols-[54px_minmax(0,1fr)_54px_96px_96px]',
  fullTarget:
    'grid-cols-[48px_minmax(0,1fr)_52px_40px] md:grid-cols-[54px_minmax(0,1fr)_54px_50px_96px_96px]',
} as const;

const targetDp = (t: number) => (Math.abs(t * 100 - Math.round(t * 100)) < 0.05 ? 0 : 1);

/** Each fund as a weight bar against its sleeve, with a target tick when one is known. */
export function WeightRows({
  holdings,
  sleeveValue,
  targets,
  full = false,
  phoneLimit,
  frozen = false,
}: WeightRowsProps) {
  const rows = weightRows(holdings, sleeveValue, targets);
  const scale = weightScale(rows);
  const withTargets = hasTargets(rows);
  const grid =
    GRID[`${full ? 'full' : 'brief'}${withTargets ? 'Target' : ''}` as keyof typeof GRID];
  const hidden = phoneLimit !== undefined ? Math.max(0, rows.length - phoneLimit) : 0;
  const head = 'font-mono text-[10.5px] font-medium text-fg-3';
  const fullCell = full ? 'hidden md:block' : 'hidden';

  return (
    <div>
      <div className={`grid items-center gap-2.5 pb-1 ${grid} ${head}`}>
        <span>Fund</span>
        <span>{withTargets ? 'Weight · target' : 'Weight'}</span>
        <span className="text-right">Now</span>
        {withTargets && <span className="text-right">Target</span>}
        <span className={`text-right ${fullCell}`}>Value</span>
        <span className={`text-right ${fullCell}`}>Unrealized</span>
      </div>
      {rows.map((r, i) => (
        <div
          key={r.holding.symbol}
          className={`grid items-center gap-2.5 py-1.5 ${grid} ${
            phoneLimit !== undefined && i >= phoneLimit ? 'max-md:hidden' : ''
          }`}
        >
          <span className="font-mono text-[13px] font-semibold">{r.holding.symbol}</span>
          <WeightBar
            weight={r.weight / scale}
            target={r.target !== undefined ? r.target / scale : undefined}
            frozen={frozen}
            valueText={`${(r.weight * 100).toFixed(1)}%`}
            label={`${r.holding.symbol} weight ${(r.weight * 100).toFixed(1)}%${
              r.target !== undefined ? `, target ${(r.target * 100).toFixed(1)}%` : ''
            }`}
          />
          <Pct value={r.weight} dp={1} className="text-right text-[12.5px]" />
          {withTargets && (
            <span className="text-right text-[12.5px] text-fg-3">
              {r.target !== undefined ? <Pct value={r.target} dp={targetDp(r.target)} /> : null}
            </span>
          )}
          <Num value={r.holding.marketValue} className={`text-right text-[12.5px] ${fullCell}`} />
          <Money
            value={r.holding.unrealizedPnl}
            pnl
            className={`text-right text-[12.5px] ${fullCell}`}
          />
        </div>
      ))}
      {hidden > 0 && (
        <div className="pt-1 text-[12.5px] text-fg-3 md:hidden">
          {hidden} more {hidden === 1 ? 'fund' : 'funds'}
        </div>
      )}
    </div>
  );
}
