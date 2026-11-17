import type { CSSProperties, ReactNode } from 'react';

import { monthTicks, tickLabel, timeFraction } from '../../lib/chart/timeScale';
import { LaneLegend, LaneMarker } from '../charts';

const LABEL_W = 112;
const FRAME_H = 196;
const LANE_H = 30;
/** Past this many, the rebalances read as a line rather than separate marks. */
const MAX_MARKS = 36;

const pos = (f: number): CSSProperties => ({ left: `${(f * 100).toFixed(3)}%` });

/**
 * The run's dates before the curve exists: how far the simulation got, the stretch still ahead,
 * and the scheduled rebalances it has passed. The progress stream carries the simulated date,
 * not equity points, so the frame holds the place the curve takes when the run completes.
 */
export function RunProgressFrame({
  start,
  end,
  through,
  tone = 'running',
  marker,
  rebalances = [],
  doneNote,
  aheadNote,
  side,
}: {
  start: Date;
  end: Date;
  /** The last simulated day; null before the first one. */
  through: Date | null;
  tone?: 'running' | 'stopped';
  /** The pill on the line at `through`, e.g. "Simulated to Apr 14, 2023". */
  marker?: string;
  /** Scheduled rebalance dates; those on or before `through` are drawn as passed. */
  rebalances?: readonly Date[];
  doneNote?: ReactNode;
  aheadNote?: ReactNode;
  side?: ReactNode;
}) {
  const span = Math.max(1, (end.getTime() - start.getTime()) / 86_400_000);
  const f = through ? timeFraction(through, start, end) : 0;
  const stopped = tone === 'stopped';
  const ticks = monthTicks(start, end, 6);
  const passed = rebalances.filter((d) => through && d.getTime() <= through.getTime()).length;

  return (
    <div>
      <div className="grid" style={{ gridTemplateColumns: `${LABEL_W}px minmax(0,1fr)` }}>
        <div className="hidden pr-3.5 sm:block" style={{ height: FRAME_H }}>
          {side}
        </div>
        <div
          className="relative col-span-2 border-b border-line sm:col-span-1"
          style={{ height: FRAME_H }}
        >
          {f > 0 && (
            <div
              className="absolute inset-y-0 left-0 grid place-items-center bg-accent/[0.05] px-3 text-center text-[12px] text-fg-3"
              style={{ width: `${(f * 100).toFixed(3)}%` }}
            >
              {f > 0.22 && doneNote}
            </div>
          )}
          <div
            className="absolute inset-y-0 right-0 flex items-center bg-sunk/70 px-4 text-[12px] text-fg-3"
            style={pos(f)}
          >
            {f < 0.78 && <span className="max-w-[340px]">{aheadNote}</span>}
          </div>
          {through && (
            <>
              <i
                aria-hidden="true"
                className={`absolute inset-y-0 border-l-[1.5px] ${stopped ? 'border-risk' : 'border-fg'}`}
                style={pos(f)}
              />
              {marker && (
                <span
                  className={`absolute top-2 z-[2] whitespace-nowrap rounded px-1.5 py-px font-mono text-[10.5px] font-semibold ${
                    stopped ? 'border border-risk-line bg-risk-soft text-risk' : 'bg-fg text-canvas'
                  }`}
                  style={{
                    ...pos(f),
                    transform: `translateX(${f > 0.85 ? '-100%' : f < 0.15 ? '0%' : '-50%'})`,
                  }}
                >
                  {marker}
                </span>
              )}
            </>
          )}
        </div>
      </div>
      {rebalances.length > 0 && (
        <div className="grid" style={{ gridTemplateColumns: `${LABEL_W}px minmax(0,1fr)` }}>
          <div className="hidden items-center text-[12px] text-fg-2 sm:flex">Rebalances</div>
          <div
            className="relative col-span-2 border-b border-line sm:col-span-1"
            style={{ height: LANE_H }}
            role="img"
            aria-label={`${passed} of ${rebalances.length} scheduled rebalances simulated`}
          >
            {rebalances.length <= MAX_MARKS ? (
              rebalances.map((d) => {
                const done = through !== null && d.getTime() <= through.getTime();
                return (
                  <LaneMarker
                    key={d.getTime()}
                    shape={done ? 'ring' : 'planned'}
                    tone={stopped ? 'muted' : 'accent'}
                    positioned
                    style={pos(timeFraction(d, start, end))}
                  />
                );
              })
            ) : (
              <>
                <i
                  aria-hidden="true"
                  className={`absolute left-0 top-1/2 border-t-2 ${stopped ? 'border-fg-3' : 'border-accent'}`}
                  style={{ width: `${(f * 100).toFixed(3)}%` }}
                />
                <i
                  aria-hidden="true"
                  className="absolute right-0 top-1/2 border-t-2 border-dashed border-fg-3/50"
                  style={pos(f)}
                />
              </>
            )}
          </div>
        </div>
      )}
      <div className="grid" style={{ gridTemplateColumns: `${LABEL_W}px minmax(0,1fr)` }}>
        <div className="hidden sm:block" />
        <div className="relative col-span-2 h-6 sm:col-span-1">
          {ticks.map((t) => {
            const x = timeFraction(t, start, end);
            return (
              <span
                key={t.getTime()}
                className="absolute top-[5px] whitespace-nowrap px-1 font-mono text-[10.5px] text-fg-3"
                style={{
                  ...pos(x),
                  transform: `translateX(${x < 0.04 ? '0%' : x > 0.96 ? '-100%' : '-50%'})`,
                }}
              >
                {tickLabel(t, span)}
              </span>
            );
          })}
        </div>
      </div>
      {rebalances.length > 0 && (
        <LaneLegend
          className="mt-1"
          items={[
            { shape: 'ring', label: `Simulated, ${passed}`, tone: stopped ? 'muted' : 'accent' },
            { shape: 'planned', label: `Still ahead, ${rebalances.length - passed}` },
          ]}
        />
      )}
    </div>
  );
}
