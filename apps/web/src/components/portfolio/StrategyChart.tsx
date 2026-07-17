/**
 * Equity-curve panel: blended portfolio line plus per-strategy lines and a
 * benchmark reference, with an inline-return legend and CSV export.
 */

import type { Benchmark, EquityPoint, Period, StrategyPerformance } from '@llamatrade/core/stores/portfolio';
import { useMemo, useState } from 'react';


interface StrategyChartProps {
  strategies: StrategyPerformance[];
  portfolioCurve: EquityPoint[];
  benchmarkData: EquityPoint[];
  selectedPeriod: Period;
  selectedBenchmark: Benchmark;
  visibleStrategyIds: Set<string>;
  hoveredStrategyId: string | null;
  onPeriodChange: (period: Period) => void;
  onBenchmarkChange: (benchmark: Benchmark) => void;
  onToggleVisibility: (id: string) => void;
  onHoverStrategy: (id: string | null) => void;
}

const PERIODS: Period[] = ['1D', '1W', '1M', '3M', '1Y', 'YTD', 'ALL'];
const BENCHMARKS: { value: Benchmark; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'SPY', label: 'SPY' },
  { value: 'QQQ', label: 'QQQ' },
  { value: 'IWM', label: 'IWM' },
  { value: 'DIA', label: 'DIA' },
];

// Benchmark is a recessive dashed reference line: warm neutral so it doesn't compete with the blue strategy series.
const BENCHMARK_COLOR = '#7a7362'; // Monolith warm-neutral (gray-500)
const PORTFOLIO_COLOR = '#0d0d0d'; // Monolith ink — the aggregate hero line

function formatDateShort(date: Date): string {
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatDateFull(date: Date): string {
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function formatPercent(value: number, digits = 2): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(digits)}%`;
}

function lastValue(curve: EquityPoint[]): number {
  return curve.length > 0 ? curve[curve.length - 1].value : 0;
}

export default function StrategyChart({
  strategies,
  portfolioCurve,
  benchmarkData,
  selectedPeriod,
  selectedBenchmark,
  visibleStrategyIds,
  hoveredStrategyId,
  onPeriodChange,
  onBenchmarkChange,
  onToggleVisibility,
  onHoverStrategy,
}: StrategyChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [showBenchmarkDropdown, setShowBenchmarkDropdown] = useState(false);

  const visibleStrategies = useMemo(
    () => strategies.filter((s) => visibleStrategyIds.has(s.id)),
    [strategies, visibleStrategyIds]
  );

  const chartBounds = useMemo(() => {
    const allValues: number[] = [];
    let maxLength = 0;

    visibleStrategies.forEach((s) => {
      s.equityCurve.forEach((p) => allValues.push(p.value));
      maxLength = Math.max(maxLength, s.equityCurve.length);
    });

    portfolioCurve.forEach((p) => allValues.push(p.value));
    maxLength = Math.max(maxLength, portfolioCurve.length);

    if (selectedBenchmark !== 'none') {
      benchmarkData.forEach((p) => allValues.push(p.value));
      maxLength = Math.max(maxLength, benchmarkData.length);
    }

    if (allValues.length === 0) {
      return { minValue: -10, maxValue: 10, dataLength: 30 };
    }

    const minValue = Math.min(...allValues, 0); // Always include 0
    const maxValue = Math.max(...allValues, 0);
    const padding = Math.max((maxValue - minValue) * 0.1, 2);

    return {
      minValue: minValue - padding,
      maxValue: maxValue + padding,
      dataLength: maxLength,
    };
  }, [visibleStrategies, portfolioCurve, benchmarkData, selectedBenchmark]);

  const width = 1000;
  const height = 320;
  const padding = { top: 30, right: 60, bottom: 50, left: 60 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  const xScale = (i: number) =>
    padding.left + (i / Math.max(chartBounds.dataLength - 1, 1)) * chartWidth;
  const yScale = (value: number) => {
    const range = chartBounds.maxValue - chartBounds.minValue;
    if (range === 0) return padding.top + chartHeight / 2;
    return padding.top + chartHeight - ((value - chartBounds.minValue) / range) * chartHeight;
  };

  const yTicks = useMemo(() => {
    const tickCount = 5;
    const range = chartBounds.maxValue - chartBounds.minValue;
    const step = range / (tickCount - 1);
    return Array.from({ length: tickCount }, (_, i) => chartBounds.minValue + i * step);
  }, [chartBounds]);

  const xTicks = useMemo(() => {
    const dataLength = chartBounds.dataLength;
    if (dataLength <= 1) return [0];
    const count = Math.min(6, dataLength);
    const step = Math.floor((dataLength - 1) / (count - 1));
    return Array.from({ length: count }, (_, i) => Math.min(i * step, dataLength - 1));
  }, [chartBounds.dataLength]);

  const getLinePath = (curve: EquityPoint[]) => {
    if (curve.length === 0) return '';
    return curve.map((p, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)},${yScale(p.value)}`).join(' ');
  };

  const portfolioAreaPath = useMemo(() => {
    if (portfolioCurve.length === 0) return '';
    const line = portfolioCurve
      .map((p, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)},${yScale(p.value)}`)
      .join(' ');
    const lastX = xScale(portfolioCurve.length - 1);
    const baseY = padding.top + chartHeight;
    return `${line} L ${lastX},${baseY} L ${xScale(0)},${baseY} Z`;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [portfolioCurve, chartBounds]);

  const getDateAtIndex = (index: number): Date => {
    const source = portfolioCurve[index] ?? visibleStrategies[0]?.equityCurve[index];
    if (source) return new Date(source.timestamp);
    const date = new Date();
    date.setDate(date.getDate() - (chartBounds.dataLength - 1 - index));
    return date;
  };

  const tooltipData = useMemo(() => {
    if (hoveredIndex === null) return null;

    const date = getDateAtIndex(hoveredIndex);
    const values: { name: string; color: string; value: number }[] = [];

    if (portfolioCurve[hoveredIndex]) {
      values.push({ name: 'Portfolio', color: PORTFOLIO_COLOR, value: portfolioCurve[hoveredIndex].value });
    }

    visibleStrategies.forEach((s) => {
      const point = s.equityCurve[hoveredIndex];
      if (point) values.push({ name: s.name, color: s.color, value: point.value });
    });

    if (selectedBenchmark !== 'none' && benchmarkData[hoveredIndex]) {
      values.push({ name: selectedBenchmark, color: BENCHMARK_COLOR, value: benchmarkData[hoveredIndex].value });
    }

    return { date, values };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hoveredIndex, visibleStrategies, portfolioCurve, benchmarkData, selectedBenchmark]);

  const zeroY = yScale(0);

  const handleExportCsv = () => {
    const columns = [
      'timestamp',
      'portfolio',
      ...visibleStrategies.map((s) => s.name),
      ...(selectedBenchmark !== 'none' ? [selectedBenchmark] : []),
    ];
    const rowCount = Math.max(
      portfolioCurve.length,
      ...visibleStrategies.map((s) => s.equityCurve.length),
      selectedBenchmark !== 'none' ? benchmarkData.length : 0
    );
    if (rowCount === 0) return;

    const lines = [columns.join(',')];
    for (let i = 0; i < rowCount; i++) {
      const ts = portfolioCurve[i]?.timestamp ?? visibleStrategies[0]?.equityCurve[i]?.timestamp ?? '';
      const cells = [
        ts,
        portfolioCurve[i]?.value?.toFixed(4) ?? '',
        ...visibleStrategies.map((s) => s.equityCurve[i]?.value?.toFixed(4) ?? ''),
        ...(selectedBenchmark !== 'none' ? [benchmarkData[i]?.value?.toFixed(4) ?? ''] : []),
      ];
      lines.push(cells.join(','));
    }

    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'portfolio-equity-curve.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const chipBase =
    'font-mono text-[10px] font-bold uppercase tracking-wide border-[1.5px] border-ink px-2 py-1 transition-colors';

  return (
    <div className="bg-paper border-2 border-ink shadow">
      <div className="flex items-center justify-between px-[18px] py-3.5 border-b-2 border-ink gap-3 flex-wrap">
        <span className="font-mono text-[11.5px] font-bold uppercase tracking-[0.1em] text-ink">
          Equity Curve · Portfolio vs Benchmark
        </span>

        <div className="flex items-center gap-3">
          <div className="relative">
            <button
              onClick={() => setShowBenchmarkDropdown(!showBenchmarkDropdown)}
              className="font-mono text-[10.5px] font-bold uppercase tracking-wide border-2 border-ink px-2.5 py-1 bg-bone shadow-[2px_2px_0_#0d0d0d]"
            >
              vs {selectedBenchmark === 'none' ? 'None' : selectedBenchmark} ▾
            </button>

            {showBenchmarkDropdown && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setShowBenchmarkDropdown(false)} />
                <div className="absolute right-0 top-full mt-1 bg-paper border-2 border-ink shadow z-20 py-1 min-w-[100px]">
                  {BENCHMARKS.map((b) => (
                    <button
                      key={b.value}
                      onClick={() => {
                        onBenchmarkChange(b.value);
                        setShowBenchmarkDropdown(false);
                      }}
                      className={`w-full px-3 py-1.5 text-left text-sm font-mono hover:bg-bone ${
                        selectedBenchmark === b.value ? 'text-orange-500 font-bold' : 'text-ink/70'
                      }`}
                    >
                      {b.label}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>

          <div className="flex gap-1.5">
            {PERIODS.map((period) => (
              <button
                key={period}
                onClick={() => onPeriodChange(period)}
                className={`${chipBase} ${
                  selectedPeriod === period
                    ? 'bg-ink text-bone'
                    : 'text-ink/70 hover:bg-bone'
                }`}
              >
                {period}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="relative px-[18px] pt-4">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-auto"
          preserveAspectRatio="xMidYMid meet"
          onMouseLeave={() => setHoveredIndex(null)}
        >
          {yTicks.map((tick, i) => (
            <line
              key={i}
              x1={padding.left}
              y1={yScale(tick)}
              x2={width - padding.right}
              y2={yScale(tick)}
              stroke="#0d0d0d"
              strokeOpacity={tick === 0 ? 0.3 : 0.14}
              strokeWidth={tick === 0 ? 1 : 0.5}
            />
          ))}

          <line
            x1={padding.left}
            y1={zeroY}
            x2={width - padding.right}
            y2={zeroY}
            stroke="#0d0d0d"
            strokeOpacity={0.3}
          />

          {portfolioAreaPath && <path d={portfolioAreaPath} fill="#0d0d0d" fillOpacity={0.06} />}

          {selectedBenchmark !== 'none' && benchmarkData.length > 0 && (
            <path
              d={getLinePath(benchmarkData)}
              fill="none"
              stroke={BENCHMARK_COLOR}
              strokeWidth="2"
              strokeDasharray="6 4"
              opacity={hoveredStrategyId ? 0.3 : 0.7}
            />
          )}

          {visibleStrategies.map((strategy) => {
            const isHovered = hoveredStrategyId === strategy.id;
            const isDimmed = hoveredStrategyId && !isHovered;
            return (
              <path
                key={strategy.id}
                d={getLinePath(strategy.equityCurve)}
                fill="none"
                stroke={strategy.color}
                strokeWidth={isHovered ? 3 : 2}
                strokeLinecap="round"
                strokeLinejoin="round"
                opacity={isDimmed ? 0.2 : 0.9}
                style={{ transition: 'opacity 0.15s, stroke-width 0.15s' }}
              />
            );
          })}

          {portfolioCurve.length > 0 && (
            <path
              d={getLinePath(portfolioCurve)}
              fill="none"
              stroke={PORTFOLIO_COLOR}
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
              opacity={hoveredStrategyId ? 0.35 : 1}
            />
          )}

          {/* End-of-series dots */}
          {visibleStrategies.map((s) =>
            s.equityCurve.length > 0 ? (
              <circle
                key={`dot-${s.id}`}
                cx={xScale(s.equityCurve.length - 1)}
                cy={yScale(lastValue(s.equityCurve))}
                r={3.5}
                fill={s.color}
              />
            ) : null
          )}
          {portfolioCurve.length > 0 && (
            <circle
              cx={xScale(portfolioCurve.length - 1)}
              cy={yScale(lastValue(portfolioCurve))}
              r={4}
              fill={PORTFOLIO_COLOR}
            />
          )}

          {yTicks.map((tick, i) => (
            <text
              key={i}
              x={padding.left - 10}
              y={yScale(tick)}
              textAnchor="end"
              dominantBaseline="middle"
              className="fill-ink text-[11px] font-mono"
            >
              {tick >= 0 ? '+' : ''}
              {tick.toFixed(1)}%
            </text>
          ))}

          {xTicks.map((idx) => (
            <text
              key={idx}
              x={xScale(idx)}
              y={height - padding.bottom + 20}
              textAnchor="middle"
              className="fill-ink text-[11px] font-mono"
            >
              {formatDateShort(getDateAtIndex(idx))}
            </text>
          ))}

          {/* Invisible hover targets */}
          {Array.from({ length: chartBounds.dataLength }).map((_, i) => (
            <rect
              key={i}
              x={xScale(i) - chartWidth / chartBounds.dataLength / 2}
              y={padding.top}
              width={chartWidth / chartBounds.dataLength}
              height={chartHeight}
              fill="transparent"
              onMouseEnter={() => setHoveredIndex(i)}
            />
          ))}

          {hoveredIndex !== null && (
            <line
              x1={xScale(hoveredIndex)}
              y1={padding.top}
              x2={xScale(hoveredIndex)}
              y2={height - padding.bottom}
              stroke="#0d0d0d"
              strokeOpacity={0.3}
              strokeDasharray="2 2"
            />
          )}

          {hoveredIndex !== null &&
            visibleStrategies.map((strategy) => {
              const point = strategy.equityCurve[hoveredIndex];
              if (!point) return null;
              return (
                <circle
                  key={strategy.id}
                  cx={xScale(hoveredIndex)}
                  cy={yScale(point.value)}
                  r="5"
                  fill={strategy.color}
                  stroke="#ffffff"
                  strokeWidth="2"
                />
              );
            })}
        </svg>

        {tooltipData && hoveredIndex !== null && (
          <div
            className="absolute bg-paper border-2 border-ink shadow p-3 pointer-events-none z-10 font-mono"
            style={{
              left: `${((xScale(hoveredIndex) / width) * 100).toFixed(1)}%`,
              top: '40px',
              transform: 'translateX(-50%)',
            }}
          >
            <p className="text-sm font-bold uppercase tracking-wide text-ink mb-2">
              {formatDateFull(tooltipData.date)}
            </p>
            <div className="space-y-1.5">
              {tooltipData.values.map((v, i) => (
                <div key={i} className="flex items-center justify-between gap-4 text-sm">
                  <div className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 border border-ink" style={{ backgroundColor: v.color }} />
                    <span className="text-ink/60">{v.name}</span>
                  </div>
                  <span className={`font-bold tabular-nums ${v.value >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {formatPercent(v.value)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center gap-4 flex-wrap font-mono text-[10.5px] font-bold uppercase tracking-wide text-ink/70 px-[18px] pt-2.5 pb-4 border-t border-line">
        {portfolioCurve.length > 0 && (
          <span className="flex items-center gap-2">
            <span className="inline-block w-4 h-1 bg-ink" />
            Portfolio <span className="text-ink/50">{formatPercent(lastValue(portfolioCurve))}</span>
          </span>
        )}

        {strategies.map((strategy) => {
          const isVisible = visibleStrategyIds.has(strategy.id);
          const isHovered = hoveredStrategyId === strategy.id;
          return (
            <button
              key={strategy.id}
              onClick={() => onToggleVisibility(strategy.id)}
              onMouseEnter={() => onHoverStrategy(strategy.id)}
              onMouseLeave={() => onHoverStrategy(null)}
              className={`flex items-center gap-2 transition-opacity ${isVisible ? 'opacity-100' : 'opacity-40'} ${
                isHovered ? 'text-ink' : ''
              }`}
            >
              <span
                className="inline-block w-4 h-[3px]"
                style={{ backgroundColor: isVisible ? strategy.color : 'transparent', outline: `2px solid ${strategy.color}` }}
              />
              {strategy.name}
              <span className="text-ink/50">{formatPercent(lastValue(strategy.equityCurve), 1)}</span>
            </button>
          );
        })}

        {selectedBenchmark !== 'none' && (
          <span className="flex items-center gap-2">
            <span className="inline-block w-4 border-t-2 border-dashed" style={{ borderColor: BENCHMARK_COLOR }} />
            {selectedBenchmark} <span className="text-ink/50">{formatPercent(lastValue(benchmarkData), 1)}</span>
          </span>
        )}

        <button
          onClick={handleExportCsv}
          className="ml-auto font-mono text-[10.5px] font-bold uppercase tracking-wide text-orange-500 hover:text-orange-600"
        >
          Export CSV →
        </button>
      </div>
    </div>
  );
}
