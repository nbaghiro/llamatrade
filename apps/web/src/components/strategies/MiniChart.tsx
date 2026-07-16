/**
 * Mini equity curve chart with optional benchmark comparison line.
 */

interface MiniChartProps {
  data: number[];
  benchmarkData?: number[];
  positive: boolean;
  width?: number;
  height?: number;
  showBenchmark?: boolean;
  /** Render the shaded area under the strategy line (off for bare sparklines). */
  showFill?: boolean;
  /** Dash the strategy line — used for draft/paused (not-yet-deployed) rows. */
  dashed?: boolean;
  /** Scale to the container width (viewBox) instead of rendering at a fixed pixel width. */
  fluid?: boolean;
  className?: string;
}

export function MiniChart({
  data,
  benchmarkData = [],
  positive,
  width = 140,
  height = 44,
  showBenchmark = true,
  showFill = true,
  dashed = false,
  fluid = false,
  className,
}: MiniChartProps) {
  // Calculate combined min/max for both lines to share the same scale
  const allValues = showBenchmark && benchmarkData.length > 0
    ? [...data, ...benchmarkData]
    : data;
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const range = max - min || 1;

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
    <svg
      {...(fluid
        ? { viewBox: `0 0 ${width} ${height}`, width: '100%', height, preserveAspectRatio: 'none' as const }
        : { width, height })}
      className={`overflow-visible ${className ?? ''}`}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={positive ? '#0f7a34' : '#c81e1e'} stopOpacity="0.15" />
          <stop offset="100%" stopColor={positive ? '#0f7a34' : '#c81e1e'} stopOpacity="0" />
        </linearGradient>
      </defs>
      {showFill && <polygon points={fillPoints} fill={`url(#${gradientId})`} />}
      {showBenchmark && benchmarkPoints && (
        <polyline
          points={benchmarkPoints}
          fill="none"
          stroke="#7a7362"
          strokeWidth="1.5"
          strokeDasharray="3,2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}
      <polyline
        points={strategyPoints}
        fill="none"
        stroke={positive ? '#0f7a34' : '#c81e1e'}
        strokeWidth="2"
        strokeDasharray={dashed ? '4 3' : undefined}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
