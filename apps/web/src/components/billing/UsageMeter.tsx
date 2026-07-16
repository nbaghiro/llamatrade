/**
 * UsageMeter — one real usage figure (used / limit) with a ratio-coloured bar.
 * `used` comes from a live product surface; `limit` from the current plan tier
 * config. A negative limit means "unlimited".
 */

interface UsageMeterProps {
  label: string;
  used: number;
  /** Plan limit for this metric; -1 = unlimited. */
  limit: number;
}

function barColor(ratio: number): string {
  if (ratio >= 1) return 'bg-red-500';
  if (ratio >= 0.8) return 'bg-orange-500';
  return 'bg-green-600';
}

export default function UsageMeter({ label, used, limit }: UsageMeterProps) {
  const unlimited = limit < 0;
  const ratio = unlimited || limit === 0 ? (used > 0 ? 1 : 0) : Math.min(1, used / limit);
  const remaining = Math.max(0, limit - used);
  const atLimit = !unlimited && limit > 0 && used >= limit;

  const note = unlimited
    ? 'Unlimited'
    : atLimit
      ? 'At limit · upgrade for more'
      : `${remaining.toLocaleString('en-US')} remaining`;

  return (
    <div className="border-2 border-ink bg-paper p-4 shadow-[4px_4px_0_rgb(var(--lt-ink))]">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-ink/55">
          {label}
        </span>
        <span className="font-mono text-[13px] font-bold text-ink tabular-nums">
          {used.toLocaleString('en-US')}
          <span className="text-ink/40"> / {unlimited ? '∞' : limit.toLocaleString('en-US')}</span>
        </span>
      </div>

      <div className="mt-3 h-2 w-full border border-ink bg-bone">
        <div
          className={`h-full ${unlimited ? 'bg-green-600' : barColor(ratio)}`}
          style={{ width: `${Math.max(unlimited ? 8 : 0, ratio * 100)}%` }}
        />
      </div>

      <p
        className={`mt-2 font-mono text-[10px] uppercase tracking-wide ${
          atLimit ? 'text-red-600' : 'text-ink/45'
        }`}
      >
        {note}
      </p>
    </div>
  );
}
