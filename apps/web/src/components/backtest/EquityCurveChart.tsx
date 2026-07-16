/**
 * Equity Curve vs Benchmark panel.
 * Plots the strategy equity curve against its benchmark with a value-mode
 * toggle ($ / % / log). Pure SVG, zero chart dependencies.
 */

import { useMemo, useState } from 'react';

import type { BacktestMetrics, EquityPoint } from '../../generated/proto/backtest_pb';
import { toNumber } from '../../store/backtest';

interface EquityCurveChartProps {
  data: EquityPoint[];
  benchmark: EquityPoint[];
  benchmarkSymbol: string;
  strategyName: string;
  metrics?: BacktestMetrics;
}

type ValueMode = 'dollar' | 'pct' | 'log';

const STRATEGY_UP = '#0f7a34';
const STRATEGY_DOWN = '#c81e1e';
const BENCHMARK_COLOR = '#7a7362';
const W = 900;
const H = 250;
const PAD = 14;

function signedPercent(value: number): string {
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);
}

export default function EquityCurveChart({
  data,
  benchmark,
  benchmarkSymbol,
  strategyName,
  metrics,
}: EquityCurveChartProps) {
  const [mode, setMode] = useState<ValueMode>('pct');

  const equities = useMemo(() => data.map((p) => toNumber(p.equity)), [data]);
  const benchEquities = useMemo(() => benchmark.map((p) => toNumber(p.equity)), [benchmark]);

  const chart = useMemo(() => {
    if (equities.length < 2) return null;

    // Plotted value for a series under the active mode.
    const plot = (series: number[]): number[] => {
      if (series.length === 0) return [];
      if (mode === 'pct') {
        const base = series[0] || 1;
        return series.map((v) => (v / base - 1) * 100);
      }
      return series; // dollar + log both plot raw equity (log scales the axis)
    };
    // Axis transform (log compresses the value axis).
    const t = (v: number): number => (mode === 'log' ? Math.log10(Math.max(v, 1e-9)) : v);

    const stratPlot = plot(equities);
    const benchPlot = benchEquities.length >= 2 ? plot(benchEquities) : [];

    const transformed = [...stratPlot, ...benchPlot].map(t);
    let min = Math.min(...transformed);
    let max = Math.max(...transformed);
    if (min === max) {
      min -= 1;
      max += 1;
    }
    const span = max - min;

    const x = (i: number, n: number) => (n <= 1 ? 0 : (i / (n - 1)) * W);
    const y = (v: number) => PAD + (1 - (t(v) - min) / span) * (H - 2 * PAD);

    const linePath = (vals: number[]): string =>
      vals.map((v, i) => `${i === 0 ? 'M' : 'L'} ${x(i, vals.length).toFixed(1)},${y(v).toFixed(1)}`).join(' ');

    const stratLine = linePath(stratPlot);
    const areaPath = `${stratLine} L ${W},${H} L 0,${H} Z`;
    const benchLine = benchPlot.length >= 2 ? linePath(benchPlot) : '';

    return { stratLine, areaPath, benchLine };
  }, [equities, benchEquities, mode]);

  const totalReturn = metrics
    ? toNumber(metrics.totalReturn)
    : equities.length >= 2
      ? equities[equities.length - 1] / (equities[0] || 1) - 1
      : 0;
  const benchmarkReturn = metrics
    ? toNumber(metrics.benchmarkReturn)
    : benchEquities.length >= 2
      ? benchEquities[benchEquities.length - 1] / (benchEquities[0] || 1) - 1
      : 0;
  const finalEquity = metrics
    ? toNumber(metrics.endingCapital)
    : equities[equities.length - 1] ?? 0;
  const stratColor = totalReturn >= 0 ? STRATEGY_UP : STRATEGY_DOWN;
  const hasBenchmark = !!chart?.benchLine && benchEquities.length >= 2;

  const chip = (m: ValueMode, label: string) => (
    <button
      key={m}
      onClick={() => setMode(m)}
      className={`font-mono text-[10px] font-bold uppercase tracking-[0.04em] border-[1.5px] border-ink px-1.5 py-[3px] transition-colors ${
        mode === m ? 'bg-ink text-bone' : 'bg-paper hover:bg-bone'
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="bg-paper border-2 border-ink shadow-[4px_4px_0_#0d0d0d]">
      <div className="flex items-center justify-between px-4 py-3 border-b-2 border-ink">
        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.1em]">
          Equity Curve vs Benchmark
        </span>
        <span className="flex gap-1.5">
          {chip('dollar', '$')}
          {chip('pct', '%')}
          {chip('log', 'Log')}
        </span>
      </div>

      <div className="px-4 pt-3.5 pb-1.5">
        {chart ? (
          <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none">
            {[0.25, 0.5, 0.75].map((f) => (
              <line
                key={f}
                x1={0}
                x2={W}
                y1={PAD + f * (H - 2 * PAD)}
                y2={PAD + f * (H - 2 * PAD)}
                stroke="#0d0d0d"
                strokeOpacity={0.1}
                vectorEffect="non-scaling-stroke"
              />
            ))}
            <path d={chart.areaPath} fill={stratColor} fillOpacity={0.12} />
            {hasBenchmark && (
              <path
                d={chart.benchLine}
                fill="none"
                stroke={BENCHMARK_COLOR}
                strokeWidth={2}
                strokeDasharray="6 4"
                vectorEffect="non-scaling-stroke"
              />
            )}
            <path
              d={chart.stratLine}
              fill="none"
              stroke={stratColor}
              strokeWidth={2.5}
              vectorEffect="non-scaling-stroke"
            />
          </svg>
        ) : (
          <div className="h-[250px] flex items-center justify-center font-mono text-[11px] uppercase tracking-[0.05em] text-ink/40">
            No equity data
          </div>
        )}
      </div>

      <div className="flex items-center gap-4 flex-wrap px-4 pt-0.5 pb-3.5 font-mono text-[10.5px] font-bold uppercase tracking-[0.05em] text-ink/60">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3.5 h-[3px]" style={{ backgroundColor: stratColor }} />
          {strategyName} · <span className={totalReturn >= 0 ? 'text-green-600' : 'text-red-600'}>{signedPercent(totalReturn)}</span>
        </span>
        {hasBenchmark && (
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-3.5 border-t-2 border-dashed" style={{ borderColor: BENCHMARK_COLOR }} />
            {benchmarkSymbol || 'Benchmark'} · {signedPercent(benchmarkReturn)}
          </span>
        )}
        <span className="ml-auto text-ink/45">Final equity {formatCurrency(finalEquity)}</span>
      </div>
    </div>
  );
}
