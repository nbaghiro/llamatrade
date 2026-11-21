import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { monthKey, type TradeInput } from '../../lib/backtestView';
import { yDomain } from '../../lib/chart/scale';
import { timeFraction, timePath } from '../../lib/chart/timeScale';
import { formatNumber, formatPct } from '../../lib/format';
import type { CodeLine } from '../../lib/strategyDiff';
import { AnnotatedCurve, type CurveLane } from '../charts';
import { SkeletonChart } from '../ui/Skeleton';
import { StatList } from '../ui/StatList';

import {
  differingStretches,
  heldStretches,
  heldSymbolsOn,
  holdingLanes,
  mostlyHeld,
  type DiffStretch,
  type HoldingLane,
} from './annotations';
import { endGap, monthsHeldDifferently, stretchMonths, symbolList } from './compareView';
import { Panel } from './parts';

/** Stretches shorter than this are fill timing, not a different choice. */
const MIN_DAYS = 3;
const MAX_STRETCHES = 8;
const LABEL_W = 210;
const RATIO_H = 44;
export const SECOND_RUN_COLOR = 'rgb(var(--fg-2))';

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

export interface CompareRunRef {
  id: string;
  /** "v3", or the full name when the runs are of different strategies. */
  label: string;
}

/**
 * Two runs over their shared dates as one stack: both curves and the benchmark, what each held
 * with the differing stretches outlined and numbered, and the value of the first over the second
 * (compare2 A). Below it, what changed in the code and the picked stretch.
 */
export function CompareHeld({
  dates,
  a,
  b,
  bench,
  benchLabel,
  runA,
  runB,
  aTrades,
  bTrades,
  changes,
}: {
  dates: readonly Date[];
  /** Both rebased to the same start. */
  a: readonly number[];
  b: readonly number[];
  bench: readonly number[] | null;
  benchLabel: string | null;
  runA: CompareRunRef;
  runB: CompareRunRef;
  /** Null while loading; an empty list when a run placed no orders. */
  aTrades: readonly TradeInput[] | null;
  bTrades: readonly TradeInput[] | null;
  /** Changed code lines from the second run's version to the first's; undefined while loading, null when unavailable. */
  changes?: CodeLine[] | null;
}) {
  const start = dates[0];
  const end = dates[dates.length - 1];
  const ratio = useMemo(() => a.map((v, i) => v / b[i] - 1), [a, b]);
  const [picked, setPicked] = useState(0);
  const aLabel = runA.label;
  const bLabel = runB.label;

  const model = useMemo(() => {
    if (!aTrades || !bTrades) return null;
    const aLanes = holdingLanes(aTrades, start, end);
    const bLanes = holdingLanes(bTrades, start, end);
    const stretches = differingStretches(dates, a, b, aLanes, bLanes)
      .filter((s) => s.days >= MIN_DAYS)
      .sort((x, y) => Math.abs(y.gained) - Math.abs(x.gained))
      .slice(0, MAX_STRETCHES)
      .sort((x, y) => x.from.getTime() - y.from.getTime());
    return {
      aLanes,
      bLanes,
      stretches,
      months: monthsHeldDifferently(dates, aLanes, bLanes),
    };
  }, [aTrades, bTrades, dates, a, b, start, end]);

  const others = useMemo(() => [{ values: b, color: SECOND_RUN_COLOR }], [b]);

  if (!model) {
    return (
      <Panel>
        <div className="p-3.5" aria-busy="true">
          <SkeletonChart height={300} />
          <p className="m-0 mt-2 text-[12px] text-fg-3">Loading the trades of both runs…</p>
        </div>
      </Panel>
    );
  }

  const last = ratio[ratio.length - 1];
  const widest = Math.max(...ratio);
  const lowest = Math.min(...ratio);
  const lanes = [
    heldLane('a', `${aLabel} held`, model.aLanes, dates),
    heldLane('b', `${bLabel} held`, model.bLanes, dates),
  ];
  const gap = endGap(last);
  const stretch = model.stretches[Math.min(picked, model.stretches.length - 1)] ?? null;

  return (
    <>
      <Panel
        footer={
          <>
            Holdings are rebuilt from each run&apos;s trade list. Outlined: the two runs held
            different symbols. Bottom: the value of {aLabel} over {bLabel}
            {gap.tone ? `, ending ${gap.text}.` : ', ending level.'}
          </>
        }
      >
        <div className="px-3.5 pb-2 pt-3">
          <Legend aLabel={aLabel} bLabel={bLabel} benchLabel={bench ? benchLabel : null} />
          <AnnotatedCurve
            label={`${aLabel} and ${bLabel}${bench && benchLabel ? ` against ${benchLabel}` : ''}, growth from the shared start`}
            dates={dates}
            values={a}
            others={others}
            benchmark={bench ?? undefined}
            height={220}
            labelWidth={LABEL_W}
            lanes={lanes}
            bands={model.stretches.map((s) => ({
              from: s.from,
              to: s.to,
              tone: 'accent' as const,
              through: true,
            }))}
            pins={model.stretches.map((s, i) => ({
              at: new Date((s.from.getTime() + s.to.getTime()) / 2),
              label: i === 0 ? 'Held different · 1' : String(i + 1),
              tone: i === picked ? ('accent' as const) : ('neutral' as const),
              guide: false,
            }))}
            side={
              <StatList
                items={[
                  {
                    label: `${aLabel} at the end`,
                    value: gap.tone ? gap.text : 'level',
                    tone: gap.tone,
                  },
                  { label: 'Widest lead', value: widest >= 0.0005 ? signed(widest) : 'never' },
                  {
                    label: `${aLabel} behind by most`,
                    value: lowest <= -0.0005 ? signed(lowest) : 'never',
                  },
                  {
                    label: 'Months differing',
                    value: `${formatNumber(model.months.differing, { dp: 0 })} of ${formatNumber(model.months.total, { dp: 0 })}`,
                  },
                ]}
              />
            }
            tooltip={(i) => (
              <>
                <b className="block font-medium text-fg-3">
                  {dates[i]?.toISOString().slice(0, 10)}
                </b>
                {aLabel} {signed(a[i] - 1)} · {bLabel} {signed(b[i] - 1)}
                <span className="block text-fg-2">
                  {heldSymbolsOn(model.aLanes, dates[i]).join(' ') || 'no positions'} ·{' '}
                  {heldSymbolsOn(model.bLanes, dates[i]).join(' ') || 'no positions'}
                </span>
              </>
            )}
          />
          <RatioStrip
            dates={dates}
            ratio={ratio}
            stretches={model.stretches}
            aLabel={aLabel}
            bLabel={bLabel}
          />
        </div>
      </Panel>

      <div className="grid gap-3.5 lg:grid-cols-2">
        <Panel title="What changed" aside={`${bLabel} → ${aLabel}`}>
          <CodeChanges changes={changes} />
        </Panel>
        <Panel
          title={
            stretch
              ? `Stretch ${model.stretches.indexOf(stretch) + 1} · ${stretchMonths(stretch.from, stretch.to)}`
              : 'Where they differed'
          }
          aside={
            model.stretches.length > 1 ? (
              <span className="flex gap-1" role="group" aria-label="Pick a stretch">
                {model.stretches.map((s, i) => (
                  <button
                    key={s.from.getTime()}
                    type="button"
                    aria-pressed={i === picked}
                    onClick={() => setPicked(i)}
                    className={`grid h-5 min-w-5 place-items-center rounded-full border px-1 font-mono text-[10.5px] ${i === picked ? 'border-accent text-fg' : 'border-line-strong text-fg-3 hover:text-fg'}`}
                  >
                    {i + 1}
                  </button>
                ))}
              </span>
            ) : undefined
          }
        >
          <div className="grid gap-2.5 px-3.5 py-3 text-[12.5px] text-fg-2">
            {stretch ? (
              <StretchDetail
                stretch={stretch}
                dates={dates}
                aLanes={model.aLanes}
                bLanes={model.bLanes}
                runA={runA}
                runB={runB}
              />
            ) : (
              <p className="m-0">
                {aLabel} and {bLabel} held the same symbols on every shared day, so the gap between
                them comes from fills and sizing.
              </p>
            )}
          </div>
        </Panel>
      </div>
    </>
  );
}

function Legend({
  aLabel,
  bLabel,
  benchLabel,
}: {
  aLabel: string;
  bLabel: string;
  benchLabel: string | null;
}) {
  return (
    <div className="mb-1.5 flex flex-wrap gap-3.5 text-[11.5px] text-fg-2">
      <span className="inline-flex items-center gap-1.5">
        <i aria-hidden="true" className="w-3.5 border-t-[1.5px] border-accent" />
        {aLabel}
      </span>
      <span className="inline-flex items-center gap-1.5">
        <i
          aria-hidden="true"
          className="w-3.5 border-t-[1.5px]"
          style={{ borderColor: SECOND_RUN_COLOR }}
        />
        {bLabel}
      </span>
      {benchLabel && (
        <span className="inline-flex items-center gap-1.5">
          <i aria-hidden="true" className="w-3.5 border-t border-dashed border-fg-3" />
          {benchLabel}
        </span>
      )}
      <span className="inline-flex items-center gap-1.5">
        <i aria-hidden="true" className="h-2.5 w-3 rounded-[2px] bg-accent/15" />
        Held different symbols
      </span>
    </div>
  );
}

/** The value of the first run over the second, on the same time axis as the stack above. */
function RatioStrip({
  dates,
  ratio,
  stretches,
  aLabel,
  bLabel,
}: {
  dates: readonly Date[];
  ratio: readonly number[];
  stretches: readonly DiffStretch[];
  aLabel: string;
  bLabel: string;
}) {
  const start = dates[0];
  const end = dates[dates.length - 1];
  const d = yDomain([ratio, [-0.01, 0.01]]);
  const line = timePath(dates, ratio, start, end, d, 1000, RATIO_H);
  const zero = (1 - (0 - d.lo) / (d.hi - d.lo || 1)) * RATIO_H;
  const area = line ? `M0,${zero} L${line.slice(1)} L1000,${zero} Z` : '';
  return (
    <div className="mt-1 grid sm:grid-cols-[210px_minmax(0,1fr)]">
      <div className="pr-3.5">
        <div className="text-[12.5px] font-semibold text-fg">
          {aLabel} against {bLabel}
        </div>
        <div className="hidden text-[11px] text-fg-3 sm:block">
          Value of {aLabel} over {bLabel}
        </div>
      </div>
      <div className="relative border-t border-line">
        {stretches.map((s) => (
          <i
            key={s.from.getTime()}
            aria-hidden="true"
            className="absolute inset-y-0 bg-accent/10"
            style={{
              left: `${(timeFraction(s.from, start, end) * 100).toFixed(3)}%`,
              width: `${(Math.max(0.002, timeFraction(s.to, start, end) - timeFraction(s.from, start, end)) * 100).toFixed(3)}%`,
            }}
          />
        ))}
        <svg
          role="img"
          aria-label={`Value of ${aLabel} over ${bLabel}, ending ${signed(ratio[ratio.length - 1])}`}
          viewBox={`0 0 1000 ${RATIO_H}`}
          preserveAspectRatio="none"
          width="100%"
          height={RATIO_H}
          className="relative block"
        >
          {area && <path d={area} fill="rgb(var(--fg-3))" fillOpacity={0.18} />}
          {line && (
            <path
              d={line}
              fill="none"
              stroke="rgb(var(--fg-2))"
              strokeWidth={1.2}
              vectorEffect="non-scaling-stroke"
            />
          )}
        </svg>
      </div>
    </div>
  );
}

function CodeChanges({ changes }: { changes: CodeLine[] | null | undefined }) {
  if (changes === undefined) {
    return <p className="m-0 px-3.5 py-3 text-[12.5px] text-fg-3">Loading both versions…</p>;
  }
  if (changes === null) {
    return (
      <p className="m-0 px-3.5 py-3 text-[12.5px] text-fg-3">
        The code of one of these versions couldn&apos;t be loaded.
      </p>
    );
  }
  if (!changes.length) {
    return (
      <p className="m-0 px-3.5 py-3 text-[12.5px] text-fg-3">
        Both runs used the same code. The difference comes from their settings.
      </p>
    );
  }
  return (
    <div className="grid gap-0.5 px-3.5 py-3 font-mono text-[12px]">
      {changes.map((l, i) => (
        <div
          key={i}
          className={
            l.kind === 'del'
              ? 'truncate px-2 py-0.5 text-fg-3 line-through'
              : 'truncate border-l-2 border-accent bg-accent/5 px-2 py-0.5 text-fg'
          }
        >
          <span className="sr-only">{l.kind === 'del' ? 'Removed: ' : 'Added: '}</span>
          {l.text}
        </div>
      ))}
    </div>
  );
}

function StretchDetail({
  stretch,
  dates,
  aLanes,
  bLanes,
  runA,
  runB,
}: {
  stretch: DiffStretch;
  dates: readonly Date[];
  aLanes: readonly HoldingLane[];
  bLanes: readonly HoldingLane[];
  runA: CompareRunRef;
  runB: CompareRunRef;
}) {
  const aHeld = mostlyHeld(aLanes, dates, stretch.from, stretch.to);
  const bHeld = mostlyHeld(bLanes, dates, stretch.from, stretch.to);
  const month = monthKey(stretch.from);
  const held = (s: readonly string[]) =>
    s.length ? (
      <span className="font-mono font-semibold text-fg">{symbolList(s)}</span>
    ) : (
      'no one symbol for most of it'
    );
  return (
    <>
      <p className="m-0">
        {runA.label} held {held(aHeld)} while {runB.label} held {held(bHeld)}.{' '}
        {endGap(stretch.gained).tone ? (
          <>
            {runA.label} {stretch.gained >= 0 ? 'gained' : 'lost'}{' '}
            <span className={`font-mono ${stretch.gained >= 0 ? 'text-gain' : 'text-loss'}`}>
              {formatPct(Math.abs(stretch.gained), { dp: 1 })}
            </span>{' '}
            on {runB.label} over these {formatNumber(stretch.days, { dp: 0 })} trading days.
          </>
        ) : (
          <>
            The gap between them moved less than 0.1% over these{' '}
            {formatNumber(stretch.days, { dp: 0 })} trading days.
          </>
        )}
      </p>
      <p className="m-0 flex flex-wrap gap-x-3 gap-y-1">
        <span className="text-fg">See the orders in both runs:</span>
        <Link to={`/backtest/${runA.id}#month-${month}`} className="text-accent hover:underline">
          {runA.label}
        </Link>
        <Link to={`/backtest/${runB.id}#month-${month}`} className="text-accent hover:underline">
          {runB.label}
        </Link>
      </p>
    </>
  );
}
