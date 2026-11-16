interface WeightBarProps {
  /** Current weight as a fraction, 0 to 1. */
  weight: number;
  /** Target weight as a fraction; draws a tick in the accent. */
  target?: number;
  /** Amber fill for a frozen holding. */
  frozen?: boolean;
  /** Bar colour as a CSS colour; defaults to chart-1. */
  color?: string;
  height?: number;
  label?: string;
  /** The true value read aloud when `weight` is scaled for display, e.g. "12.4%". */
  valueText?: string;
  className?: string;
}

const clamp = (v: number) => Math.max(0, Math.min(1, Number.isFinite(v) ? v : 0));

/** A weight with an optional target tick, used for holdings, sleeves and previews. */
export function WeightBar({
  weight,
  target,
  frozen = false,
  color,
  height = 8,
  label,
  valueText,
  className = '',
}: WeightBarProps) {
  const w = clamp(weight);
  return (
    <div
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(w * 1000) / 10}
      aria-valuetext={valueText}
      aria-label={label}
      className={`relative rounded-full bg-sunk ${className}`}
      style={{ height }}
    >
      <i
        className={`absolute inset-y-0 left-0 rounded-full ${frozen ? 'bg-risk' : color ? '' : 'bg-chart-1'}`}
        style={{ width: `${w * 100}%`, background: frozen ? undefined : color }}
      />
      {target !== undefined && (
        <b
          aria-hidden="true"
          className="absolute -top-1 -bottom-1 w-0.5 -ml-px rounded-[1px] bg-accent"
          style={{ left: `${clamp(target) * 100}%` }}
        />
      )}
    </div>
  );
}
