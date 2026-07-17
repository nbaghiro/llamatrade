import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toNumber, useBacktestStore } from '@llamatrade/core/stores/backtest';
import { ChevronDown, LineChart, Play } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';


import { useStrategyBuilderStoreWithContext } from '../../../store/strategy-builder';
import { EquityMiniChart } from '../../strategies/EquityMiniChart';

const signedPct = (v: number): string => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`;

export function RightPanel() {
  const [isPreviewOpen, setIsPreviewOpen] = useState(true);
  const strategyId = useStrategyBuilderStoreWithContext((s) => s.strategyId);
  const fetchLatestCompletedBacktest = useBacktestStore((s) => s.fetchLatestCompletedBacktest);

  const [preview, setPreview] = useState<BacktestRun | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    if (!strategyId) {
      setPreview(null);
      return;
    }
    let cancelled = false;
    setPreviewLoading(true);
    fetchLatestCompletedBacktest(strategyId)
      .then((run) => {
        if (!cancelled) setPreview(run);
      })
      .finally(() => {
        if (!cancelled) setPreviewLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [strategyId, fetchLatestCompletedBacktest]);

  const results = preview?.results;
  const metrics = results?.metrics;
  const equityCurve = (results?.equityCurve ?? []).map((p) => toNumber(p.equity));
  const benchmarkCurve = (results?.benchmarkEquityCurve ?? []).map((p) => toNumber(p.equity));
  const benchmarkSymbol =
    results?.benchmarkSymbol || metrics?.benchmarkSymbol || preview?.config?.benchmarkSymbol || 'SPY';

  // Only metrics the engine populates (see servicer _to_proto_metrics); volatility isn't computed, so it's omitted.
  const stats: [string, string][] = [
    ['CAGR', metrics ? signedPct(toNumber(metrics.annualizedReturn)) : '--'],
    ['Max Drawdown', metrics ? `-${Math.abs(toNumber(metrics.maxDrawdown) * 100).toFixed(1)}%` : '--'],
    ['Sharpe Ratio', metrics ? toNumber(metrics.sharpeRatio).toFixed(2) : '--'],
    ['Sortino Ratio', metrics ? toNumber(metrics.sortinoRatio).toFixed(2) : '--'],
    ['Win Rate', metrics ? `${(toNumber(metrics.winRate) * 100).toFixed(1)}%` : '--'],
  ];

  return (
    <div className="w-[420px] flex-shrink-0 flex flex-col gap-3 p-4 overflow-y-auto">
      <div className="bg-paper border-2 border-ink shadow">
        <button
          onClick={() => setIsPreviewOpen(!isPreviewOpen)}
          className="w-full flex items-center justify-between px-4 py-3 hover:bg-ink/5 transition-colors"
        >
          <span className="text-[11px] font-mono uppercase tracking-wide text-ink/70">Backtest Preview</span>
          <ChevronDown
            className={`w-4 h-4 text-ink/60 transition-transform ${isPreviewOpen ? '' : '-rotate-90'}`}
          />
        </button>

        {isPreviewOpen && (
          <div className="px-3 pb-3">
            {previewLoading ? (
              <div className="h-40 bg-bone border-2 border-ink mb-3 flex items-center justify-center text-[11px] font-mono uppercase tracking-wide text-ink/50">
                Loading preview…
              </div>
            ) : equityCurve.length > 1 ? (
              <div className="bg-bone border-2 border-ink mb-3">
                <EquityMiniChart
                  strategy={equityCurve}
                  benchmark={benchmarkCurve}
                  benchmarkSymbol={benchmarkSymbol}
                />
              </div>
            ) : (
              <div className="h-40 bg-bone border-2 border-ink mb-3 flex flex-col items-center justify-center gap-2 text-center px-4">
                <LineChart className="w-6 h-6 text-ink/30" />
                <span className="text-[11px] font-mono uppercase tracking-wide text-ink/50">
                  Run a backtest to preview
                </span>
              </div>
            )}

            {strategyId ? (
              <Link
                to={`/backtest?strategy=${strategyId}`}
                className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-green-600 hover:bg-green-700 text-bone font-mono font-bold uppercase tracking-wide transition-colors border-2 border-ink shadow"
              >
                <Play className="w-4 h-4 fill-current" />
                <span className="text-sm">Open in Backtest</span>
              </Link>
            ) : (
              <>
                <button
                  disabled
                  className="w-full flex items-center justify-center gap-2 py-2.5 px-4 bg-green-600 text-bone font-mono font-bold uppercase tracking-wide border-2 border-ink shadow opacity-40 cursor-not-allowed"
                >
                  <Play className="w-4 h-4 fill-current" />
                  <span className="text-sm">Open in Backtest</span>
                </button>
                <p className="mt-1.5 text-center text-[11px] font-mono text-ink/45">
                  Save the strategy to run a backtest.
                </p>
              </>
            )}
          </div>
        )}
      </div>

      <div className="bg-paper border-2 border-ink p-4 shadow">
        <h3 className="text-[11px] font-mono uppercase tracking-wide text-ink/70 mb-3">Quick Stats</h3>
        <div className="space-y-2.5 text-sm">
          {stats.map(([label, value]) => (
            <div key={label} className="flex justify-between">
              <span className="text-ink/60">{label}</span>
              <span className="text-ink font-mono tabular-nums">{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
