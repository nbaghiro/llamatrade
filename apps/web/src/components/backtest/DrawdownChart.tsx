/**
 * Underwater / Drawdown panel.
 * Renders the equity curve's underwater plot (distance below the running peak)
 * with the deepest drawdown and recovery duration.
 */

import { useMemo } from 'react';

import type { BacktestMetrics, EquityPoint } from '@llamatrade/core/proto/backtest_pb';
import { toDate, toNumber } from '@llamatrade/core/stores/backtest';

interface DrawdownChartProps {
  data: EquityPoint[];
  metrics?: BacktestMetrics;
}

const RED = '#c81e1e';
const W = 900;
const H = 90;
const TOP = 3;

function signedPercent(value: number): string {
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`;
}

export default function DrawdownChart({ data, metrics }: DrawdownChartProps) {
  const model = useMemo(() => {
    if (data.length < 2) return null;

    // Magnitude below peak, always >= 0 regardless of the sign convention used.
    const mags = data.map((p) => Math.abs(toNumber(p.drawdown)));
    const deepestMag = Math.max(...mags, 0);
    const troughIndex = mags.indexOf(deepestMag);
    const domainMax = deepestMag > 0 ? deepestMag * 1.1 : 1;

    const x = (i: number) => (i / (data.length - 1)) * W;
    const y = (mag: number) => TOP + (mag / domainMax) * (H - TOP - 3);

    const points = mags.map((m, i) => `${x(i).toFixed(1)},${y(m).toFixed(1)}`);
    const line = `M${points.join(' L')}`;
    const area = `M0,${TOP} L${points.join(' L')} L${W},${TOP} Z`;

    return { line, area, deepestMag, troughDate: toDate(data[troughIndex]?.timestamp) };
  }, [data]);

  const deepest = metrics ? -Math.abs(toNumber(metrics.maxDrawdown)) : model ? -model.deepestMag : 0;
  const recoveryDays = metrics ? Math.round(toNumber(metrics.maxDrawdownDurationDays)) : 0;
  const troughLabel = model?.troughDate
    ? model.troughDate.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
    : null;

  return (
    <div className="bg-paper border-2 border-ink shadow-[4px_4px_0_#0d0d0d]">
      <div className="flex items-center justify-between px-4 py-3 border-b-2 border-ink">
        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.1em]">
          Underwater / Drawdown
        </span>
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.04em] border-[1.5px] border-ink px-1.5 py-[3px]">
          Max {signedPercent(deepest)}
        </span>
      </div>

      <div className="px-4 pt-3 pb-2">
        {model ? (
          <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none">
            <line x1={0} x2={W} y1={TOP} y2={TOP} stroke="#0d0d0d" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
            <path d={model.area} fill={RED} fillOpacity={0.16} />
            <path d={model.line} fill="none" stroke={RED} strokeWidth={2} vectorEffect="non-scaling-stroke" />
          </svg>
        ) : (
          <div className="h-[90px] flex items-center justify-center font-mono text-[11px] uppercase tracking-[0.05em] text-ink/40">
            No drawdown data
          </div>
        )}
      </div>

      <div className="flex items-center justify-between px-4 pb-3 font-mono text-[10px] uppercase tracking-[0.06em] text-ink/50">
        <span>0% — peak</span>
        <span>
          Deepest {signedPercent(deepest)}
          {troughLabel ? ` · ${troughLabel}` : ''}
          {recoveryDays > 0 ? ` · recovered in ${recoveryDays} days` : ''}
        </span>
      </div>
    </div>
  );
}
