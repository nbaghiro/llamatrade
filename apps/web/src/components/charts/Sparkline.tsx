import { linePath, yDomain, type Plot } from '../../lib/chart/scale';

interface SparklineProps {
  values: readonly number[];
  width?: number;
  height?: number;
  /** Accent by default; gain and loss only when the line is profit and loss. */
  tone?: 'accent' | 'neutral' | 'gain' | 'loss';
  label?: string;
  className?: string;
}

const STROKE = {
  accent: 'rgb(var(--accent))',
  neutral: 'rgb(var(--fg-3))',
  gain: 'rgb(var(--gain))',
  loss: 'rgb(var(--loss))',
} as const;

export function Sparkline({
  values,
  width = 90,
  height = 24,
  tone = 'accent',
  label,
  className = '',
}: SparklineProps) {
  if (values.length < 2)
    return <svg width={width} height={height} className={className} aria-hidden="true" />;
  const plot: Plot = {
    width,
    height,
    pad: { t: 1.5, r: 0, b: 1.5, l: 0 },
    domain: yDomain([values], { base: Math.min(...values), ceil: Math.max(...values) }),
    count: values.length,
  };
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={`block ${className}`}
    >
      <path
        d={linePath(plot, values)}
        fill="none"
        stroke={STROKE[tone]}
        strokeWidth={1.4}
        strokeLinejoin="round"
      />
    </svg>
  );
}
