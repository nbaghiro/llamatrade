import { boundsOf, buildPath, sliceByPeriod } from '@llamatrade/core/chart';
import {
  DASHBOARD_PERIODS,
  useDashboardStore,
  type DashboardPeriod,
} from '@llamatrade/core/stores/dashboard';
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';



import { colorForSign, fmtCurrency, fmtSignedCurrency, fmtSignedPercent, UP } from './format';

const CHART_W = 860;
const CHART_H = 250;
const BENCHMARK_COLOR = '#7a7362';

export default function EquityView() {
  const navigate = useNavigate();
  const {
    totalEquity,
    dayPnl,
    totalReturnPercent,
    benchmarkSymbol,
    portfolioCurve,
    benchmarkCurve,
    selectedPeriod,
    setPeriod,
  } = useDashboardStore();

  const { portfolioPath, benchmarkPath, endColor, spyDelta } = useMemo(() => {
    const port = sliceByPeriod(portfolioCurve, selectedPeriod);
    const bench = sliceByPeriod(benchmarkCurve, selectedPeriod);
    const portValues = port.map((p) => p.value);
    const benchValues = bench.map((p) => p.value);
    const { min, max } = boundsOf(portValues, benchValues);
    const last = portValues[portValues.length - 1] ?? 0;
    // SPY window return ≈ change in its cumulative-% between the window ends.
    const delta =
      benchValues.length > 1 ? benchValues[benchValues.length - 1] - benchValues[0] : null;
    return {
      portfolioPath: buildPath(portValues, CHART_W, CHART_H, min, max),
      benchmarkPath: buildPath(benchValues, CHART_W, CHART_H, min, max),
      endColor: colorForSign(last),
      spyDelta: delta,
    };
  }, [portfolioCurve, benchmarkCurve, selectedPeriod]);

  const hasData = portfolioPath.line !== '';
  const areaFill = endColor === UP ? 'rgba(15,122,52,0.12)' : 'rgba(200,30,30,0.12)';

  return (
    <div className="flex flex-col">
      <div className="px-[18px] pt-1 pb-1.5 flex items-start justify-between">
        <div>
          <div className="font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-ink/50">
            Total Equity{benchmarkSymbol ? ` · vs ${benchmarkSymbol}` : ''}
          </div>
          <div className="font-mono font-bold text-[42px] leading-none tabular-nums tracking-[-0.02em] mt-1">
            {fmtCurrency(totalEquity)}
          </div>
          <div className="flex gap-2 mt-2.5 flex-wrap">
            <span
              className="font-mono text-[11px] font-bold uppercase tracking-[0.03em] px-2 py-1 text-bone border-[1.5px]"
              style={{ background: colorForSign(totalReturnPercent), borderColor: colorForSign(totalReturnPercent) }}
            >
              {fmtSignedPercent(totalReturnPercent)} ALL-TIME
            </span>
            <span
              className="font-mono text-[11px] font-bold uppercase tracking-[0.03em] px-2 py-1 bg-paper border-[1.5px] border-ink"
              style={{ color: colorForSign(dayPnl) }}
            >
              {fmtSignedCurrency(dayPnl)} TODAY
            </span>
            {spyDelta !== null && (
              <span className="font-mono text-[11px] font-bold uppercase tracking-[0.03em] px-2 py-1 bg-paper border-[1.5px] border-ink text-ink/55">
                {benchmarkSymbol} {fmtSignedPercent(spyDelta, 1)}
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-1.5 shrink-0">
          {DASHBOARD_PERIODS.map((p: DashboardPeriod) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`font-mono text-[10px] font-bold uppercase tracking-[0.04em] border-[1.5px] border-ink px-1.5 py-1 transition-colors ${
                selectedPeriod === p ? 'bg-ink text-bone' : 'bg-paper text-ink hover:bg-ink/5'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </div>

      <div className="px-3 pb-1.5 pt-0.5 flex-1">
        {hasData ? (
          <svg
            viewBox={`0 0 ${CHART_W} ${CHART_H}`}
            width="100%"
            height={CHART_H}
            preserveAspectRatio="none"
            role="img"
            aria-label="Portfolio equity curve versus benchmark"
          >
            {[0.25, 0.5, 0.75].map((f) => (
              <line
                key={f}
                x1="0"
                y1={CHART_H * f}
                x2={CHART_W}
                y2={CHART_H * f}
                stroke="rgba(13,13,13,0.10)"
              />
            ))}
            <path d={portfolioPath.area} fill={areaFill} />
            {benchmarkPath.line && (
              <path
                d={benchmarkPath.line}
                fill="none"
                stroke={BENCHMARK_COLOR}
                strokeWidth="2"
                strokeDasharray="6 4"
              />
            )}
            <path d={portfolioPath.line} fill="none" stroke={endColor} strokeWidth="2.8" />
            <circle cx={portfolioPath.endX} cy={portfolioPath.endY} r="4" fill={endColor} />
          </svg>
        ) : (
          <div
            className="flex items-center justify-center font-mono text-[11px] uppercase tracking-[0.08em] text-ink/40"
            style={{ height: CHART_H }}
          >
            No equity history yet
          </div>
        )}
      </div>

      <div className="flex gap-4 items-center font-mono text-[10.5px] font-bold uppercase tracking-[0.05em] text-ink/60 px-[18px] pb-3.5">
        <span className="flex items-center gap-1.5">
          <i className="inline-block w-3.5 h-[3px] align-middle" style={{ background: endColor }} />
          Portfolio
        </span>
        {benchmarkPath.line && (
          <span className="flex items-center gap-1.5">
            <i
              className="inline-block w-3.5 align-middle"
              style={{ borderTop: `2px dashed ${BENCHMARK_COLOR}`, height: 0 }}
            />
            {benchmarkSymbol} benchmark
          </span>
        )}
        <button
          onClick={() => navigate('/portfolio')}
          className="ml-auto font-mono text-[10.5px] font-bold uppercase tracking-[0.05em] text-orange-500 hover:underline"
        >
          Open full portfolio →
        </button>
      </div>
    </div>
  );
}
