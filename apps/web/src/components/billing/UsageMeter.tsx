import { meterState } from '@llamatrade/core/billing/usage';

interface UsageMeterProps {
  label: string;
  used: number;
  /** Plan limit for this metric; -1 means unlimited. */
  limit: number;
  /** Replaces the computed note, e.g. "Not available in the beta". */
  note?: string;
}

/** One usage figure against its plan limit. The bar uses the accent; reaching the limit turns the note amber. */
export default function UsageMeter({ label, used, limit, note }: UsageMeterProps) {
  const m = meterState(used, limit);
  const pct = Math.round(m.fraction * 1000) / 10;
  return (
    <div className="min-w-0">
      <div className="flex items-center justify-between gap-2.5 text-[12.5px]">
        <span className="text-fg">{label}</span>
        <span className="num text-fg-2">
          {used.toLocaleString('en-US')} /{' '}
          {m.unlimited ? 'Unlimited' : limit.toLocaleString('en-US')}
        </span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        className="my-1.5 h-1.5 overflow-hidden rounded-[3px] bg-sunk"
      >
        <i className="block h-full bg-accent-fill" style={{ width: `${pct}%` }} />
      </div>
      <span className={`text-[11px] ${m.atLimit && !note ? 'text-risk' : 'text-fg-3'}`}>
        {note ?? m.note}
      </span>
    </div>
  );
}
