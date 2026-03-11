/**
 * Reusable mini equity curve chart component.
 * Shows strategy performance line with optional benchmark comparison.
 */

interface MiniChartProps {
  data: number[];
  benchmarkData?: number[];
  positive: boolean;
  width?: number;
  height?: number;
  showBenchmark?: boolean;
}

export function MiniChart({
  data,
  benchmarkData = [],
  positive,
  width = 140,
  height = 44,
  showBenchmark = true,
}: MiniChartProps) {
  // Calculate combined min/max for both lines to share the same scale
  const allValues = showBenchmark && benchmarkData.length > 0
    ? [...data, ...benchmarkData]
    : data;
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const range = max - min || 1;

  // Padding for the chart area
  const paddingY = 4;
  const chartHeight = height - paddingY * 2;

  const toPoints = (values: number[]) =>
    values
      .map((v, i) => {
        const x = (i / (values.length - 1)) * width;
        const y = paddingY + chartHeight - ((v - min) / range) * chartHeight;
        return `${x},${y}`;
      })
      .join(' ');

  const strategyPoints = toPoints(data);
  const benchmarkPoints = showBenchmark && benchmarkData.length > 0 ? toPoints(benchmarkData) : '';
  const fillPoints = `0,${height - paddingY} ${strategyPoints} ${width},${height - paddingY}`;
  const gradientId = `gradient-${positive ? 'pos' : 'neg'}-${Math.random().toString(36).slice(2)}`;

  return (
    <svg width={width} height={height} className="overflow-visible">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={positive ? '#22c55e' : '#ef4444'} stopOpacity="0.15" />
          <stop offset="100%" stopColor={positive ? '#22c55e' : '#ef4444'} stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* Strategy fill area */}
      <polygon points={fillPoints} fill={`url(#${gradientId})`} />
      {/* Benchmark line (SPY) - dashed gray */}
      {showBenchmark && benchmarkPoints && (
        <polyline
          points={benchmarkPoints}
          fill="none"
          stroke="#9ca3af"
          strokeWidth="1.5"
          strokeDasharray="3,2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="dark:stroke-gray-500"
        />
      )}
      {/* Strategy line */}
      <polyline
        points={strategyPoints}
        fill="none"
        stroke={positive ? '#22c55e' : '#ef4444'}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
