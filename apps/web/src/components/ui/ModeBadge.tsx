export type AccountMode = 'live' | 'paper';

interface ModeBadgeProps {
  mode: AccountMode;
  size?: 'sm' | 'md';
  className?: string;
}

const SIZE = {
  sm: 'h-[17px] px-1.5 text-[9.5px]',
  md: 'h-5 px-2 text-[10.5px]',
} as const;

/** Live in solid ink, paper in a dashed outline, so a live figure never looks simulated. */
export function ModeBadge({ mode, size = 'md', className = '' }: ModeBadgeProps) {
  const tone =
    mode === 'live'
      ? 'border border-fg bg-fg text-canvas'
      : 'border border-dashed border-line-strong text-fg-2';
  return (
    <span
      className={`inline-flex flex-none items-center whitespace-nowrap rounded-full font-semibold uppercase tracking-[0.04em] ${SIZE[size]} ${tone} ${className}`}
      title={
        mode === 'live'
          ? 'Live: orders use real money in your Alpaca account.'
          : "Paper: orders go to Alpaca's paper environment and use no real money."
      }
    >
      {mode === 'live' ? 'Live' : 'Paper'}
    </span>
  );
}
