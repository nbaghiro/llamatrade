import { allocationSegments } from '../../lib/portfolioView';
import { Pct } from '../ui';

import { sleeveColor } from './sleeveView';

export interface AllocationSleeve {
  id: string;
  label: string;
  value: number;
  frozen: boolean;
}

interface AllocationBarProps {
  sleeves: readonly AllocationSleeve[];
  unallocated: number;
  height?: number;
  legend?: boolean;
}

/** The account in one bar: each sleeve in its tone, then unallocated cash hatched. */
export function AllocationBar({
  sleeves,
  unallocated,
  height = 14,
  legend = true,
}: AllocationBarProps) {
  const seg = allocationSegments(sleeves, unallocated);
  const label = [
    ...sleeves.map((s, i) => `${s.label} ${(seg.sleeves[i].share * 100).toFixed(1)}%`),
    `Unallocated ${(seg.unallocated.share * 100).toFixed(1)}%`,
  ].join(', ');

  return (
    <div>
      <div
        role="img"
        aria-label={`Allocation: ${label}`}
        className="flex gap-0.5 overflow-hidden rounded-[4px]"
        style={{ height }}
      >
        {sleeves.map((s, i) =>
          seg.sleeves[i].value > 0 ? (
            <i
              key={s.id}
              className={`block h-full ${s.frozen ? 'shadow-[inset_0_0_0_2px_rgb(var(--risk))]' : ''}`}
              style={{ flex: `${seg.sleeves[i].value} 1 0`, background: sleeveColor(i) }}
            />
          ) : null
        )}
        {seg.unallocated.value > 0 && (
          <i
            className="block h-full rounded-[2px] border border-dashed border-line-strong bg-hatch"
            style={{ flex: `${seg.unallocated.value} 1 0` }}
          />
        )}
        {seg.unallocated.value <= 0 && seg.sleeves.every((s) => s.value <= 0) && (
          <i className="block h-full flex-1 bg-sunk" />
        )}
      </div>
      {legend && (
        <div className="mt-2.5 flex flex-wrap gap-x-[18px] gap-y-1.5 text-[12.5px] text-fg-2">
          {sleeves.map((s, i) => (
            <span key={s.id} className="inline-flex items-center">
              <span
                aria-hidden="true"
                className="mr-2 inline-block h-[9px] w-[9px] rounded-[2px]"
                style={{ background: sleeveColor(i) }}
              />
              {s.label}
              <Pct value={seg.sleeves[i].share} dp={1} className="ml-1.5 text-fg-3" />
              {s.frozen && <span className="ml-1.5 text-risk">Frozen</span>}
            </span>
          ))}
          <span className="inline-flex items-center">
            <span
              aria-hidden="true"
              className="mr-2 inline-block h-[9px] w-[9px] rounded-[2px] border border-dashed border-line-strong"
            />
            Unallocated
            <Pct value={seg.unallocated.share} dp={1} className="ml-1.5 text-fg-3" />
          </span>
        </div>
      )}
    </div>
  );
}
