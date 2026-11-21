import { useState, type MouseEvent, type ReactNode } from 'react';

import { useWidth } from '../charts/useWidth';
import { Segmented } from '../ui';

import { dayLabel, etDay, HOME_RANGES, signedPct, toneText, type HomeRange } from './homeModel';
import { HomeCard } from './HomePanels';
import type { Line, PerfWindow } from './perfModel';

const RANGE_LABEL: Record<HomeRange, string> = {
  '1W': '1W',
  '1M': '1M',
  '3M': '3M',
  '1Y': '1Y',
  ALL: 'All',
};
const RANGE_WORDS: Record<HomeRange, string> = {
  '1W': 'Past week',
  '1M': 'Past month',
  '3M': 'Past three months',
  '1Y': 'Past year',
  ALL: 'Since the first session',
};

const H = 320;
const PT = 60;
const PB = 26;
const PR = 92;
const DH = 84;

function niceStep(span: number, target: number) {
  const raw = span / target;
  return [0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10, 20, 25, 50].find((s) => s >= raw) ?? 100;
}

const pathOf = (
  s: readonly (number | null)[],
  x: (i: number) => number,
  y: (v: number) => number
) =>
  s
    .map((v, i) =>
      v === null
        ? ''
        : `${i === 0 || s[i - 1] === null ? 'M' : 'L'}${x(i).toFixed(1)},${y(v).toFixed(1)}`
    )
    .join('');

const lastOf = (l: Line) => {
  for (let i = l.length - 1; i >= 0; i--) if (l[i] !== null) return { i, v: l[i] ?? 0 };
  return null;
};

const AX = 'fill-fg-3 font-mono text-[11px]';

export interface PerfSelection {
  label: string;
  line: Line;
}

function Legend({ hasSpy, selection }: { hasSpy: boolean; selection: PerfSelection | null }) {
  const end = selection ? lastOf(selection.line) : null;
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-[18px] gap-y-1 text-[12px] text-fg-3">
      <span className="inline-flex items-center gap-[7px]">
        <i aria-hidden="true" className="w-4 border-t-2 border-accent" />
        Account
      </span>
      {hasSpy && (
        <span className="inline-flex items-center gap-[7px]">
          <i aria-hidden="true" className="w-4 border-t-[1.5px] border-dashed border-fg-3" />
          SPY
        </span>
      )}
      <span className="inline-flex items-center gap-[7px]">
        <i aria-hidden="true" className="h-2 w-2 rounded-full border-[1.5px] border-fg bg-panel" />
        Day with fills
      </span>
      <span className="inline-flex items-center gap-[7px]">
        <ChangeNumber n={1} />
        Session change, listed below
      </span>
      {selection && (
        <span className="inline-flex items-center gap-[7px] text-fg">
          <i aria-hidden="true" className="w-4 border-t-[1.5px] border-fg" />
          {selection.label}
          {end && (
            <b className={`font-mono font-medium ${toneText(end.v)}`}>{signedPct(end.v, 1)}</b>
          )}
        </span>
      )}
    </div>
  );
}

function ChangeNumber({ n }: { n: number }) {
  return (
    <i className="inline-grid h-4 w-4 flex-none place-items-center rounded-[4px] border border-line-strong bg-sunk font-mono text-[10px] not-italic text-fg">
      {n}
    </i>
  );
}

export interface PerfCardProps {
  perf: PerfWindow | null;
  range: HomeRange;
  onRange: (r: HomeRange) => void;
  selection: PerfSelection | null;
  /** A session hovered elsewhere on Home; its marks stay lit and the rest fade. */
  hotSession: string | null;
  /** Shown in place of the chart with under two daily snapshots in the range. */
  empty: ReactNode;
}

/** home/perf: the account against SPY over a range, with a stats strip, markers and the drawdown. */
export function PerfCard({ perf, range, onRange, selection, hotSession, empty }: PerfCardProps) {
  return (
    <HomeCard
      title="Account against SPY"
      sub={<Legend hasSpy={Boolean(perf?.spy)} selection={selection} />}
      right={
        <Segmented<HomeRange>
          label="Range"
          value={range}
          onChange={onRange}
          options={HOME_RANGES.map((r) => ({ key: r, label: RANGE_LABEL[r] }))}
        />
      }
    >
      {perf ? (
        <PerfBody perf={perf} range={range} selection={selection} hotSession={hotSession} />
      ) : (
        <div className="p-5">{empty}</div>
      )}
    </HomeCard>
  );
}

function Stats({ perf, range }: { perf: PerfWindow; range: HomeRange }) {
  const n = perf.acc.length;
  const ea = perf.acc[n - 1];
  const es = perf.spy ? perf.spy[n - 1] : null;
  const diff = es === null ? null : ea - es;
  const sessionsTraded = new Set(perf.dots.map((d) => `${d.sessionId}:${d.index}`)).size;
  const stats: [string, ReactNode, string][] = [
    [
      'Account',
      <span key="a" className={toneText(ea)}>
        {signedPct(ea)}
      </span>,
      RANGE_WORDS[range],
    ],
    [
      'SPY',
      es === null ? (
        <span key="s" className="text-fg-3">
          No data
        </span>
      ) : (
        <span key="s" className={toneText(es)}>
          {signedPct(es)}
        </span>
      ),
      'Same dates',
    ],
    [
      'Against SPY',
      diff === null ? '' : `${diff >= 0 ? '+' : '−'}${Math.abs(diff).toFixed(2)} pts`,
      diff === null
        ? 'No benchmark data'
        : diff >= 0
          ? 'Ahead over this range'
          : 'Behind over this range',
    ],
    [
      'Worst drop',
      signedPct(perf.accDrawdown[perf.worst], 1),
      perf.accDrawdown[perf.worst] < 0
        ? `Reached ${dayLabel(etDay(perf.dates[perf.worst]))}`
        : 'No drop from a high',
    ],
    ['Fills', String(perf.fills), 'Orders filled in range'],
    ['Rebalances', String(sessionsTraded), 'Days a session traded'],
  ];
  return (
    <div className="mx-5 mt-4 grid grid-cols-3 border-y border-line xl:grid-cols-6">
      {stats.map(([k, v, s], i) => (
        <div
          key={k}
          className={`min-w-0 py-3 ${
            i === 0
              ? 'pl-0'
              : i === 3
                ? 'pl-0 xl:border-l xl:border-line xl:pl-4'
                : 'border-l border-line pl-4'
          }`}
        >
          <span className="mb-[7px] block font-mono text-[10.5px] font-medium uppercase tracking-[0.08em] text-fg-3">
            {k}
          </span>
          <div className="font-mono text-[19px] font-medium leading-[1.1] tracking-[-0.02em] text-fg">
            {v}
          </div>
          <div className="mt-[3px] truncate text-[12px] text-fg-3">{s}</div>
        </div>
      ))}
    </div>
  );
}

function PerfBody({
  perf,
  range,
  selection,
  hotSession,
}: {
  perf: PerfWindow;
  range: HomeRange;
  selection: PerfSelection | null;
  hotSession: string | null;
}) {
  const [ref, W] = useWidth<HTMLDivElement>(1100);
  const [hov, setHov] = useState<{ i: number; left: number } | null>(null);
  const { acc, spy, dates } = perf;
  const n = acc.length;
  const sel = selection?.line ?? null;
  const vals = [...acc, ...(spy ?? []), ...(sel ?? []).filter((v): v is number => v !== null)];
  let lo = Math.min(...vals, 0);
  let hi = Math.max(...vals, 0);
  const st = niceStep(hi - lo || 1, 5);
  lo = Math.floor(lo / st) * st;
  hi = Math.ceil(hi / st) * st;
  if (hi - lo < st * 3) hi += st;
  const plotW = Math.max(100, W - PR);
  const x = (i: number) => (n > 1 ? (i / (n - 1)) * plotW : 0);
  const y = (v: number) => PT + (1 - (v - lo) / (hi - lo)) * (H - PT - PB);
  const dec = st === 0.25 ? 2 : Number.isInteger(st) ? 0 : 1;
  const grid: number[] = [];
  for (let v = lo; v <= hi + 1e-9; v += st) grid.push(v);
  const label = (i: number) => dayLabel(etDay(dates[i]));
  // Several snapshots can share a day, so a label is drawn once.
  const ticks = [
    ...new Set(Array.from({ length: 6 }, (_, k) => Math.round((k * (n - 1)) / 5))),
  ].filter((i, k, all) => k === 0 || label(i) !== label(all[k - 1]));

  const lanes: [number, number][][] = [[], [], []];
  const placed = perf.changes.map((c, k) => {
    const X = x(c.index);
    let row = lanes.findIndex((lane) => lane.every(([a, b]) => X + 10 < a || X - 10 > b));
    if (row < 0) row = 2;
    lanes[row].push([X - 8, X + 8]);
    return { c, X, Y: 2 + row * 18, n: k + 1 };
  });
  const fade = (sessionId: string) =>
    hotSession ? (sessionId === hotSession ? 'opacity-100' : 'opacity-[0.12]') : '';

  const ea = acc[n - 1];
  const es = spy ? spy[n - 1] : null;
  const xe = x(n - 1);
  let ya = y(ea);
  let ys = es === null ? 0 : y(es);
  if (es !== null && Math.abs(ya - ys) < 14) {
    const up = ya < ys ? -7 : 7;
    ya += up;
    ys -= up;
  }

  const dd = perf.accDrawdown;
  const ddS = perf.spyDrawdown;
  const wi = perf.worst;
  let dlo = Math.min(...dd, ...(ddS ?? []));
  const dst = niceStep(-dlo || 1, 2);
  dlo = Math.floor(dlo / dst) * dst;
  if (dlo === 0) dlo = -dst;
  const dy = (v: number) => 4 + (v / dlo) * (DH - 20);
  const dgrid: number[] = [];
  for (let v = 0; v >= dlo - 1e-9; v -= dst) dgrid.push(v);
  const wl = x(wi) > plotW * 0.7;

  const move = (e: MouseEvent<SVGRectElement>) => {
    const bb = e.currentTarget.getBoundingClientRect();
    const i = Math.max(0, Math.min(n - 1, Math.round(((e.clientX - bb.left) / plotW) * (n - 1))));
    const left = e.clientX - bb.left + 20;
    setHov({ i, left: left + 240 > W ? left - 262 : left + 16 });
  };
  const hi2 = hov?.i;
  const dotsAt = hi2 === undefined ? [] : perf.dots.filter((d) => d.index === hi2);
  const changesAt = hi2 === undefined ? [] : perf.changes.filter((c) => c.index === hi2);
  const selEnd = sel ? lastOf(sel) : null;

  return (
    <>
      <Stats perf={perf} range={range} />
      <div className="relative px-5 pt-1.5" ref={ref}>
        <svg
          viewBox={`0 0 ${W} ${H}`}
          height={H}
          className="block w-full overflow-visible"
          role="img"
          aria-label={`Account${spy ? ' and SPY' : ''} over the range`}
        >
          <defs>
            <linearGradient id="home-perf-area" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="rgb(var(--accent))" stopOpacity=".12" />
              <stop offset="1" stopColor="rgb(var(--accent))" stopOpacity="0" />
            </linearGradient>
          </defs>
          {grid.map((v) => (
            <g key={v}>
              <line
                className={Math.abs(v) < 1e-9 ? 'stroke-line-strong' : 'stroke-line'}
                x1="0"
                x2={plotW}
                y1={y(v)}
                y2={y(v)}
              />
              <text className={AX} x={W} y={y(v) + 4} textAnchor="end">
                {Math.abs(v) < 1e-9 ? '0%' : signedPct(v, dec)}
              </text>
            </g>
          ))}
          {placed.map(({ c, X, Y, n: k }) => (
            <g
              key={`${c.sessionId}${c.label}`}
              className={`transition-opacity ${fade(c.sessionId)}`}
            >
              <line
                className="stroke-fg-3 [stroke-dasharray:2_3]"
                x1={X}
                x2={X}
                y1={PT - 4}
                y2={H - PB}
              />
              <line className="stroke-fg-3" x1={X} x2={X} y1={Y + 16} y2={PT - 4} />
              <rect
                x={X - 8}
                y={Y}
                width="16"
                height="16"
                rx="3"
                className="fill-sunk stroke-line-strong"
              />
              <text
                className="fill-fg font-mono text-[10px]"
                x={X}
                y={Y + 11.5}
                textAnchor="middle"
              >
                {k}
              </text>
            </g>
          ))}
          {ticks.map((i, k) => (
            <text
              key={i}
              className={AX}
              x={x(i)}
              y={H - 6}
              textAnchor={k === 0 ? 'start' : k === ticks.length - 1 ? 'end' : 'middle'}
            >
              {label(i)}
            </text>
          ))}
          <path d={`${pathOf(acc, x, y)}L${xe},${y(0)}L0,${y(0)}Z`} fill="url(#home-perf-area)" />
          {spy && (
            <path
              d={pathOf(spy, x, y)}
              className="fill-none stroke-fg-3 [stroke-dasharray:3_3] [stroke-width:1.3]"
            />
          )}
          {sel && (
            <>
              <path
                d={pathOf(sel, x, y)}
                className="fill-none stroke-fg opacity-85 [stroke-linejoin:round] [stroke-width:1.4]"
              />
              {selEnd && <circle cx={x(selEnd.i)} cy={y(selEnd.v)} r="2.8" className="fill-fg" />}
            </>
          )}
          <path
            d={pathOf(acc, x, y)}
            className="fill-none stroke-accent [stroke-linejoin:round] [stroke-width:2]"
          />
          {perf.dots.map((d) => (
            <circle
              key={`${d.sessionId}${d.index}`}
              className={`fill-panel stroke-fg transition-opacity [stroke-width:1.4] ${fade(d.sessionId)}`}
              cx={x(d.index)}
              cy={y(acc[d.index])}
              r={3.2}
            />
          ))}
          <circle cx={xe} cy={y(ea)} r="3.4" className="fill-accent" />
          {es !== null && <circle cx={xe} cy={y(es)} r="2.6" className="fill-fg-3" />}
          <text className="fill-accent font-mono text-[11px] font-medium" x={xe + 8} y={ya + 4}>
            {signedPct(ea, 1)}
          </text>
          {es !== null && (
            <text className={AX} x={xe + 8} y={ys + 4}>
              {signedPct(es, 1)}
            </text>
          )}
          {hi2 !== undefined && (
            <g>
              <line className="stroke-fg-2" x1={x(hi2)} x2={x(hi2)} y1={PT - 4} y2={H - PB} />
              {sel && sel[hi2] !== null && (
                <circle
                  cx={x(hi2)}
                  cy={y(sel[hi2] ?? 0)}
                  r="3.2"
                  className="fill-fg stroke-panel [stroke-width:2]"
                />
              )}
              {spy && (
                <circle
                  cx={x(hi2)}
                  cy={y(spy[hi2])}
                  r="3.4"
                  className="fill-fg-3 stroke-panel [stroke-width:2]"
                />
              )}
              <circle
                cx={x(hi2)}
                cy={y(acc[hi2])}
                r="4"
                className="fill-accent stroke-panel [stroke-width:2]"
              />
            </g>
          )}
          <rect
            x="0"
            y="0"
            width={plotW}
            height={H}
            fill="transparent"
            onMouseMove={move}
            onMouseLeave={() => setHov(null)}
          />
        </svg>
        {hov && (
          <div
            className="pointer-events-none absolute z-10 min-w-[220px] rounded-[8px] bg-panel px-3 py-2.5 text-[12.5px] text-fg-2 shadow-[0_14px_34px_-14px_rgb(0_0_0/0.28),0_0_0_1px_rgb(var(--line-strong))]"
            style={{ left: hov.left, top: Math.max(0, y(acc[hov.i]) - 20) }}
          >
            <span className="font-mono text-[10.5px] font-medium uppercase tracking-[0.08em] text-fg-3">
              {label(hov.i)}
            </span>
            <TipRow label="Account" value={signedPct(acc[hov.i])} />
            {spy && <TipRow label="SPY" value={signedPct(spy[hov.i])} />}
            {sel && selection && (
              <TipRow
                label={selection.label}
                value={sel[hov.i] === null ? 'Not started' : signedPct(sel[hov.i] ?? 0)}
              />
            )}
            <TipRow label="Account drawdown" value={signedPct(dd[hov.i])} />
            {dotsAt.length > 0 && (
              <div className="mt-1.5 border-t border-line pt-1.5 text-fg">
                {dotsAt.reduce((a, d) => a + d.fills, 0)} fills
              </div>
            )}
            {changesAt.map((c) => (
              <div key={c.label} className="mt-1 text-fg">
                {c.label}
              </div>
            ))}
          </div>
        )}
        {placed.length > 0 && (
          <div className="flex flex-wrap gap-x-[22px] gap-y-1.5 pb-3 pt-1 text-[12.5px] text-fg-2">
            {placed.map(({ c, n: k }) => (
              <span
                key={`${c.sessionId}${c.label}`}
                className={`inline-flex items-center gap-[7px] transition-opacity ${fade(c.sessionId)}`}
              >
                <ChangeNumber n={k} />
                {c.label}
                <span className="font-mono text-[12px] text-fg-3">{dayLabel(etDay(c.at))}</span>
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="mx-5 mt-1 flex items-baseline justify-between border-t border-line pt-2.5">
        <span className="font-mono text-[10.5px] font-medium uppercase tracking-[0.08em] text-fg-3">
          Drawdown from the range&apos;s peak
        </span>
        <span className="text-[12px] text-fg-3">
          Account worst <b className="font-mono font-medium text-fg">{signedPct(dd[wi], 1)}</b>
          {ddS && (
            <>
              {' '}
              · SPY worst{' '}
              <b className="font-mono font-medium text-fg">{signedPct(Math.min(...ddS), 1)}</b>
            </>
          )}
        </span>
      </div>
      <div className="px-5 pb-3.5 pt-1.5">
        <svg
          viewBox={`0 0 ${W} ${DH}`}
          height={DH}
          className="block w-full overflow-visible"
          role="img"
          aria-label="Drawdown from the range's peak"
        >
          {dgrid.map((v) => (
            <g key={v}>
              <line
                className={v === 0 ? 'stroke-line-strong' : 'stroke-line'}
                x1="0"
                x2={plotW}
                y1={dy(v)}
                y2={dy(v)}
              />
              <text className={AX} x={W} y={dy(v) + 4} textAnchor="end">
                {v === 0 ? '0%' : signedPct(v, dst < 1 ? 1 : 0)}
              </text>
            </g>
          ))}
          <path
            d={`${pathOf(dd, x, dy)}L${xe},${dy(0)}L0,${dy(0)}Z`}
            className="fill-fg-2/[0.14]"
          />
          {ddS && (
            <path
              d={pathOf(ddS, x, dy)}
              className="fill-none stroke-fg-3 [stroke-dasharray:3_3] [stroke-width:1.3]"
            />
          )}
          <path d={pathOf(dd, x, dy)} className="fill-none stroke-fg-2 [stroke-width:1.4]" />
          {dd[wi] < 0 && (
            <>
              <circle cx={x(wi)} cy={dy(dd[wi])} r="3" className="fill-fg" />
              <text
                className="fill-fg stroke-panel font-mono text-[11px] [paint-order:stroke] [stroke-width:4px]"
                x={x(wi) + (wl ? -8 : 8)}
                y={dy(dd[wi]) + 14}
                textAnchor={wl ? 'end' : 'start'}
              >
                {signedPct(dd[wi], 1)} {label(wi)}
              </text>
            </>
          )}
        </svg>
      </div>
    </>
  );
}

function TipRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="mt-1 flex justify-between gap-4">
      <span>{label}</span>
      <b className="font-mono font-medium text-fg">{value}</b>
    </div>
  );
}
