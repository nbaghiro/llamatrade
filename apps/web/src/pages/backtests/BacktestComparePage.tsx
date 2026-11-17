import { useBacktestStore } from '@llamatrade/core/stores/backtest';
import { AlertTriangle, Columns2, Download } from 'lucide-react';
import { useEffect, useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { CompareChart } from '../../components/backtest/CompareChart';
import { compareColor } from '../../components/backtest/compareColors';
import { CompareHeld } from '../../components/backtest/CompareHeld';
import { csvRow, downloadText } from '../../components/backtest/files';
import { Panel } from '../../components/backtest/parts';
import { runMeta, toCurve } from '../../components/backtest/runData';
import { strategyNameOf } from '../../components/backtest/runLabels';
import { T } from '../../components/backtest/tableStyles';
import { useRunTrades } from '../../components/backtest/useRunTrades';
import { DrawdownBand } from '../../components/charts';
import { EmptyState } from '../../components/ui/EmptyState';
import { Pct } from '../../components/ui/Num';
import { PageHead } from '../../components/ui/PageHead';
import { PanelError } from '../../components/ui/PanelError';
import { SkeletonChart, SkeletonRows } from '../../components/ui/Skeleton';
import {
  commonRange,
  COMPARE_SOFT_LIMIT,
  dayKey,
  drawdownOf,
  figuresFromCurve,
  parseRunIds,
  rangeLabel,
  type PerfFigures,
} from '../../lib/backtestView';
import { formatMoney, formatNumber, formatPct } from '../../lib/format';

interface Row {
  id: string;
  label: string;
  color: string | null;
  figures: PerfFigures | null;
  trades: number | null;
}

/** /backtests/compare?runs=a,b,c: one chart over the shared range and one metrics table. */
export default function BacktestComparePage() {
  const [params] = useSearchParams();
  const runsParam = params.get('runs');
  const ids = useMemo(() => parseRunIds(runsParam), [runsParam]);
  const comparison = useBacktestStore((s) => s.comparison);
  const loadComparison = useBacktestStore((s) => s.loadComparison);
  const strategies = useBacktestStore((s) => s.strategies);
  const fetchStrategies = useBacktestStore((s) => s.fetchStrategies);

  useEffect(() => {
    fetchStrategies().catch(() => undefined);
  }, [fetchStrategies]);

  useEffect(() => {
    if (ids.length) loadComparison(ids).catch(() => undefined);
  }, [ids, loadComparison]);

  const model = useMemo(() => {
    const runs = comparison.runs.filter((r) => toCurve(r.results?.equityCurve).values.length > 1);
    if (runs.length < 2) return null;
    const benchRun = runs.find((r) => (r.results?.benchmarkEquityCurve.length ?? 0) > 1);
    const bench = benchRun ? runMeta(benchRun).benchmark || 'Benchmark' : null;
    const curves = runs.map((r) => toCurve(r.results?.equityCurve));
    const range = commonRange(
      benchRun ? [...curves, toCurve(benchRun.results?.benchmarkEquityCurve)] : curves
    );
    if (!range) return { runs, bench, range: null, rows: [] as Row[] };
    const label = (i: number) => {
      const r = runs[i];
      return `${strategyNameOf(strategies, r.strategyId)} v${r.strategyVersion}`;
    };
    const rows: Row[] = runs.map((r, i) => ({
      id: r.id,
      label: label(i),
      color: compareColor(i),
      figures: figuresFromCurve(range.series[i]),
      trades: comparison.metrics[r.id]?.totalTrades ?? null,
    }));
    if (bench) {
      rows.push({
        id: 'benchmark',
        label: bench,
        color: null,
        figures: figuresFromCurve(range.series[runs.length]),
        trades: null,
      });
    }
    const capitals = new Set(runs.map((r) => runMeta(r).capital));
    const benchmarks = new Set(runs.map((r) => runMeta(r).benchmark).filter(Boolean));
    return {
      runs,
      bench,
      range,
      rows,
      sameCapital: capitals.size === 1 ? [...capitals][0] : null,
      mixedBench: benchmarks.size > 1,
    };
  }, [comparison.runs, comparison.metrics, strategies]);

  const pairIds = useMemo(() => model?.runs.slice(0, 2).map((r) => r.id) ?? [], [model]);
  const pairTrades = useRunTrades(pairIds);

  const missing = ids.length - comparison.runs.length;
  const title = `Compare ${ids.length} runs`;

  if (ids.length < 2) {
    return (
      <div className="page grid gap-3.5">
        <PageHead title="Compare backtests" />
        <Panel>
          <EmptyState
            icon={Columns2}
            title="Pick two or more runs to compare"
            body="Tick completed runs in the history and press Compare. They're drawn over the dates they share."
            actions={
              <Link to="/backtests" className="btn btn-primary">
                Open history
              </Link>
            }
          />
        </Panel>
      </div>
    );
  }

  const exportCsv = () => {
    if (!model?.rows.length) return;
    const lines = [
      csvRow([
        'run',
        'total_return',
        'cagr',
        'sharpe',
        'sortino',
        'max_drawdown',
        'volatility',
        'trades',
      ]),
      ...model.rows.map((r) =>
        csvRow([
          r.label,
          r.figures?.totalReturn.toFixed(6) ?? '',
          r.figures?.cagr.toFixed(6) ?? '',
          r.figures?.sharpe.toFixed(4) ?? '',
          r.figures?.sortino.toFixed(4) ?? '',
          r.figures?.maxDrawdown.toFixed(6) ?? '',
          r.figures?.volatility.toFixed(6) ?? '',
          r.trades ?? '',
        ])
      ),
    ];
    downloadText('backtest-comparison.csv', lines.join('\n'));
  };

  const meta = model?.range ? (
    <span className="num">
      {dayKey(model.range.start)} → {dayKey(model.range.end)}
      {model.sameCapital ? ` · ${formatMoney(model.sameCapital, { dp: 0 })} each` : ''}
      {model.bench ? ` · benchmark ${model.bench}` : ''}
    </span>
  ) : undefined;

  return (
    <div className="page grid gap-3.5">
      <PageHead
        title={title}
        sub={meta}
        actions={
          <>
            <Link to={`/backtests?select=${ids.join(',')}`} className="btn btn-secondary">
              Add a run
            </Link>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={!model?.rows.length}
              onClick={exportCsv}
            >
              <Download className="h-3.5 w-3.5" aria-hidden="true" />
              Export CSV
            </button>
          </>
        }
      />
      {ids.length > COMPARE_SOFT_LIMIT && (
        <p
          role="status"
          className="m-0 flex items-center gap-2 rounded-[8px] border border-risk-line bg-risk-soft px-3 py-2 text-[12.5px]"
        >
          <AlertTriangle className="h-4 w-4 flex-none text-risk" aria-hidden="true" />
          {ids.length} runs are selected. More than {COMPARE_SOFT_LIMIT} lines get hard to read; the
          table stays exact.
        </p>
      )}
      {missing > 0 && !comparison.loading && !comparison.error && (
        <p className="m-0 text-[12.5px] text-fg-2">
          {missing} of the selected runs couldn&apos;t be loaded and {missing === 1 ? 'is' : 'are'}{' '}
          left out.
        </p>
      )}

      {comparison.error ? (
        <Panel>
          <PanelError
            title="These runs couldn't be compared"
            cause={comparison.error}
            onRetry={() => loadComparison(ids)}
            retrying={comparison.loading}
          />
        </Panel>
      ) : comparison.loading || !comparison.ids.length ? (
        <>
          <Panel>
            <div className="p-3.5">
              <SkeletonChart height={300} />
            </div>
          </Panel>
          <Panel>
            <SkeletonRows rows={ids.length + 1} cols={7} />
          </Panel>
        </>
      ) : !model || !model.range ? (
        <Panel>
          <EmptyState
            icon={Columns2}
            title="These runs share no dates"
            body="Compared runs are cut to the dates they all cover. Pick completed runs whose ranges overlap."
            actions={
              <Link to="/backtests" className="btn btn-primary">
                Open history
              </Link>
            }
          />
        </Panel>
      ) : (
        <>
          <Panel>
            <div className="px-3.5 py-3">
              <div className="mb-1.5 flex flex-wrap gap-3.5 text-[11.5px] text-fg-2">
                {model.rows.map((r) => (
                  <span key={r.id} className="inline-flex items-center gap-1.5">
                    <i
                      aria-hidden="true"
                      className={`w-3.5 ${r.color ? 'border-t-[1.5px]' : 'border-t border-dashed border-fg-3'}`}
                      style={r.color ? { borderColor: r.color } : undefined}
                    />
                    {r.label}
                  </span>
                ))}
              </div>
              <CompareChart
                dates={model.range.dates}
                lines={model.rows.map((r, i) => ({
                  label: r.label,
                  values: model.range.series[i],
                  bench: r.color === null,
                }))}
              />
              <div className="mt-2 text-[11px] font-medium text-fg-3">
                Drawdown from peak, {model.rows[0].label}
              </div>
              <DrawdownBand
                dates={model.range.dates}
                drawdown={drawdownOf(model.range.series[0])}
                height={70}
              />
            </div>
          </Panel>
          {model.runs.length >= 2 && model.runs[0].strategyId === model.runs[1].strategyId && (
            <Panel
              title={`${model.rows[0].label} against ${model.rows[1].label}`}
              aside={model.runs.length > 2 ? 'the first two runs' : 'what each held'}
            >
              <div className="px-3.5 py-3">
                <CompareHeld
                  dates={model.range.dates}
                  a={model.range.series[0]}
                  b={model.range.series[1]}
                  aLabel={model.rows[0].label}
                  bLabel={model.rows[1].label}
                  aTrades={pairTrades ? (pairTrades[model.rows[0].id] ?? []) : null}
                  bTrades={pairTrades ? (pairTrades[model.rows[1].id] ?? []) : null}
                />
              </div>
            </Panel>
          )}
          <Panel
            footer={
              <>
                Worked out over {rangeLabel(model.range.start, model.range.end)} from daily closes,
                the way the engine does it: 252 trading days and a 2% risk-free rate.
                {model.mixedBench
                  ? ' The runs used different benchmarks; the line shown is the first one.'
                  : ''}
              </>
            }
          >
            <div className="overflow-x-auto">
              <table className={T.table}>
                <thead>
                  <tr>
                    <th className={T.th}>Run</th>
                    <th className={T.thN}>Total return</th>
                    <th className={T.thN}>CAGR</th>
                    <th className={T.thN}>Sharpe</th>
                    <th className={T.thN}>Sortino</th>
                    <th className={T.thN}>Max drawdown</th>
                    <th className={T.thN}>Volatility</th>
                    <th className={T.thN}>Trades</th>
                  </tr>
                </thead>
                <tbody>
                  {model.rows.map((r) => {
                    const f = r.figures;
                    const dim = r.color === null;
                    return (
                      <tr key={r.id} className={dim ? 'text-fg-3' : ''}>
                        <td className={`${T.td} h-9`}>
                          <span className="inline-flex items-center gap-2">
                            <span
                              aria-hidden="true"
                              className={`h-2 w-2 rounded-[2px] ${r.color ? '' : 'ring-1 ring-inset ring-fg-3'}`}
                              style={r.color ? { background: r.color } : undefined}
                            />
                            {r.color ? (
                              <Link
                                to={`/backtest/${r.id}`}
                                className="font-semibold text-fg hover:underline"
                              >
                                {r.label}
                              </Link>
                            ) : (
                              r.label
                            )}
                          </span>
                        </td>
                        <td className={T.tdN}>
                          {f ? <Pct value={f.totalReturn} pnl dp={1} /> : '·'}
                        </td>
                        <td className={T.tdN}>{f ? <Pct value={f.cagr} pnl dp={1} /> : '·'}</td>
                        <td className={T.tdN}>{f ? formatNumber(f.sharpe, { dp: 2 }) : '·'}</td>
                        <td className={T.tdN}>{f ? formatNumber(f.sortino, { dp: 2 }) : '·'}</td>
                        <td className={T.tdN}>
                          {f ? <Pct value={f.maxDrawdown} pnl dp={1} /> : '·'}
                        </td>
                        <td className={T.tdN}>{f ? formatPct(f.volatility, { dp: 1 }) : '·'}</td>
                        <td className={T.tdN}>
                          {r.trades === null ? '·' : formatNumber(r.trades, { dp: 0 })}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}
