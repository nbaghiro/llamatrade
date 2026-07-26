import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { useAgentStore } from '@llamatrade/core/stores/agent';
import { toNumber, useBacktestStore } from '@llamatrade/core/stores/backtest';
import { AlertTriangle, CheckCircle2, Play } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { useRunConsole } from '../../../store/runConsole';
import { useStrategyBuilderStoreWithContext } from '../../../store/strategy-builder';
import { MagicIcon } from '../../common/MagicIcon';
import { estimateAllocation } from '../treeAdapter';

const signedPct = (v: number): string => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`;

// Categorical slice colours (Monolith ramp) for the estimated allocation bar.
const SLICE_COLORS = ['#ff4d1c', '#24408a', '#0c6a2d', '#0d0d0d', '#7a7362', '#a8a08c'];

/**
 * The Split Studio bottom insights strip — always-on, replacing the old right
 * BacktestPreview + QuickStats panels. Shows an estimated holdings bar (from the
 * tree structure), last-backtest quick stats, validation status, and the
 * backtest CTA.
 */
export function BuilderInsightsBar() {
  const tree = useStrategyBuilderStoreWithContext((s) => s.tree);
  const strategyId = useStrategyBuilderStoreWithContext((s) => s.strategyId);
  const strategyName = useStrategyBuilderStoreWithContext((s) => s.strategyName);
  const isValid = useStrategyBuilderStoreWithContext((s) => s.isValid);
  const validationResult = useStrategyBuilderStoreWithContext((s) => s.validationResult);
  const fetchLatestCompletedBacktest = useBacktestStore((s) => s.fetchLatestCompletedBacktest);
  const toggleCopilot = useAgentStore((s) => s.togglePanel);
  const openRunConsole = useRunConsole((s) => s.openRunConsole);

  const [preview, setPreview] = useState<BacktestRun | null>(null);

  useEffect(() => {
    if (!strategyId) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    fetchLatestCompletedBacktest(strategyId).then((run) => {
      if (!cancelled) setPreview(run);
    });
    return () => {
      cancelled = true;
    };
  }, [strategyId, fetchLatestCompletedBacktest]);

  const metrics = preview?.results?.metrics;
  const stats: [string, string, string?][] = [
    ['CAGR', metrics ? signedPct(toNumber(metrics.annualizedReturn)) : '—', metrics ? 'pos' : undefined],
    ['Max DD', metrics ? `-${Math.abs(toNumber(metrics.maxDrawdown) * 100).toFixed(1)}%` : '—', 'neg'],
    ['Sharpe', metrics ? toNumber(metrics.sharpeRatio).toFixed(2) : '—'],
    ['Sortino', metrics ? toNumber(metrics.sortinoRatio).toFixed(2) : '—'],
    ['Win', metrics ? `${(toNumber(metrics.winRate) * 100).toFixed(1)}%` : '—'],
  ];

  const alloc = useMemo(() => estimateAllocation(tree), [tree]);
  const shown = alloc.slice(0, SLICE_COLORS.length);
  const restPct = alloc.slice(SLICE_COLORS.length).reduce((s, a) => s + a.pct, 0);

  const errorCount = validationResult?.errors?.length ?? 0;

  return (
    <div className="flex flex-shrink-0 flex-wrap items-center gap-x-6 gap-y-2 border-t-2 border-ink bg-paper px-4 py-2.5">
      {/* Estimated holdings */}
      <div className="flex min-w-[220px] flex-1 items-center gap-3">
        <span className="font-mono text-[9px] font-bold uppercase tracking-[0.09em] text-ink/50" title="Structural estimate — computed weights resolve at run time">
          Holdings · est
        </span>
        {alloc.length > 0 ? (
          <>
            <div className="flex h-4 min-w-[120px] flex-1 overflow-hidden border-2 border-ink">
              {shown.map((a, i) => (
                <span key={a.symbol} style={{ width: `${a.pct}%`, background: SLICE_COLORS[i] }} title={`${a.symbol} ~${a.pct.toFixed(0)}%`} />
              ))}
              {restPct > 0 && <span style={{ width: `${restPct}%`, background: '#d4cdba' }} />}
            </div>
            <span className="whitespace-nowrap font-mono text-[10px] font-bold tabular-nums text-ink/70">
              {alloc.length} {alloc.length === 1 ? 'holding' : 'holdings'}
            </span>
          </>
        ) : (
          <span className="font-mono text-[10px] text-ink/40">no assets yet</span>
        )}
      </div>

      {/* Quick stats */}
      <div className="flex items-center gap-4">
        {stats.map(([label, value, tone]) => (
          <div key={label} className="flex items-baseline gap-1.5">
            <span className="font-mono text-[9px] font-bold uppercase tracking-[0.08em] text-ink/45">{label}</span>
            <span
              className={`font-mono text-[12px] font-bold tabular-nums ${
                value === '—' ? 'text-ink/40' : tone === 'pos' ? 'text-green-500' : tone === 'neg' ? 'text-red-500' : 'text-ink'
              }`}
            >
              {value}
            </span>
          </div>
        ))}
      </div>

      {/* Status + CTA */}
      <div className="ml-auto flex items-center gap-3">
        {isValid ? (
          <span className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-wide text-green-700">
            <CheckCircle2 className="h-3.5 w-3.5" /> Valid
          </span>
        ) : (
          <span className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-wide text-red-600">
            <AlertTriangle className="h-3.5 w-3.5" /> {errorCount || 'check'} {errorCount === 1 ? 'issue' : 'issues'}
          </span>
        )}
        {strategyId ? (
          <button
            onClick={() => openRunConsole(strategyId, strategyName)}
            className="flex items-center gap-1.5 border-2 border-ink bg-green-600 px-3 py-1.5 font-mono text-[10px] font-bold uppercase tracking-wide text-bone shadow-[2px_2px_0_rgb(var(--lt-ink))] transition-all hover:bg-green-700"
          >
            <Play className="h-3 w-3 fill-current" /> Open in Backtest
          </button>
        ) : (
          <span
            title="Save the strategy to run a backtest"
            className="flex items-center gap-1.5 border-2 border-ink bg-green-600/40 px-3 py-1.5 font-mono text-[10px] font-bold uppercase tracking-wide text-bone/80"
          >
            <Play className="h-3 w-3 fill-current" /> Open in Backtest
          </span>
        )}

        {/* Compact Copilot launcher — replaces the floating FAB inside the builder. */}
        <button
          type="button"
          onClick={toggleCopilot}
          title="Ask Copilot"
          className="flex h-8 w-8 flex-none items-center justify-center border-2 border-orange-500 bg-ink transition-colors hover:bg-ink/80"
        >
          <MagicIcon className="h-4 w-4 text-orange-500" />
        </button>
      </div>
    </div>
  );
}
