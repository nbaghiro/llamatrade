import { MoreHorizontal, Pause, Pencil, Play, Trash2, X } from 'lucide-react';
import { lazy, Suspense, useState } from 'react';
import { Link } from 'react-router-dom';

import { StrategyStatus } from '../../generated/proto/strategy_pb';

import { EquityMiniChart } from './EquityMiniChart';
import {
  formatReturn,
  pillClass,
  positionAllocations,
  STRATEGY_COLORS,
  type StrategyRowView,
} from './strategyRow';

const DslCodeBlock = lazy(() => import('./DslCodeBlock'));

const dslPlaceholder = (text: string) => (
  <div className="mx-4 mb-3.5 font-mono text-[10.5px] text-ink/40">{text}</div>
);

interface StrategyDetailDrawerProps {
  row: StrategyRowView;
  /** True while the full strategy (DSL/symbols/timeframe) is being hydrated. */
  dslLoading?: boolean;
  onClose: () => void;
  onActivate: (id: string) => void;
  onPause: (id: string) => void;
  onDelete: (id: string) => void;
  actionLoading: boolean;
}

export function StrategyDetailDrawer({
  row,
  dslLoading = false,
  onClose,
  onActivate,
  onPause,
  onDelete,
  actionLoading,
}: StrategyDetailDrawerProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const { strategy } = row;

  const dsl = strategy.dslCode || strategy.compiledJson;
  const allocations = positionAllocations(row.run);

  const results = row.run?.results;
  const benchmarkSymbol =
    results?.benchmarkSymbol || results?.metrics?.benchmarkSymbol || row.run?.config?.benchmarkSymbol || 'SPY';

  const tags: string[] = [
    row.implementation.toUpperCase(),
    strategy.timeframe || '1D',
    `${strategy.symbols.length} symbols`,
    `v${strategy.version}`,
  ];
  if (row.benchmarkCurve.length > 1) tags.push(`Bench · ${benchmarkSymbol}`);

  return (
    <div className="card-shadow sticky top-4">
      {/* Header — ink block within the paper card */}
      <div className="bg-ink text-bone px-4 py-4">
        <div className="flex items-center justify-between">
          <span className="font-mono text-[9px] font-bold uppercase tracking-[0.14em] text-bone/50">
            Strategy detail
          </span>
          <button
            onClick={onClose}
            className="text-bone/60 hover:text-bone transition-colors"
            aria-label="Close"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
        <h2 className="font-display uppercase text-[26px] leading-[0.98] tracking-tight mt-2">
          {strategy.name}
        </h2>
        <div className="flex flex-wrap gap-1.5 mt-3">
          <span
            className={`inline-flex items-center px-[7px] py-[3px] font-mono text-[9px] font-bold uppercase tracking-wide border-[1.5px] border-ink ${pillClass(
              row.pill
            )}`}
          >
            {row.pill}
          </span>
          {tags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center px-[7px] py-[3px] font-mono text-[9px] font-bold uppercase tracking-wide border-[1.5px] border-bone/35 text-bone/85"
            >
              {tag}
            </span>
          ))}
        </div>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-3 border-b-2 border-ink">
        <div className="px-3.5 py-3">
          <div className="font-mono text-[9px] font-bold uppercase tracking-wide text-ink/45">Return</div>
          <div
            className={`font-mono text-[19px] font-bold mt-1 tabular-nums ${
              row.returnPct === null ? 'text-ink/40' : row.returnPct >= 0 ? 'text-green-500' : 'text-red-500'
            }`}
          >
            {row.returnPct === null ? '—' : formatReturn(row.returnPct)}
          </div>
        </div>
        <div className="px-3.5 py-3 border-l border-ink/10">
          <div className="font-mono text-[9px] font-bold uppercase tracking-wide text-ink/45">Sharpe</div>
          <div className="font-mono text-[19px] font-bold mt-1 tabular-nums text-ink">
            {row.sharpe === null ? '—' : row.sharpe.toFixed(2)}
          </div>
        </div>
        <div className="px-3.5 py-3 border-l border-ink/10">
          <div className="font-mono text-[9px] font-bold uppercase tracking-wide text-ink/45">Max DD</div>
          <div className="font-mono text-[15px] font-bold mt-[7px] tabular-nums text-ink">
            {row.maxDrawdownPct === null ? '—' : `-${Math.abs(row.maxDrawdownPct).toFixed(1)}%`}
          </div>
        </div>
      </div>

      {/* Equity vs SPY */}
      {row.equityCurve.length > 1 ? (
        <EquityMiniChart strategy={row.equityCurve} benchmark={row.benchmarkCurve} benchmarkSymbol={benchmarkSymbol} />
      ) : (
        <div className="px-4 py-6 text-center font-mono text-[10px] uppercase tracking-wide text-ink/40">
          No backtest yet
        </div>
      )}

      {/* DSL */}
      <div className="border-t-2 border-ink">
        <div className="font-mono text-[10px] font-bold uppercase tracking-widest text-ink/55 px-4 pt-3 pb-2">
          Definition · DSL
        </div>
        {dsl ? (
          <Suspense fallback={dslPlaceholder('Loading definition…')}>
            <DslCodeBlock code={dsl} />
          </Suspense>
        ) : dslLoading ? (
          dslPlaceholder('Loading definition…')
        ) : (
          dslPlaceholder('No DSL definition available.')
        )}
      </div>

      {/* Allocation */}
      <div className="border-t-2 border-ink">
        <div className="font-mono text-[10px] font-bold uppercase tracking-widest text-ink/55 px-4 pt-3 pb-2">
          Allocation · {allocations.length} {allocations.length === 1 ? 'position' : 'positions'}
        </div>
        {allocations.length > 0 ? (
          <div className="px-4 pb-3.5">
            {allocations.map((pos, i) => (
              <div key={pos.symbol} className="flex items-center gap-2.5 py-1.5">
                <span className="font-mono text-[11px] font-bold w-11 text-ink">{pos.symbol}</span>
                <span className="flex-1 h-2.5 border-[1.5px] border-ink bg-bone relative">
                  <span
                    className="absolute inset-y-0 left-0"
                    style={{
                      width: `${Math.min(100, pos.weight)}%`,
                      background: STRATEGY_COLORS[i % STRATEGY_COLORS.length],
                    }}
                  />
                </span>
                <span className="font-mono text-[11px] font-bold w-9 text-right tabular-nums text-ink">
                  {Math.round(pos.weight)}%
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="px-4 pb-3.5 font-mono text-[10.5px] text-ink/40">
            No position data — run a backtest to populate holdings.
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex gap-2.5 px-4 py-3.5 border-t-2 border-ink">
        <Link
          to={`/strategies/${strategy.id}`}
          className="flex-1 flex items-center justify-center gap-1.5 font-mono text-[11px] font-bold uppercase tracking-wide border-2 border-ink px-2 py-3 bg-orange-500 text-ink shadow-[3px_3px_0_rgb(var(--lt-ink))] hover:-translate-x-0.5 hover:-translate-y-0.5 transition-transform"
        >
          <Pencil className="w-3.5 h-3.5" />
          Edit
        </Link>
        <Link
          to={`/backtest?strategy=${strategy.id}`}
          className="flex-1 flex items-center justify-center gap-1.5 font-mono text-[11px] font-bold uppercase tracking-wide border-2 border-ink px-2 py-3 bg-paper text-ink shadow-[3px_3px_0_rgb(var(--lt-ink))] hover:-translate-x-0.5 hover:-translate-y-0.5 transition-transform"
        >
          <Play className="w-3.5 h-3.5" />
          Backtest
        </Link>
        <div className="relative">
          <button
            onClick={() => setMenuOpen((v) => !v)}
            disabled={actionLoading}
            aria-label="More actions"
            className="h-full flex items-center justify-center border-2 border-ink px-3 py-3 bg-paper text-ink shadow-[3px_3px_0_rgb(var(--lt-ink))] disabled:opacity-40"
          >
            <MoreHorizontal className="w-3.5 h-3.5" />
          </button>
          {menuOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
              <div className="dropdown right-0 bottom-full mb-1 w-44">
                {strategy.status === StrategyStatus.ACTIVE ? (
                  <button
                    onClick={() => {
                      onPause(strategy.id);
                      setMenuOpen(false);
                    }}
                    disabled={actionLoading}
                    className="dropdown-item w-full disabled:opacity-50"
                  >
                    <Pause className="dropdown-item-icon" />
                    Pause Strategy
                  </button>
                ) : (
                  <button
                    onClick={() => {
                      onActivate(strategy.id);
                      setMenuOpen(false);
                    }}
                    disabled={actionLoading}
                    className="dropdown-item w-full disabled:opacity-50"
                  >
                    <Play className="dropdown-item-icon" />
                    Activate Strategy
                  </button>
                )}
                <button
                  onClick={() => {
                    onDelete(strategy.id);
                    setMenuOpen(false);
                  }}
                  disabled={actionLoading}
                  className="dropdown-item w-full text-red-600 hover:bg-red-500 hover:text-bone disabled:opacity-50"
                >
                  <Trash2 className="dropdown-item-icon" />
                  Delete
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
