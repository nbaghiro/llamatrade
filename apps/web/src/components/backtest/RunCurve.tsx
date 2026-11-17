import { useMemo } from 'react';

import { drawdownOf, longDate, type TradeInput } from '../../lib/backtestView';
import { yDomain } from '../../lib/chart/scale';
import { timeFraction, timePath } from '../../lib/chart/timeScale';
import { formatMoney, formatNumber, formatPct } from '../../lib/format';
import {
  AnnotatedCurve,
  LaneLegend,
  type CurveBand,
  type CurveLane,
  type CurvePin,
  type LegendItem,
} from '../charts';

import {
  foldLanes,
  holdingLanes,
  rebalanceMarks,
  stretchLabel,
  thinMarks,
  toLog,
  worstStretch,
  type WorstStretch,
} from './annotations';

const LABEL_W = 112;
const CURVE_H = 236;
const DD_H = 64;
const MAX_LANES = 6;
/** Marks closer than this share one, so the lane stays readable. */
const MAX_MARKS = 72;

interface RunCurveProps {
  strategyName: string;
  benchmark: string;
  dates: readonly Date[];
  values: readonly number[];
  benchValues: readonly number[] | null;
  /** The run's trades: null while they load, undefined where the page doesn't fetch them. */
  trades?: readonly TradeInput[] | null;
  log?: boolean;
  /** A stretch to shade, such as the month picked below the chart. */
  highlight?: { from: Date; to: Date } | null;
}

/**
 * The finished run's curve against the benchmark with what it did on the same dates: the worst
 * fall shaded, a lane per symbol for when it was held and a mark for every day it traded.
 */
export function RunCurve({
  strategyName,
  benchmark,
  dates,
  values,
  benchValues,
  trades,
  log = false,
  highlight = null,
}: RunCurveProps) {
  const start = dates[0];
  const end = dates[dates.length - 1];
  const worst = useMemo(() => worstStretch(dates, values), [dates, values]);
  const drawdown = useMemo(() => drawdownOf(values), [values]);

  const { lanes, dense, switches, markCount } = useMemo(() => {
    if (!trades) return { lanes: [], dense: false, switches: 0, markCount: 0 };
    const marks = rebalanceMarks(trades).filter(
      (m) => m.at.getTime() >= start.getTime() && m.at.getTime() <= end.getTime()
    );
    const thin = thinMarks(marks, start, end, MAX_MARKS);
    const shown = thin.marks;
    const holding: CurveLane[] = foldLanes(holdingLanes(trades, start, end), MAX_LANES).map(
      (l) => ({
        id: `held-${l.symbol}`,
        label: <span className="font-mono">{l.symbol}</span>,
        spans: l.spans.map((s) => ({ from: s.from, to: s.to, style: 'bar' as const })),
      })
    );
    const rebalance: CurveLane = {
      id: 'rebalances',
      label: <span className="font-normal text-fg-2">Trading days</span>,
      spans: [],
      events: shown.map((m) => ({
        at: m.at,
        shape: m.switched ? ('dot' as const) : ('ring' as const),
        title: `${thin.thinned ? 'From ' : ''}${longDate(m.at)}: ${m.orders} ${m.orders === 1 ? 'order' : 'orders'}${m.switched ? ', switched symbols' : ''}`,
      })),
    };
    return {
      lanes: marks.length ? [...holding, rebalance] : holding,
      dense: thin.thinned,
      switches: marks.filter((m) => m.switched).length,
      markCount: marks.length,
    };
  }, [trades, start, end]);

  const shown = log ? toLog(values) : values;
  const shownBench = benchValues ? (log ? toLog(benchValues) : benchValues) : undefined;

  const bands: CurveBand[] = [
    ...(worst
      ? [{ from: worst.peak, to: worst.recovered ?? end, tone: 'loss' as const, through: true }]
      : []),
    ...(highlight ? [{ ...highlight, tone: 'accent' as const, through: true }] : []),
  ];
  const pins: CurvePin[] = worst
    ? [{ at: worst.trough, label: stretchLabel(worst), tone: 'loss', guide: false }]
    : [];

  const peak = Math.max(...values);
  const legend: LegendItem[] = [
    ...(markCount ? [{ shape: 'ring' as const, label: 'Orders, same symbols' }] : []),
    ...(switches
      ? [
          {
            shape: 'dot' as const,
            label: `Switched symbols (${formatNumber(switches, { dp: 0 })} days)`,
          },
        ]
      : []),
  ];

  return (
    <div>
      <AnnotatedCurve
        label={`${strategyName} equity${shownBench ? ` against ${benchmark}` : ''}${log ? ', log scale' : ''}`}
        dates={dates}
        values={shown}
        benchmark={shownBench}
        height={CURVE_H}
        labelWidth={LABEL_W}
        bands={bands}
        pins={pins}
        lanes={lanes}
        side={
          <dl className="m-0 grid gap-2.5 pt-1">
            {[
              ['Ended', formatMoney(values[values.length - 1], { dp: 0 })],
              ['Peak', formatMoney(peak, { dp: 0 })],
              ...(log ? [['Scale', 'Log']] : []),
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-[11px] text-fg-3">{k}</dt>
                <dd className="m-0 font-mono text-[13px] tabular-nums text-fg">{v}</dd>
              </div>
            ))}
          </dl>
        }
        tooltip={(i) => (
          <>
            <b className="block font-medium text-fg-3">{dates[i]?.toISOString().slice(0, 10)}</b>
            {strategyName} {formatMoney(values[i])}
            {benchValues && (
              <span className="block text-fg-2">
                {benchmark} {formatMoney(benchValues[i])}
              </span>
            )}
          </>
        )}
      />
      <DrawdownStrip dates={dates} drawdown={drawdown} worst={worst} start={start} end={end} />
      <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 text-[11.5px] text-fg-3">
        {legend.length > 0 ? <LaneLegend items={legend} /> : <span />}
        {trades === undefined ? null : trades === null ? (
          <span>Loading the trades for the holding lanes…</span>
        ) : markCount > 0 ? (
          <span>
            Holdings are rebuilt from the trade list
            {dense
              ? `. ${formatNumber(markCount, { dp: 0 })} trading days had orders; marks that would overlap are combined.`
              : '.'}
          </span>
        ) : (
          <span>This run placed no orders.</span>
        )}
      </div>
    </div>
  );
}

/** Drawdown from the running peak on the same time axis as the curve above it. */
function DrawdownStrip({
  dates,
  drawdown,
  worst,
  start,
  end,
}: {
  dates: readonly Date[];
  drawdown: readonly number[];
  worst: WorstStretch | null;
  start: Date;
  end: Date;
}) {
  const d = { lo: yDomain([drawdown], { ceil: 0 }).lo, hi: 0 };
  const line = d.lo < 0 ? timePath(dates, drawdown, start, end, d, 1000, DD_H) : '';
  const area = line ? `M0,0 L${line.slice(1)} L1000,0 Z` : '';
  return (
    <div className="mt-1 grid" style={{ gridTemplateColumns: `${LABEL_W}px minmax(0,1fr)` }}>
      <div className="hidden pr-3.5 sm:block">
        <div className="text-[11px] font-medium text-fg-3">Drawdown from peak</div>
        {worst && (
          <div className="mt-0.5 font-mono text-[12px] text-loss">
            {formatPct(worst.depth, { dp: 1 })}
          </div>
        )}
      </div>
      <div className="relative col-span-2 border-t border-line sm:col-span-1">
        <div className="text-[11px] font-medium text-fg-3 sm:hidden">Drawdown from peak</div>
        {worst && (
          <i
            aria-hidden="true"
            className="absolute inset-y-0 bg-loss/10"
            style={{
              left: `${(timeFraction(worst.peak, start, end) * 100).toFixed(3)}%`,
              width: `${((timeFraction(worst.recovered ?? end, start, end) - timeFraction(worst.peak, start, end)) * 100).toFixed(3)}%`,
            }}
          />
        )}
        <svg
          role="img"
          aria-label={`Drawdown from peak${worst ? `, deepest ${formatPct(worst.depth, { dp: 1 })}` : ''}`}
          viewBox={`0 0 1000 ${DD_H}`}
          preserveAspectRatio="none"
          width="100%"
          height={DD_H}
          className="relative block"
        >
          {area && <path d={area} fill="rgb(var(--loss))" fillOpacity={0.14} />}
          {line && (
            <path
              d={line}
              fill="none"
              stroke="rgb(var(--loss))"
              strokeWidth={1.2}
              vectorEffect="non-scaling-stroke"
            />
          )}
        </svg>
      </div>
    </div>
  );
}
