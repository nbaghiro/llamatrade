import { formatReturn } from './strategyRow';

const CHART_W = 356;
const CHART_H = 128;
const CHART_PAD = 10;

function toPath(values: number[], min: number, range: number): string {
  return values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * CHART_W;
      const y = CHART_PAD + (CHART_H - CHART_PAD * 2) - ((v - min) / range) * (CHART_H - CHART_PAD * 2);
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
}

function curveReturn(values: number[]): number | null {
  if (values.length < 2 || values[0] === 0) return null;
  return (values[values.length - 1] / values[0] - 1) * 100;
}

interface EquityMiniChartProps {
  strategy: number[];
  benchmark: number[];
  benchmarkSymbol: string;
}

// Compact equity-vs-benchmark sparkline shared by the strategies drawer and the
// builder's backtest preview. Expects at least two strategy points.
export function EquityMiniChart({ strategy, benchmark, benchmarkSymbol }: EquityMiniChartProps) {
  const all = benchmark.length > 1 ? [...strategy, ...benchmark] : strategy;
  const min = Math.min(...all);
  const max = Math.max(...all);
  const range = max - min || 1;
  const line = toPath(strategy, min, range);
  const area = `${line} L${CHART_W},${CHART_H} L0,${CHART_H} Z`;
  const benchLine = benchmark.length > 1 ? toPath(benchmark, min, range) : '';

  const stratRet = curveReturn(strategy);
  const benchRet = curveReturn(benchmark);

  return (
    <div className="px-4 pt-3.5 pb-1.5">
      <svg viewBox={`0 0 ${CHART_W} ${CHART_H}`} width="100%" height={CHART_H} preserveAspectRatio="none">
        <line x1="0" y1={CHART_H * 0.33} x2={CHART_W} y2={CHART_H * 0.33} stroke="rgb(13 13 13 / 0.1)" />
        <line x1="0" y1={CHART_H * 0.66} x2={CHART_W} y2={CHART_H * 0.66} stroke="rgb(13 13 13 / 0.1)" />
        <path d={area} fill="rgb(15 122 52 / 0.12)" />
        <path d={line} fill="none" stroke="#0f7a34" strokeWidth="2.5" />
        {benchLine && (
          <path d={benchLine} fill="none" stroke="rgb(13 13 13 / 0.5)" strokeWidth="2" strokeDasharray="6 4" />
        )}
      </svg>
      <div className="flex gap-4 pt-2.5 pb-1 font-mono text-[9.5px] font-bold uppercase tracking-wide text-ink/60">
        <span className="flex items-center gap-1.5">
          <i className="inline-block w-3 h-[3px] bg-green-500" />
          Strategy{stratRet !== null && ` ${formatReturn(stratRet)}`}
        </span>
        {benchLine && (
          <span className="flex items-center gap-1.5">
            <i className="inline-block w-3 border-t-2 border-dashed border-ink/50" />
            {benchmarkSymbol}{benchRet !== null && ` ${formatReturn(benchRet)}`}
          </span>
        )}
      </div>
    </div>
  );
}
