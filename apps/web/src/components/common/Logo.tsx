export interface LogoProps {
  /** Size of the mark in px. Defaults to 22. */
  size?: number;
  /** Show the LlamaTrade wordmark beside the mark. */
  showText?: boolean;
  className?: string;
}

const BODY: ReadonlyArray<[number, number, number, number]> = [
  [6.4, 4.5, 3.2, 14],
  [10.8, 14.5, 3.2, 10],
  [15.2, 14.5, 3.2, 6],
  [19.6, 15, 3.2, 5.5],
  [24, 14.5, 3.2, 10],
  [28.4, 13, 2, 4.5],
];

/** The Candlesticks mark: a llama drawn as a run of candles, the first one in the accent. */
export function LogoMark({
  size = 22,
  className = '',
  bold = false,
}: {
  size?: number;
  className?: string;
  /** Heavier wicks and slightly wider bodies, for large display sizes. */
  bold?: boolean;
}) {
  const scale = bold ? 1.1 : 1;
  return (
    <svg
      viewBox="0 0 32 32"
      width={size}
      height={size}
      fill="none"
      aria-hidden="true"
      className={`block flex-none ${className}`}
    >
      <path
        d="M8 2v20M12.4 13v16.5M25.6 13v16.5M16.8 12.5v10M21.2 13v9"
        stroke="currentColor"
        strokeWidth={bold ? 1.4 : 1.1}
        strokeLinecap="round"
      />
      <rect
        x={2 - (3.2 * scale - 3.2) / 2}
        y="7"
        width={3.2 * scale}
        height="4"
        rx="0.5"
        style={{ fill: 'rgb(var(--accent))' }}
      />
      {BODY.map(([x, y, w, h]) => (
        <rect
          key={x}
          x={x - (w * scale - w) / 2}
          y={y}
          width={w * scale}
          height={h}
          rx="0.5"
          fill="currentColor"
        />
      ))}
    </svg>
  );
}

export function Logo({ size = 22, showText = false, className = '' }: LogoProps) {
  return (
    <span className={`inline-flex items-center gap-2 text-fg ${className}`}>
      <LogoMark size={size} />
      {showText && (
        <span
          className="font-sans font-semibold leading-none whitespace-nowrap"
          style={{ fontSize: Math.max(13, Math.round(size * 0.68)), letterSpacing: '-0.01em' }}
        >
          LlamaTrade
        </span>
      )}
    </span>
  );
}
