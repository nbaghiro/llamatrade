import { useId, useMemo, useState, type CSSProperties, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { yDomain } from '../../lib/chart/scale';
import {
  monthTicks,
  nearestDateIndex,
  pinAlign,
  timeArea,
  timeFraction,
  timePath,
  tickLabel,
} from '../../lib/chart/timeScale';

import {
  LaneLegend,
  LaneMarker,
  type LegendItem,
  type MarkerShape,
  type MarkerTone,
} from './LaneMarker';
import { useWidth } from './useWidth';

/** A label above the curve on a date, with a dashed guide down through the curve. */
export interface CurvePin {
  at: Date;
  label: ReactNode;
  /** accent for today's news, loss for a drawdown; neutral otherwise. */
  tone?: 'neutral' | 'accent' | 'loss';
  /** A number in a dot before the label, e.g. "3 Fills today". */
  count?: number;
  /** 0 is the top line, 1 the line under it, for pins that would collide. */
  row?: 0 | 1;
  /** Draw the dashed guide; on by default. */
  guide?: boolean;
}

/** A shaded stretch of time: held periods, a worst drawdown. */
export interface CurveBand {
  from: Date;
  to: Date;
  tone?: 'held' | 'loss' | 'accent';
  /** Extend the shade down through the lanes as well as the curve. */
  through?: boolean;
}

/** One mark on a lane. */
export interface LaneEvent {
  at: Date;
  shape: MarkerShape;
  tone?: MarkerTone;
  count?: number;
  /** Shown on hover and read by screen readers. */
  title?: string;
  /** A short note to the right of the mark, e.g. "+$3,000" or "v3 saved Nov 3". */
  text?: ReactNode;
}

/** A stretch of a lane: the line a session ran on, or a labelled bar. */
export interface LaneSpan {
  from: Date;
  /** Defaults to the end of the past. */
  to?: Date;
  /** on: running; off: stopped or idle; plan: scheduled; bar: a held period, labelled or not. */
  style?: 'on' | 'off' | 'plan' | 'bar';
  tone?: 'accent' | 'risk' | 'muted';
  label?: ReactNode;
}

/** What a lane shows in the future column. */
export interface LaneFuture {
  /** Marks between Now and `future.end`, usually planned rebalances. */
  events?: readonly LaneEvent[];
  /** A dashed line through the future; drawn by default when there are events. */
  line?: boolean;
  /** Text in place of marks, e.g. "Stopped, holding cash". */
  note?: ReactNode;
}

/** One row under the curve: a session, a version, a holding. */
export interface CurveLane {
  id: string;
  label: ReactNode;
  /** A second line under the label, e.g. "205 shares · 58.2%". */
  sub?: ReactNode;
  /** A Live or Paper badge beside the label. */
  badge?: ReactNode;
  /** A figure at the right of the label column. */
  value?: ReactNode;
  /** risk paints the label and line amber; muted greys a stopped lane. */
  tone?: 'default' | 'muted' | 'risk';
  href?: string;
  /** Defaults to one running line across the whole window. */
  spans?: readonly LaneSpan[];
  events?: readonly LaneEvent[];
  future?: LaneFuture;
}

export interface CurveFuture {
  /** The last day the future column covers. */
  end: Date;
  /** The heading in the column, e.g. "Next two weeks". */
  title?: ReactNode;
  /** Rows under the heading, e.g. what is scheduled. */
  content?: ReactNode;
  ticks?: readonly Date[];
}

export interface CurveNow {
  /** "Now 10:42" or "Last update 10:38". */
  label: string;
  /** The figures stopped updating: the marker turns hollow and the line dashed. */
  stale?: boolean;
}

export interface AnnotatedCurveProps {
  /** Read by screen readers, e.g. "Account equity, last three months". */
  label: string;
  /** One date per value. */
  dates: readonly Date[];
  values: readonly number[];
  /** A recessive dashed line on the same dates, such as SPY scaled to the same start. */
  benchmark?: readonly number[];
  /** The window shown; defaults to the first and last date. */
  start?: Date;
  /** The end of the past, where Now sits when there is a future column. */
  end?: Date;
  now?: CurveNow;
  /** A fixed-width column after Now for what is scheduled. */
  future?: CurveFuture;
  pins?: readonly CurvePin[];
  bands?: readonly CurveBand[];
  lanes?: readonly CurveLane[];
  /** Figures beside the curve in the label column, usually a `StatList`. */
  side?: ReactNode;
  legend?: readonly LegendItem[];
  /** Height of the curve itself, without pins, lanes or axis. */
  height?: number;
  labelWidth?: number;
  futureWidth?: number;
  ticks?: readonly Date[];
  tickFormat?: (d: Date) => string;
  /** The hover readout for a data index. */
  tooltip?: (index: number) => ReactNode;
  /** Shade the area under the main line; on by default. */
  area?: boolean;
  className?: string;
}

const PIN_ROW = 19;
const LANE = 27;
const LANE_SUB = 36;
const LANE_COMPACT = 38;
const AXIS = 24;
const COMPACT_BELOW = 640;
const VIEW_W = 1000;

const PIN_TONE: Record<NonNullable<CurvePin['tone']>, string> = {
  neutral: 'border-line-strong bg-panel text-fg-2',
  accent: 'border-accent/45 bg-accent-soft text-fg',
  loss: 'border-loss/40 bg-loss/10 text-loss',
};

const BAND_TONE: Record<NonNullable<CurveBand['tone']>, string> = {
  held: 'bg-fg-3/10',
  loss: 'bg-loss/10 border-x border-loss/40',
  accent: 'bg-accent/10',
};

const SPAN_LINE: Record<'on' | 'off' | 'plan', string> = {
  on: 'border-t-[1.5px] border-accent/60',
  off: 'border-t-[1.5px] border-fg-3/45',
  plan: 'border-t-[1.5px] border-dashed border-fg-3/45',
};

const ALIGN_SHIFT = { start: '0%', center: '-50%', end: '-100%' } as const;

function laneHeight(lane: CurveLane, compact: boolean): number {
  if (compact) return LANE_COMPACT;
  return lane.sub ? LANE_SUB : LANE;
}

const left = (f: number): CSSProperties => ({ left: `${(f * 100).toFixed(3)}%` });

/**
 * A large equity curve on a time axis with what happened on it: pins and guides above, a lane
 * per session, version or holding below, a Now line and a column for what is scheduled next.
 */
export function AnnotatedCurve({
  label,
  dates,
  values,
  benchmark,
  start: startProp,
  end: endProp,
  now,
  future,
  pins = [],
  bands = [],
  lanes = [],
  side,
  legend = [],
  height = 196,
  labelWidth = 212,
  futureWidth = 210,
  ticks,
  tickFormat,
  tooltip,
  area = true,
  className = '',
}: AnnotatedCurveProps) {
  const gradientId = useId();
  const [ref, width] = useWidth<HTMLDivElement>(1200);
  const compact = width < COMPACT_BELOW;
  const [hover, setHover] = useState<number | null>(null);

  const startMs = (startProp ?? dates[0])?.getTime() ?? 0;
  const endMs = (endProp ?? dates[dates.length - 1])?.getTime() ?? startMs;
  const start = useMemo(() => new Date(startMs), [startMs]);
  const end = useMemo(() => new Date(endMs), [endMs]);
  const spanDays = Math.max(1, (end.getTime() - start.getTime()) / 86_400_000);

  const domain = useMemo(
    () => yDomain(benchmark ? [values, benchmark] : [values]),
    [values, benchmark]
  );
  const main = useMemo(
    () => timePath(dates, values, start, end, domain, VIEW_W, height),
    [dates, values, start, end, domain, height]
  );
  const fill = useMemo(
    () => (area ? timeArea(dates, values, start, end, domain, VIEW_W, height) : ''),
    [area, dates, values, start, end, domain, height]
  );
  const bench = useMemo(
    () => (benchmark ? timePath(dates, benchmark, start, end, domain, VIEW_W, height) : ''),
    [dates, benchmark, start, end, domain, height]
  );

  const pinRows = pins.length ? Math.max(...pins.map((p) => p.row ?? 0)) + 1 : 0;
  const pinsH = pinRows ? pinRows * PIN_ROW + 6 : 0;
  const laneHs = lanes.map((l) => laneHeight(l, compact));
  const lanesH = laneHs.reduce((a, b) => a + b, 0);
  const totalH = pinsH + height + lanesH + AXIS;
  const futureW = future ? (compact ? Math.min(futureWidth, 56) : futureWidth) : 0;
  const showLabels = !compact;
  const axisTicks = ticks ?? monthTicks(start, end, compact ? 3 : 5);
  const fmt = tickFormat ?? ((d: Date) => tickLabel(d, spanDays));
  const fx = (t: Date) => timeFraction(t, start, end);
  const futureFx = (t: Date) => (future ? timeFraction(t, end, future.end) : 0);

  const yOf = (v: number) => (1 - (v - domain.lo) / (domain.hi - domain.lo || 1)) * height;
  const lastIdx = values.length - 1;
  const lastY = lastIdx >= 0 && Number.isFinite(values[lastIdx]) ? yOf(values[lastIdx]) : null;

  const onMove = (clientX: number, rect: DOMRect) => {
    if (!dates.length) return;
    const f = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    const t = new Date(start.getTime() + f * (end.getTime() - start.getTime()));
    setHover(nearestDateIndex(dates, t));
  };

  const gridCols = showLabels
    ? `${labelWidth}px minmax(0,1fr)${future ? ` ${futureW}px` : ''}`
    : `minmax(0,1fr)${future ? ` ${futureW}px` : ''}`;

  let laneTop = pinsH + height;
  const laneTops = laneHs.map((h) => {
    const top = laneTop;
    laneTop += h;
    return top;
  });

  return (
    <div ref={ref} className={`w-full ${className}`}>
      <div className="grid" style={{ gridTemplateColumns: gridCols }}>
        {showLabels && (
          <div className="relative min-w-0 pr-3.5" style={{ height: totalH }}>
            {side && (
              <div
                className="absolute inset-x-0 overflow-hidden pr-3.5"
                style={{ top: pinsH, height }}
              >
                {side}
              </div>
            )}
            {lanes.map((lane, i) => (
              <LaneLabel key={lane.id} lane={lane} top={laneTops[i]} height={laneHs[i]} />
            ))}
            {legend.length > 0 && (
              <div
                className="absolute inset-x-0 flex items-center"
                style={{ top: totalH - AXIS, height: AXIS }}
              >
                <LaneLegend items={legend} className="flex-nowrap" />
              </div>
            )}
          </div>
        )}

        <div className="relative min-w-0" style={{ height: totalH }}>
          {bands.map((b, i) => {
            const f0 = fx(b.from);
            const f1 = fx(b.to);
            return (
              <i
                key={`band-${i}`}
                aria-hidden="true"
                className={`pointer-events-none absolute ${BAND_TONE[b.tone ?? 'held']}`}
                style={{
                  ...left(f0),
                  width: `${(Math.max(0.002, f1 - f0) * 100).toFixed(3)}%`,
                  top: pinsH,
                  height: b.through ? height + lanesH : height,
                }}
              />
            );
          })}

          {pins.map((p, i) => {
            if (compact && (p.tone ?? 'neutral') === 'neutral') return null;
            const f = fx(p.at);
            const align = pinAlign(f);
            return (
              <span key={`pin-${i}`}>
                <span
                  className={`absolute inline-flex h-[18px] items-center gap-[5px] whitespace-nowrap rounded-full border px-[7px] font-mono text-[10.5px] font-medium ${PIN_TONE[p.tone ?? 'neutral']}`}
                  style={{
                    ...left(f),
                    top: (p.row ?? 0) * PIN_ROW + 2,
                    transform: `translateX(${ALIGN_SHIFT[align]})`,
                    zIndex: 4,
                  }}
                >
                  {p.count !== undefined && (
                    <b className="grid h-[13px] min-w-[13px] place-items-center rounded-full bg-accent px-0.5 text-[8.5px] font-semibold text-canvas">
                      {p.count}
                    </b>
                  )}
                  {p.label}
                </span>
                {p.guide !== false && (
                  <i
                    aria-hidden="true"
                    className="pointer-events-none absolute border-l border-dashed border-line-strong"
                    style={{ ...left(f), top: pinsH, height, zIndex: 1 }}
                  />
                )}
              </span>
            );
          })}

          <div
            className="absolute inset-x-0"
            style={{ top: pinsH, height }}
            onMouseMove={(e) => onMove(e.clientX, e.currentTarget.getBoundingClientRect())}
            onMouseLeave={() => setHover(null)}
            onTouchMove={(e) =>
              onMove(e.touches[0].clientX, e.currentTarget.getBoundingClientRect())
            }
            onTouchEnd={() => setHover(null)}
          >
            <svg
              role="img"
              aria-label={label}
              viewBox={`0 0 ${VIEW_W} ${height}`}
              preserveAspectRatio="none"
              width="100%"
              height={height}
              className="block overflow-visible"
            >
              <defs>
                <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="rgb(var(--accent))" stopOpacity="0.2" />
                  <stop offset="100%" stopColor="rgb(var(--accent))" stopOpacity="0.01" />
                </linearGradient>
              </defs>
              {fill && <path d={fill} fill={`url(#${gradientId})`} />}
              {bench && (
                <path
                  d={bench}
                  fill="none"
                  stroke="rgb(var(--fg-3))"
                  strokeWidth={1.2}
                  strokeDasharray="3 3"
                  vectorEffect="non-scaling-stroke"
                />
              )}
              {main && (
                <path
                  d={main}
                  fill="none"
                  stroke="rgb(var(--accent))"
                  strokeWidth={1.75}
                  strokeLinejoin="round"
                  vectorEffect="non-scaling-stroke"
                />
              )}
            </svg>
            {now && lastY !== null && dates[lastIdx] && (
              <i
                aria-hidden="true"
                className={`absolute h-[7px] w-[7px] -translate-x-1/2 -translate-y-1/2 rounded-full ${now.stale ? 'border-[1.5px] border-accent bg-panel' : 'bg-accent shadow-[0_0_0_3px_var(--accent-soft)]'}`}
                style={{ ...left(fx(dates[lastIdx])), top: lastY }}
              />
            )}
            {hover !== null && dates[hover] && Number.isFinite(values[hover]) && (
              <>
                <i
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-y-0 border-l border-dashed border-fg-3"
                  style={left(fx(dates[hover]))}
                />
                <i
                  aria-hidden="true"
                  className="pointer-events-none absolute h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-panel bg-accent"
                  style={{ ...left(fx(dates[hover])), top: yOf(values[hover]) }}
                />
                {tooltip && (
                  <div
                    className="pointer-events-none absolute z-10 whitespace-nowrap rounded border border-line-strong bg-panel px-2 py-1.5 font-mono text-[11px] leading-normal text-fg shadow-lg"
                    style={
                      fx(dates[hover]) > 0.6
                        ? {
                            right: `${((1 - fx(dates[hover])) * 100).toFixed(3)}%`,
                            top: 8,
                            marginRight: 12,
                          }
                        : { ...left(fx(dates[hover])), top: 8, marginLeft: 12 }
                    }
                  >
                    {tooltip(hover)}
                  </div>
                )}
              </>
            )}
          </div>

          {lanes.map((lane, i) => (
            <LaneTrack
              key={lane.id}
              lane={lane}
              top={laneTops[i]}
              height={laneHs[i]}
              fx={fx}
              start={start}
              end={end}
              compact={compact}
            />
          ))}

          <Axis top={totalH - AXIS} ticks={axisTicks} fx={fx} fmt={fmt} />

          {now && !future && (
            <NowMarker
              label={now.label}
              stale={now.stale}
              top={pinsH}
              height={totalH - pinsH}
              edge="right"
            />
          )}
        </div>

        {future && (
          <div
            className={`relative min-w-0 bg-sunk/70 ${now?.stale ? 'border-l-[1.5px] border-dashed border-fg' : 'border-l-[1.5px] border-fg'}`}
            style={{ height: totalH }}
          >
            {now && <NowMarker label={now.label} stale={now.stale} top={pinsH + 4} edge="left" />}
            {!compact && (future.title || future.content) && (
              <div
                className="absolute inset-x-3 text-[11.5px] text-fg-2"
                style={{ top: pinsH + 32 }}
              >
                {future.title && <div className="mb-1.5 text-fg-3">{future.title}</div>}
                {future.content}
              </div>
            )}
            {lanes.map((lane, i) => (
              <FutureTrack
                key={lane.id}
                lane={lane}
                top={laneTops[i]}
                height={laneHs[i]}
                fx={futureFx}
                compact={compact}
              />
            ))}
            {!compact && future.ticks && (
              <Axis top={totalH - AXIS} ticks={future.ticks} fx={futureFx} fmt={fmt} />
            )}
          </div>
        )}
      </div>
      {compact && legend.length > 0 && <LaneLegend items={legend} className="mt-2" />}
    </div>
  );
}

function LaneLabel({ lane, top, height }: { lane: CurveLane; top: number; height: number }) {
  const tone = lane.tone === 'risk' ? 'text-risk' : lane.tone === 'muted' ? 'text-fg-2' : 'text-fg';
  const name = (
    <span className={`min-w-0 truncate text-[12.5px] font-semibold ${tone}`}>{lane.label}</span>
  );
  return (
    <div
      className="absolute inset-x-0 flex items-center gap-2 border-t border-transparent pr-3.5"
      style={{ top, height }}
    >
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-2">
          {lane.href ? (
            <Link to={lane.href} className="flex min-w-0 hover:underline">
              {name}
            </Link>
          ) : (
            name
          )}
          {lane.badge}
        </div>
        {lane.sub && <div className="truncate text-[11px] leading-tight text-fg-3">{lane.sub}</div>}
      </div>
      {lane.value && <div className="flex-none font-mono text-[12px] text-fg">{lane.value}</div>}
    </div>
  );
}

function defaultSpans(lane: CurveLane, start: Date): readonly LaneSpan[] {
  return lane.spans ?? [{ from: start, style: 'on' }];
}

function LaneTrack({
  lane,
  top,
  height,
  fx,
  start,
  end,
  compact,
}: {
  lane: CurveLane;
  top: number;
  height: number;
  fx: (t: Date) => number;
  start: Date;
  end: Date;
  compact: boolean;
}) {
  const risk = lane.tone === 'risk';
  const midTop = compact ? 14 : 0;
  return (
    <div className="absolute inset-x-0 border-t border-line" style={{ top, height }}>
      {compact && (
        <span
          className={`absolute left-0 top-0.5 max-w-full truncate text-[11px] font-semibold ${risk ? 'text-risk' : 'text-fg-2'}`}
        >
          {lane.label}
        </span>
      )}
      <div className="absolute inset-x-0 bottom-0" style={{ top: midTop }}>
        {defaultSpans(lane, start).map((s, i) => {
          const f0 = fx(s.from);
          const f1 = fx(s.to ?? end);
          const width = `${(Math.max(0, f1 - f0) * 100).toFixed(3)}%`;
          const style = s.style ?? 'on';
          if (style === 'bar') {
            return (
              <span
                key={i}
                className={`absolute top-1/2 flex h-3 -translate-y-1/2 items-center overflow-hidden whitespace-nowrap rounded-[2px] border px-1.5 font-mono text-[10px] ${
                  s.tone === 'risk'
                    ? 'border-risk-line bg-risk-soft text-risk'
                    : s.tone === 'muted'
                      ? 'border-line-strong bg-sunk text-fg-3'
                      : 'border-accent/45 bg-accent/20 text-fg-2'
                } ${s.label ? 'h-[17px]' : ''}`}
                style={{ ...left(f0), width }}
              >
                {s.label}
              </span>
            );
          }
          return (
            <i
              key={i}
              aria-hidden="true"
              className={`absolute top-1/2 ${risk || s.tone === 'risk' ? 'border-t-[1.5px] border-risk' : SPAN_LINE[style]}`}
              style={{ ...left(f0), width }}
            />
          );
        })}
        {(lane.events ?? []).map((e, i) => (
          <EventMark key={i} event={e} f={fx(e.at)} laneRisk={risk} showText={!compact} />
        ))}
      </div>
    </div>
  );
}

function EventMark({
  event,
  f,
  laneRisk,
  showText = true,
}: {
  event: LaneEvent;
  f: number;
  laneRisk: boolean;
  showText?: boolean;
}) {
  const tone = event.tone ?? (laneRisk ? 'risk' : 'accent');
  return (
    <>
      <LaneMarker
        shape={event.shape}
        tone={tone}
        count={event.count}
        positioned
        title={event.title}
        style={left(f)}
      />
      {event.text && showText && (
        <span
          className="absolute top-1/2 z-[2] -translate-y-1/2 whitespace-nowrap bg-panel/80 pl-3 font-mono text-[10.5px] text-fg-2"
          style={left(f)}
        >
          {event.text}
        </span>
      )}
    </>
  );
}

function FutureTrack({
  lane,
  top,
  height,
  fx,
  compact,
}: {
  lane: CurveLane;
  top: number;
  height: number;
  fx: (t: Date) => number;
  compact: boolean;
}) {
  const fut = lane.future;
  const events = fut?.events ?? [];
  const line = fut?.line ?? events.length > 0;
  return (
    <div className="absolute inset-x-0 border-t border-line" style={{ top, height }}>
      <div className="absolute inset-x-0 bottom-0" style={{ top: compact ? 14 : 0 }}>
        {line && (
          <i
            aria-hidden="true"
            className="absolute inset-x-0 top-1/2 border-t-[1.5px] border-dashed border-fg-3/45"
          />
        )}
        {events.map((e, i) => (
          <EventMark
            key={i}
            event={e}
            f={Math.min(0.96, Math.max(0.04, fx(e.at)))}
            laneRisk={false}
          />
        ))}
        {fut?.note && !compact && (
          <span className="absolute left-3 right-2 top-1/2 -translate-y-1/2 truncate text-[11.5px] text-fg-3">
            {fut.note}
          </span>
        )}
      </div>
    </div>
  );
}

function Axis({
  top,
  ticks,
  fx,
  fmt,
}: {
  top: number;
  ticks: readonly Date[];
  fx: (t: Date) => number;
  fmt: (d: Date) => string;
}) {
  return (
    <div className="absolute inset-x-0 border-t border-line" style={{ top, height: AXIS }}>
      {ticks.map((t) => {
        const f = fx(t);
        const shift = f < 0.04 ? '0%' : f > 0.96 ? '-100%' : '-50%';
        return (
          <span
            key={t.getTime()}
            className="absolute top-[5px] whitespace-nowrap px-1 font-mono text-[10.5px] text-fg-3"
            style={{ ...left(f), transform: `translateX(${shift})` }}
          >
            {fmt(t)}
          </span>
        );
      })}
    </div>
  );
}

function NowMarker({
  label,
  stale,
  top,
  height,
  edge,
}: {
  label: string;
  stale?: boolean;
  top: number;
  height?: number;
  edge: 'left' | 'right';
}) {
  return (
    <>
      {edge === 'right' && height !== undefined && (
        <i
          aria-hidden="true"
          className={`absolute right-0 border-l-[1.5px] ${stale ? 'border-dashed' : ''} border-fg`}
          style={{ top, height }}
        />
      )}
      <span
        className={`absolute z-[5] whitespace-nowrap rounded px-1.5 py-px font-mono text-[10px] font-semibold ${
          stale ? 'border border-fg-3 bg-panel text-fg' : 'bg-fg text-canvas'
        }`}
        style={
          edge === 'left'
            ? { left: -1, top, transform: 'translateX(-50%)' }
            : { right: 0, top: top - 2, transform: 'translateX(50%)' }
        }
      >
        {label}
      </span>
    </>
  );
}
