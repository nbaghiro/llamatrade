import { useMemo } from 'react';

import { longDate, type TradeInput } from '../../lib/backtestView';
import { formatNumber, formatPct } from '../../lib/format';
import { AnnotatedCurve, type CurveLane } from '../charts';
import { SkeletonChart } from '../ui/Skeleton';
import { StatList } from '../ui/StatList';

import {
  differingStretches,
  heldStretches,
  heldSymbolsOn,
  holdingLanes,
  mostlyHeld,
  type HoldingLane,
} from './annotations';

/** Stretches shorter than this are fill timing, not a different choice. */
const MIN_DAYS = 3;
const MAX_STRETCHES = 8;

const signed = (v: number) => formatPct(v, { dp: 1, signed: true });

function heldLane(
  id: string,
  label: string,
  lanes: readonly HoldingLane[],
  dates: readonly Date[]
) {
  const span = Math.max(1, dates[dates.length - 1].getTime() - dates[0].getTime());
  const lane: CurveLane = {
    id,
    label,
    spans: heldStretches(lanes, dates)
      .filter((s) => s.symbols.length)
      .map((s) => ({
        from: s.from,
        to: s.to,
        style: 'bar' as const,
        label: (s.to.getTime() - s.from.getTime()) / span > 0.06 ? s.symbols.join(' ') : undefined,
      })),
  };
  return lane;
}

/**
 * What two runs held over their shared dates, with the stretches where they differed outlined
 * and the value of the first over the second drawn under them (compare2 A).
 */
export function CompareHeld({
  dates,
  a,
  b,
  aLabel,
  bLabel,
  aTrades,
  bTrades,
}: {
  dates: readonly Date[];
  /** Both rebased to the same start. */
  a: readonly number[];
  b: readonly number[];
  aLabel: string;
  bLabel: string;
  /** Null while loading; an empty list when a run placed no orders. */
  aTrades: readonly TradeInput[] | null;
  bTrades: readonly TradeInput[] | null;
}) {
  const start = dates[0];
  const end = dates[dates.length - 1];
  const ratio = useMemo(() => a.map((v, i) => v / b[i] - 1), [a, b]);

  const model = useMemo(() => {
    if (!aTrades || !bTrades) return null;
    const aLanes = holdingLanes(aTrades, start, end);
    const bLanes = holdingLanes(bTrades, start, end);
    const all = differingStretches(dates, a, b, aLanes, bLanes);
    const stretches = all
      .filter((s) => s.days >= MIN_DAYS)
      .sort((x, y) => Math.abs(y.gained) - Math.abs(x.gained))
      .slice(0, MAX_STRETCHES)
      .sort((x, y) => x.from.getTime() - y.from.getTime());
    return {
      aLanes,
      bLanes,
      stretches,
      differingDays: all.reduce((s, x) => s + x.days, 0),
    };
  }, [aTrades, bTrades, dates, a, b, start, end]);

  if (!model) {
    return (
      <div aria-busy="true">
        <SkeletonChart height={180} />
        <p className="m-0 mt-2 text-[12px] text-fg-3">Loading the trades of both runs…</p>
      </div>
    );
  }

  const widest = Math.max(...ratio);
  const lowest = Math.min(...ratio);
  const lanes = [
    heldLane('a', `${aLabel} held`, model.aLanes, dates),
    heldLane('b', `${bLabel} held`, model.bLanes, dates),
  ];

  return (
    <div className="grid gap-3.5">
      <AnnotatedCurve
        label={`Value of ${aLabel} over ${bLabel}`}
        dates={dates}
        values={ratio}
        height={120}
        labelWidth={170}
        lanes={lanes}
        bands={model.stretches.map((s) => ({
          from: s.from,
          to: s.to,
          tone: 'accent' as const,
          through: true,
        }))}
        pins={model.stretches.map((s, i) => ({
          at: new Date((s.from.getTime() + s.to.getTime()) / 2),
          label: i === 0 ? `Held different · 1` : String(i + 1),
          guide: false,
        }))}
        side={
          <StatList
            items={[
              {
                label: 'Ahead at end',
                value: signed(ratio[ratio.length - 1]),
                tone: ratio[ratio.length - 1] >= 0 ? 'gain' : 'loss',
              },
              { label: 'Widest lead', value: widest > 0 ? signed(widest) : 'never' },
              { label: 'Behind by most', value: lowest < 0 ? signed(lowest) : 'never' },
            ]}
          />
        }
        tooltip={(i) => (
          <>
            <b className="block font-medium text-fg-3">{dates[i]?.toISOString().slice(0, 10)}</b>
            {aLabel} {signed(ratio[i])} against {bLabel}
            <span className="block text-fg-2">
              {heldSymbolsOn(model.aLanes, dates[i]).join(' ') || 'no positions'} ·{' '}
              {heldSymbolsOn(model.bLanes, dates[i]).join(' ') || 'no positions'}
            </span>
          </>
        )}
      />
      <p className="m-0 text-[12px] text-fg-3">
        The line is the value of {aLabel} over {bLabel}. Holdings are rebuilt from each run&apos;s
        trade list. They held different symbols on {formatNumber(model.differingDays, { dp: 0 })} of{' '}
        {formatNumber(dates.length, { dp: 0 })} trading days.
      </p>
      {model.stretches.length > 0 && (
        <ol className="m-0 grid list-none gap-0 p-0 text-[12.5px]">
          {model.stretches.map((s, i) => {
            const aHeld = mostlyHeld(model.aLanes, dates, s.from, s.to).join(' ');
            const bHeld = mostlyHeld(model.bLanes, dates, s.from, s.to).join(' ');
            return (
              <li
                key={s.from.getTime()}
                className="grid grid-cols-[28px_minmax(0,1fr)_auto] gap-2 border-t border-line py-2"
              >
                <span className="font-mono text-fg-3">{i + 1}</span>
                <span className="min-w-0 text-fg-2">
                  <span className="text-fg">
                    {longDate(s.from)} to {longDate(s.to)}
                  </span>
                  : {aLabel} mostly held{' '}
                  {aHeld ? <span className="font-mono">{aHeld}</span> : 'no positions'} while{' '}
                  {bLabel} held{' '}
                  {bHeld ? <span className="font-mono">{bHeld}</span> : 'no positions'}.
                </span>
                <span className={`font-mono ${s.gained >= 0 ? 'text-gain' : 'text-loss'}`}>
                  {signed(s.gained)}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
