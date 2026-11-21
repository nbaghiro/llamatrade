import { useRef, useState, type PointerEvent, type ReactNode } from 'react';

import { pctAt, timeFraction } from '../../lib/chart/timeScale';
import { LaneLegend, LaneMarker, type MarkerShape, type MarkerTone } from '../charts';

export interface ActivityMark {
  key: string;
  at: Date;
  shape: MarkerShape;
  tone?: MarkerTone;
  count?: number;
  title: string;
}

export interface ActivityLane {
  id: string;
  label: ReactNode;
  badge?: ReactNode;
  marks: readonly ActivityMark[];
}

export interface DateRange {
  from: Date;
  to: Date;
}

interface ActivityLanesProps {
  lanes: readonly ActivityLane[];
  start: Date;
  end: Date;
  range: DateRange | null;
  onRange: (range: DateRange | null) => void;
  /** "Nov 12 to today · 6 entries", shown on the selection. */
  rangeLabel?: string;
}

const DAY = 86_400_000;
const MONTH_DAY = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' });

/** Mondays in the window, labelled "Mon 9", and the first day as "Nov 1". */
function weekTicks(start: Date, end: Date): { at: Date; label: string }[] {
  const out = [{ at: start, label: MONTH_DAY.format(start) }];
  const d = new Date(start);
  d.setHours(0, 0, 0, 0);
  while (d <= end) {
    if (d.getDay() === 1 && d.getTime() - start.getTime() > 2 * DAY) {
      out.push({ at: new Date(d), label: `Mon ${d.getDate()}` });
    }
    d.setDate(d.getDate() + 1);
  }
  return out;
}

const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const endOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999);

/**
 * A lane per sleeve over a month with its fills and money movements, and a range you drag
 * across the lanes to filter the statement below (activity2 A).
 */
export function ActivityLanes({
  lanes,
  start,
  end,
  range,
  onRange,
  rangeLabel,
}: ActivityLanesProps) {
  const track = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<{ a: Date; b: Date } | null>(null);

  const dateAt = (clientX: number): Date => {
    const box = track.current?.getBoundingClientRect();
    if (!box || box.width <= 0) return start;
    const f = Math.min(1, Math.max(0, (clientX - box.left) / box.width));
    return new Date(start.getTime() + f * (end.getTime() - start.getTime()));
  };

  const onDown = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const at = dateAt(e.clientX);
    setDrag({ a: at, b: at });
  };
  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    if (drag) setDrag({ a: drag.a, b: dateAt(e.clientX) });
  };
  const onUp = () => {
    if (!drag) return;
    const [lo, hi] = drag.a <= drag.b ? [drag.a, drag.b] : [drag.b, drag.a];
    setDrag(null);
    if (hi.getTime() - lo.getTime() < DAY / 4) {
      onRange(null);
      return;
    }
    onRange({ from: startOfDay(lo), to: endOfDay(hi) });
  };

  const shown = drag
    ? drag.a <= drag.b
      ? { from: drag.a, to: drag.b }
      : { from: drag.b, to: drag.a }
    : range;
  const ticks = weekTicks(start, end);

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-y-1 md:grid-cols-[236px_minmax(0,1fr)]">
      <LaneLegend
        className="mb-1 md:col-span-2"
        items={[
          { shape: 'dot', label: 'Fills', count: 2 },
          { shape: 'diamondFilled', label: 'In' },
          { shape: 'diamond', label: 'Out' },
        ]}
      />
      <div className="hidden md:grid" style={{ gridTemplateRows: `repeat(${lanes.length}, 26px)` }}>
        {lanes.map((l) => (
          <div
            key={l.id}
            className="flex min-w-0 items-center gap-1.5 pr-3 text-[12.5px] font-medium"
          >
            <span className="min-w-0 truncate">{l.label}</span>
            {l.badge}
          </div>
        ))}
      </div>
      <div>
        <div
          ref={track}
          role="group"
          aria-label="Drag across the lanes to choose a range of dates"
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={onUp}
          onPointerCancel={() => setDrag(null)}
          className="relative cursor-crosshair touch-pan-y select-none"
          style={{ height: lanes.length * 26 }}
        >
          {shown && (
            <div
              className="pointer-events-none absolute -bottom-1 -top-1 border-x border-accent bg-accent/10"
              style={{
                left: pctAt(shown.from, start, end),
                width: `${(timeFraction(shown.to, start, end) - timeFraction(shown.from, start, end)) * 100}%`,
              }}
            >
              {rangeLabel && !drag && (
                <span className="absolute -top-5 left-1 whitespace-nowrap rounded-full border border-accent/45 bg-panel px-2 font-mono text-[10.5px] text-fg-2">
                  {rangeLabel}
                </span>
              )}
            </div>
          )}
          {lanes.map((l, i) => (
            <div key={l.id} className="absolute inset-x-0" style={{ top: i * 26, height: 26 }}>
              <span className="pointer-events-none absolute left-0 top-0 text-[10.5px] text-fg-3 md:hidden">
                {l.label}
              </span>
              <i className="absolute inset-x-0 top-[13px] h-px bg-line-strong" />
              {l.marks.map((m) => (
                <span
                  key={m.key}
                  className="absolute top-[13px]"
                  style={{ left: pctAt(m.at, start, end) }}
                >
                  <LaneMarker
                    shape={m.shape}
                    tone={m.tone}
                    count={m.count}
                    title={m.title}
                    positioned
                  />
                </span>
              ))}
            </div>
          ))}
        </div>
        <div className="relative mt-1 h-4 font-mono text-[10.5px] text-fg-3">
          {ticks.map((t) => (
            <span
              key={t.at.getTime()}
              className="absolute whitespace-nowrap"
              style={{ left: pctAt(t.at, start, end) }}
            >
              {t.label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
