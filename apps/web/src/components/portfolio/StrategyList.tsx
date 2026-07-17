/**
 * Strategies allocation & performance table with expandable position detail.
 */

import { Link } from 'react-router-dom';

import type { StrategyPerformance } from '@llamatrade/core/stores/portfolio';

import StrategyRow, { STRAT_GRID_COLS } from './StrategyRow';

interface StrategyListProps {
  strategies: StrategyPerformance[];
  totalBook: number;
  expandedStrategyId: string | null;
  hoveredStrategyId: string | null;
  onToggleExpanded: (id: string) => void;
  onHoverStrategy: (id: string | null) => void;
}

const COL = 'font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-ink/50';

export default function StrategyList({
  strategies,
  totalBook,
  expandedStrategyId,
  hoveredStrategyId,
  onToggleExpanded,
  onHoverStrategy,
}: StrategyListProps) {
  return (
    <div className="bg-paper border-2 border-ink shadow">
      <div className="flex items-center justify-between px-[18px] py-3.5 border-b-2 border-ink gap-3">
        <span className="font-mono text-[11.5px] font-bold uppercase tracking-[0.1em] text-ink">
          Strategies · Allocation &amp; Performance
        </span>
        <Link
          to="/strategies"
          className="font-mono text-[10.5px] font-bold uppercase tracking-wide text-orange-500 hover:text-orange-600"
        >
          Manage strategies →
        </Link>
      </div>

      <div
        className="grid items-center gap-2.5 px-[18px] py-2.5 border-b-2 border-ink"
        style={{ gridTemplateColumns: STRAT_GRID_COLS }}
      >
        <span />
        <span className={COL}>Strategy</span>
        <span className={`${COL} text-right`}>Allocation</span>
        <span className={`${COL} text-right`}>Market Value</span>
        <span className={`${COL} text-right`}>Day P&L</span>
        <span className={`${COL} text-right`}>Total Return</span>
        <span className={`${COL} text-right`}>Trend</span>
        <span className={`${COL} text-right`}>Status</span>
      </div>

      {strategies.length === 0 ? (
        <div className="flex items-center justify-center h-32 font-mono uppercase tracking-wide text-ink/50">
          No strategies yet
        </div>
      ) : (
        strategies.map((strategy) => (
          <StrategyRow
            key={strategy.id}
            strategy={strategy}
            totalBook={totalBook}
            isExpanded={expandedStrategyId === strategy.id}
            isHovered={hoveredStrategyId === strategy.id}
            onToggleExpand={() => onToggleExpanded(strategy.id)}
            onHover={(hovered) => onHoverStrategy(hovered ? strategy.id : null)}
          />
        ))
      )}
    </div>
  );
}
