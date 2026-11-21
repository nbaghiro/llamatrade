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

/**
 * Copilot's mark: one candle whose wick splits into three strokes, an asterisk with the body,
 * in the accent, at its centre. Sized by `size`, or by `className` when `size` is left out.
 */
export function CopilotMark({
  size,
  className = '',
  bold = false,
}: {
  size?: number;
  className?: string;
  bold?: boolean;
}) {
  const w = bold ? 5.3 : 4.8;
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
        d="M16 3.5V28.5M5.2 9.75L26.8 22.25M5.2 22.25L26.8 9.75"
        stroke="currentColor"
        strokeWidth={bold ? 1.9 : 1.7}
        strokeLinecap="round"
      />
      <rect
        x={16 - w / 2}
        y="10"
        width={w}
        height="12"
        rx="0.6"
        style={{ fill: 'rgb(var(--accent))' }}
      />
    </svg>
  );
}

/** The app's brand: the 34px Candlesticks mark with the caps wordmark, as in the top bar. */
export function BrandLockup({ wordClassName = '' }: { wordClassName?: string }) {
  return (
    <span className="flex items-center gap-3 text-fg">
      <LogoMark size={34} bold className="-my-2" />
      <span
        className={`whitespace-nowrap text-[12px] font-semibold uppercase leading-none tracking-[0.16em] ${wordClassName}`}
      >
        LlamaTrade
      </span>
    </span>
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
