import { X } from 'lucide-react';

import { formatMoney } from '../../lib/format';
import type { AccountScope } from '../../lib/scope';
import { ModeBadge, Money, Pct } from '../ui';

export interface AccountHalf {
  kind: 'live' | 'paper';
  /** "Alpaca paper ••PA92". */
  label: string;
  value: number;
  today: number;
  sleeves: readonly { id: string; name: string; value: number }[];
}

interface AccountSplitProps {
  halves: readonly AccountHalf[];
  scope: AccountScope;
  onScope: (scope: AccountScope) => void;
}

/** Narrow halves keep this share of the bar so their figures stay readable. */
const MIN_SHARE = 0.26;

function shares(values: readonly number[]): number[] {
  const total = values.reduce((s, v) => s + Math.max(0, v), 0);
  if (values.length < 2 || total <= 0) return values.map(() => 1 / values.length);
  const raw = values.map((v) => Math.max(0, v) / total);
  const lifted = raw.map((r) => Math.max(MIN_SHARE, r));
  const sum = lifted.reduce((s, v) => s + v, 0);
  return lifted.map((v) => v / sum);
}

/**
 * The two Alpaca accounts as one bar split by size, live solid and paper dashed (accounts2 C).
 * Selecting a half filters the page to that account and dims the other.
 */
export function AccountSplit({ halves, scope, onScope }: AccountSplitProps) {
  const total = halves.reduce((s, h) => s + h.value, 0);
  const widths = shares(halves.map((h) => h.value));
  const choosable = halves.length > 1;

  return (
    <div className="flex flex-col gap-2 md:flex-row" role={choosable ? 'group' : undefined}>
      {halves.map((h, i) => {
        const on = choosable && scope === h.kind;
        const dim = choosable && scope !== 'all' && !on;
        const frame =
          h.kind === 'live'
            ? 'border border-fg'
            : 'border border-dashed border-fg-3 [background-image:repeating-linear-gradient(135deg,transparent_0_7px,rgb(var(--line)/0.35)_7px_8px)]';
        const body = (
          <>
            <div className="flex items-center gap-2 text-[12.5px] text-fg-3">
              <ModeBadge mode={h.kind} size="sm" />
              <span className="truncate">{h.label}</span>
              {total > 0 && choosable && (
                <span className="num ml-auto">{((h.value / total) * 100).toFixed(1)}%</span>
              )}
              {on && <X aria-hidden="true" className="h-3.5 w-3.5 flex-none text-fg-2" />}
            </div>
            <div className="mt-1 flex flex-wrap items-baseline justify-between gap-x-3">
              <Money value={h.value} className="text-[24px] font-medium tracking-[-0.02em]" />
              <span className="text-[12.5px]">
                <Money value={h.today} pnl /> today
                {h.value - h.today > 0 && (
                  <>
                    {' · '}
                    <Pct value={h.today / (h.value - h.today)} pnl />
                  </>
                )}
              </span>
            </div>
            <div className="mt-2 flex min-h-[22px] gap-1">
              {h.sleeves.length === 0 ? (
                <span className="text-[12px] text-fg-3">No sleeves on this account</span>
              ) : (
                h.sleeves.map((s) => (
                  <span
                    key={s.id}
                    title={`${s.name} ${formatMoney(s.value)}`}
                    className="min-w-0 truncate rounded-[4px] border border-line bg-sunk px-1.5 py-0.5 text-left text-[11.5px] text-fg-2"
                    style={{ flex: `${Math.max(1, s.value)} 1 0` }}
                  >
                    {s.name}
                  </span>
                ))
              )}
            </div>
          </>
        );
        const cls = `min-w-0 rounded-[10px] bg-panel px-4 py-3 text-left transition-opacity ${frame} ${
          dim ? 'opacity-45' : ''
        } ${on ? 'shadow-[0_0_0_3px_var(--accent-soft)]' : ''}`;
        return choosable ? (
          <button
            key={h.kind}
            type="button"
            aria-pressed={on}
            onClick={() => onScope(on ? 'all' : h.kind)}
            className={`${cls} hover:border-accent`}
            style={{ flex: `${widths[i]} 1 0` }}
          >
            {body}
          </button>
        ) : (
          <div key={h.kind} className={cls} style={{ flex: '1 1 0' }}>
            {body}
          </div>
        );
      })}
    </div>
  );
}
