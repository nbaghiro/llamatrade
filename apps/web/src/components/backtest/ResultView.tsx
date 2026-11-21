import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toNumber } from '@llamatrade/core/stores/backtest';
import { useMemo, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import {
  daysBackToHigh,
  startsAtFloor,
  stretchFigures,
  stretchesWithin,
  type CuratedRange,
} from '../../lib/backtestRanges';
import {
  alignTo,
  figuresFromCurve,
  longDate,
  tradesToOrders,
  type RebalanceFrequency,
  type TradeInput,
} from '../../lib/backtestView';
import { formatMoney, formatNumber, formatPct } from '../../lib/format';
import type { CurveBand, CurvePin } from '../charts';
import { Pct } from '../ui/Num';
import { Segmented } from '../ui/Tabs';

import {
  holdingLanes,
  LOG_SCALE_FROM_YEARS,
  mostlyHeld,
  rebalanceMarks,
  scheduleFor,
  worstStretch,
  yearsBetween,
} from './annotations';
import { KvList } from './parts';
import {
  defensiveStretches,
  drawdownPhrase,
  inStocksShare,
  joinWords,
  switchSentence,
  toSymbolsLabel,
} from './resultStory';
import { RunCurve } from './RunCurve';
import { runMeta, toCurve } from './runData';
import { openSessionLabel, type StrategySession } from './strategySessions';

/** A move into bonds or gold shorter than this reads as noise, not a switch. */
const MIN_MOVE_DAYS = 5;
const DAY_MS = 86_400_000;

const shortDate = (d: Date) =>
  d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  });
const monthYear = (iso: string) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-US', {
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  });

interface ResultViewProps {
  run: BacktestRun;
  strategyName: string;
  /** The run's trades: null while they load. */
  trades: readonly TradeInput[] | null;
  rebalance: RebalanceFrequency | null;
  /** The session running this version, if any. */
  session: StrategySession | null;
  /** A curated range this version hasn't run on yet. */
  next: CuratedRange | null;
  onNext: (range: CuratedRange) => void;
  onOpenTrades: () => void;
}

/** A finished run, annotated: the sentence and figures, the curve with what it held, the side notes. */
export function ResultView({
  run,
  strategyName,
  trades,
  rebalance,
  session,
  next,
  onNext,
  onOpenTrades,
}: ResultViewProps) {
  const m = run.results?.metrics;
  const meta = runMeta(run);
  const bench = meta.benchmark;
  const version = `v${run.strategyVersion}`;

  const eq = useMemo(() => toCurve(run.results?.equityCurve), [run]);
  const benchCurve = useMemo(() => toCurve(run.results?.benchmarkEquityCurve), [run]);
  const benchAligned = useMemo(() => alignTo(eq.dates, benchCurve), [eq, benchCurve]);
  const benchFig = useMemo(() => figuresFromCurve(benchCurve.values), [benchCurve]);
  const benchValues = benchAligned.every((v): v is number => v !== null) ? benchAligned : null;

  const start = eq.dates[0] ?? meta.start;
  const end = eq.dates[eq.dates.length - 1] ?? meta.end;
  const long =
    meta.start && meta.end ? yearsBetween(meta.start, meta.end) > LOG_SCALE_FROM_YEARS : false;
  const [scaleChoice, setScale] = useState<'linear' | 'log' | null>(null);
  const scale = scaleChoice ?? (long ? 'log' : 'linear');

  const startMs = meta.start?.getTime() ?? null;
  const endMs = meta.end?.getTime() ?? null;
  const schedule = useMemo(
    () =>
      scheduleFor(
        startMs === null ? null : new Date(startMs),
        endMs === null ? null : new Date(endMs),
        rebalance
      ),
    [startMs, endMs, rebalance]
  );

  const story = useMemo(() => {
    if (!trades || !start || !end) return null;
    const lanes = holdingLanes(trades, start, end);
    const moves = defensiveStretches(lanes, eq.dates).filter(
      (s) => s.to.getTime() - s.from.getTime() >= MIN_MOVE_DAYS * DAY_MS
    );
    return {
      lanes,
      moves,
      switches: rebalanceMarks(trades).filter((x) => x.switched).length,
      orders: tradesToOrders(trades).length,
      inStocks: inStocksShare(lanes, eq.dates),
    };
  }, [trades, start, end, eq]);

  const worst = useMemo(() => worstStretch(eq.dates, eq.values), [eq]);
  const stretches = useMemo(
    () => (long && meta.start && meta.end ? stretchesWithin(meta.start, meta.end) : []),
    [long, meta.start, meta.end]
  );
  const stretchRows = useMemo(
    () => stretchFigures(stretches, eq.dates, eq.values, benchValues),
    [stretches, eq, benchValues]
  );

  if (!m || eq.values.length < 2 || !start || !end) {
    return (
      <p className="m-0 rounded-panel border border-line bg-panel px-4 py-16 text-center text-[12.5px] text-fg-3">
        This run has no equity points.
      </p>
    );
  }

  const total = toNumber(m.totalReturn);
  const benchTotal = bench && m.benchmarkReturn ? toNumber(m.benchmarkReturn) : null;
  const mdd = -Math.abs(toNumber(m.maxDrawdown));
  const ended = eq.values[eq.values.length - 1];
  const benchEnded = benchValues ? benchValues[benchValues.length - 1] : null;
  const defensiveNames = story ? [...new Set(story.moves.flatMap((s) => s.symbols))].sort() : [];

  const bands: CurveBand[] = long
    ? stretches.map((s) => ({
        from: new Date(`${s.start}T00:00:00Z`),
        to: new Date(`${s.end}T00:00:00Z`),
        tone: 'held' as const,
        through: true,
      }))
    : (story?.moves ?? []).map((s) => ({
        from: s.from,
        to: s.to,
        tone: 'accent' as const,
        through: true,
      }));

  const firstMove = story?.moves[0];
  const pins: CurvePin[] = [
    ...(long
      ? stretches.map((s) => ({
          at: new Date(`${s.start}T00:00:00Z`),
          label: s.label,
          guide: false,
        }))
      : firstMove
        ? [
            {
              at: firstMove.from,
              label: `${toSymbolsLabel(firstMove.symbols)} · ${shortDate(firstMove.from)}`,
              guide: false,
            },
          ]
        : []),
    {
      at: end,
      label: `${formatMoney(ended, { dp: 0 })}${benchEnded !== null && bench ? ` · ${bench} ${formatMoney(benchEnded, { dp: 0 })}` : ''}`,
      guide: false,
    },
  ];

  const side = (
    <dl className="m-0 grid gap-0 pt-1 text-[12.5px]">
      {(
        [
          ['Ended', formatMoney(ended, { dp: 0 })],
          ['Peak', formatMoney(Math.max(...eq.values), { dp: 0 })],
          ['Orders', story ? formatNumber(story.orders, { dp: 0 }) : '·'],
          ['Switches', story ? formatNumber(story.switches, { dp: 0 }) : '·'],
          [
            'In stocks',
            story?.inStocks !== null && story?.inStocks !== undefined
              ? formatPct(story.inStocks, { dp: 0 })
              : '·',
          ],
          ...(scale === 'log' ? [['Scale', 'Log']] : []),
        ] as [string, string][]
      ).map(([k, v]) => (
        <div
          key={k}
          className="flex justify-between gap-2 border-b border-line py-[7px] last:border-b-0"
        >
          <dt className="text-fg-2">{k}</dt>
          <dd className="m-0 font-mono tabular-nums text-fg">{v}</dd>
        </div>
      ))}
    </dl>
  );

  const signed = (x: number) => formatPct(x, { dp: 1, signed: true });
  const ratio = (x: number) => formatNumber(x, { dp: 2 });
  const vs = (v: number | undefined, fmt: (x: number) => string) =>
    bench && benchFig && v !== undefined ? `${bench} ${fmt(v)}` : undefined;

  const figures: { label: string; value: ReactNode; sub?: string }[] = [
    {
      label: 'Total return',
      value: <Pct value={total} pnl dp={1} />,
      sub: benchTotal !== null ? `${bench} ${signed(benchTotal)}` : undefined,
    },
    {
      label: 'CAGR',
      value: formatPct(toNumber(m.annualizedReturn), { dp: 1 }),
      sub: vs(benchFig?.cagr, (x) => formatPct(x, { dp: 1 })),
    },
    { label: 'Sharpe', value: ratio(toNumber(m.sharpeRatio)), sub: vs(benchFig?.sharpe, ratio) },
    { label: 'Sortino', value: ratio(toNumber(m.sortinoRatio)), sub: vs(benchFig?.sortino, ratio) },
    {
      label: 'Max drawdown',
      value: <span className="text-loss">{formatPct(mdd, { dp: 1 })}</span>,
      sub: vs(benchFig?.maxDrawdown, (x) => formatPct(x, { dp: 1 })),
    },
    {
      label: 'Volatility',
      value: m.volatility ? (
        formatPct(toNumber(m.volatility), { dp: 1 })
      ) : (
        <span className="text-fg-3" title="Not computed for this run">
          ·
        </span>
      ),
      sub: vs(benchFig?.volatility, (x) => formatPct(x, { dp: 1 })),
    },
  ];

  const gap = benchTotal === null ? null : (total - benchTotal) * 100;
  const moveSentence = story ? switchSentence(story.moves) : null;
  const closing = (m.winningTrades ?? 0) + (m.losingTrades ?? 0);
  const worstDays = worst
    ? Math.round(((worst.recovered ?? end).getTime() - worst.peak.getTime()) / DAY_MS)
    : 0;
  const heldThen =
    worst && story ? mostlyHeld(story.lanes, eq.dates, worst.peak, worst.trough) : null;

  return (
    <div className="grid min-w-0 gap-3.5">
      <div className="grid items-start gap-3.5 xl:grid-cols-[minmax(0,1fr)_minmax(0,640px)]">
        <p className="m-0 max-w-[560px] text-[15px] leading-relaxed text-fg-2">
          Returned <Pct value={total} pnl dp={1} className="font-semibold" /> in this backtest
          {gap !== null && (
            <>
              , <span className="num">{formatNumber(Math.abs(gap), { dp: 1 })}</span> points{' '}
              {gap >= 0 ? 'more' : 'less'} than {bench}
            </>
          )}
          {benchFig && bench && (
            <>
              , with{' '}
              <b className="font-semibold text-fg">
                {drawdownPhrase(mdd, benchFig.maxDrawdown, bench)}
              </b>
            </>
          )}
          .{moveSentence ? ` ${moveSentence}` : ''}
        </p>
        <dl className="m-0 grid grid-cols-3 overflow-hidden rounded-panel border border-line bg-panel sm:grid-cols-6">
          {figures.map((f) => (
            <div
              key={f.label}
              className="min-w-0 border-b border-r border-line px-2.5 py-2.5 [&:nth-child(3n)]:border-r-0 sm:border-b-0 sm:[&:nth-child(3n)]:border-r sm:last:border-r-0"
            >
              <dt className="truncate text-[10px] font-medium uppercase tracking-[0.04em] text-fg-3">
                {f.label}
              </dt>
              <dd className="m-0 mt-1 whitespace-nowrap font-mono text-[16px] font-medium tabular-nums text-fg">
                {f.value}
              </dd>
              {f.sub && (
                <dd className="m-0 mt-0.5 whitespace-nowrap font-mono text-[10.5px] text-fg-3">
                  {f.sub}
                </dd>
              )}
            </div>
          ))}
        </dl>
      </div>

      <div className="grid items-start gap-3.5 lg:grid-cols-[minmax(0,1fr)_250px]">
        <section
          aria-label={`${strategyName} ${version} curve`}
          className="min-w-0 rounded-panel border border-line bg-panel px-3.5 pb-3 pt-3"
        >
          <header className="mb-2 flex flex-wrap items-center justify-between gap-2.5">
            <h2 className="m-0 font-sans text-[13px] font-semibold tracking-normal">
              Growth of {formatMoney(meta.capital, { dp: 0 })}
            </h2>
            <div className="flex flex-wrap items-center gap-3.5 text-[11.5px] text-fg-2">
              <span className="inline-flex items-center gap-1.5">
                <i aria-hidden="true" className="w-3.5 border-t-[1.5px] border-accent" />
                {strategyName} {version}
              </span>
              {bench && (
                <span className="inline-flex items-center gap-1.5">
                  <i aria-hidden="true" className="w-3.5 border-t border-dashed border-fg-3" />
                  {bench}
                </span>
              )}
              {long
                ? stretches.length > 0 && (
                    <span className="inline-flex items-center gap-1.5">
                      <i aria-hidden="true" className="h-2.5 w-2.5 rounded-sm bg-fg-3/20" />
                      Hard stretch
                    </span>
                  )
                : defensiveNames.length > 0 && (
                    <span className="inline-flex items-center gap-1.5">
                      <i aria-hidden="true" className="h-2.5 w-2.5 rounded-sm bg-accent/20" />
                      In {joinWords(defensiveNames)}
                    </span>
                  )}
              {worst && (
                <span className="inline-flex items-center gap-1.5">
                  <i
                    aria-hidden="true"
                    className="h-2.5 w-2.5 rounded-sm border border-loss/40 bg-loss/10"
                  />
                  Worst drawdown
                </span>
              )}
              {long && (
                <Segmented
                  label="Scale"
                  value={scale}
                  onChange={setScale}
                  options={[
                    { key: 'linear', label: 'Linear' },
                    { key: 'log', label: 'Log' },
                  ]}
                />
              )}
            </div>
          </header>
          <RunCurve
            strategyName={`${strategyName} ${version}`}
            benchmark={bench}
            dates={eq.dates}
            values={eq.values}
            benchValues={benchValues}
            trades={trades}
            log={scale === 'log'}
            extraBands={bands}
            extraPins={pins}
            side={side}
            drawdown={false}
            schedule={schedule}
            scheduleLabel={
              rebalance ? `${rebalance[0].toUpperCase()}${rebalance.slice(1)} rebalance` : undefined
            }
            foldDefensive={long}
          />
        </section>

        <div className="grid gap-3.5">
          {long && stretchRows.length > 0 && (
            <SideBox title="During each stretch">
              <table className="w-full border-collapse text-[12.5px]">
                <thead>
                  <tr className="text-[10.5px] uppercase tracking-[0.04em] text-fg-3">
                    <th className="py-1 text-left font-medium">
                      <span className="sr-only">Stretch</span>
                    </th>
                    <th className="py-1 text-right font-medium">{version}</th>
                    {bench && <th className="py-1 text-right font-medium">{bench}</th>}
                  </tr>
                </thead>
                <tbody>
                  {stretchRows.map((r) => (
                    <tr key={r.stretch.id} className="border-t border-line">
                      <td className="py-[7px] text-fg-2">{r.stretch.label}</td>
                      <td className="py-[7px] text-right font-mono tabular-nums text-loss">
                        {formatPct(r.run, { dp: 1 })}
                      </td>
                      {bench && (
                        <td className="py-[7px] text-right font-mono tabular-nums text-fg-2">
                          {r.bench === null ? '·' : formatPct(r.bench, { dp: 1 })}
                        </td>
                      )}
                    </tr>
                  ))}
                  {stretches.some((s) => s.id === 'mar-2020') && (
                    <BackToHigh
                      dates={eq.dates}
                      values={eq.values}
                      bench={benchValues}
                      hasBench={Boolean(bench)}
                    />
                  )}
                </tbody>
              </table>
              <p className="m-0 mt-2 text-[11.5px] text-fg-3">
                {stretches
                  .map(
                    (s) =>
                      `${s.label} is ${shortDate(new Date(`${s.start}T00:00:00Z`))} to ${shortDate(new Date(`${s.end}T00:00:00Z`))}`
                  )
                  .join(', ')}
                , peak to low for {bench || 'the market'}.
              </p>
            </SideBox>
          )}
          {worst && !long && (
            <SideBox title="Worst stretch" aside={`${formatNumber(worstDays, { dp: 0 })} days`}>
              <KvList
                rows={[
                  [
                    'Peak',
                    <span key="p" className="num">
                      {shortDate(worst.peak)}
                    </span>,
                  ],
                  [
                    'Fell',
                    <span key="f" className="num text-loss">
                      {formatPct(worst.depth, { dp: 1 })}
                    </span>,
                  ],
                  [
                    'Back to the peak',
                    <span key="b" className="num">
                      {worst.recovered ? shortDate(worst.recovered) : 'Not by the end'}
                    </span>,
                  ],
                  [
                    'Held then',
                    <span key="h" className="num">
                      {heldThen === null ? '·' : heldThen.length ? heldThen.join(', ') : 'Varied'}
                    </span>,
                  ],
                ]}
              />
            </SideBox>
          )}
          <SideBox
            title={
              long
                ? `Trading over ${formatNumber(yearsBetween(start, end), { dp: 0 })} years`
                : 'Trading'
            }
            aside={
              <button type="button" onClick={onOpenTrades} className="text-accent hover:underline">
                Month by month
              </button>
            }
          >
            <KvList
              rows={[
                [
                  'Closed trades',
                  <span key="c" className="num">
                    {formatNumber(closing, { dp: 0 })}
                  </span>,
                ],
                [
                  'Win rate',
                  <span key="w" className="num">
                    {closing ? formatPct(toNumber(m.winRate), { dp: 1 }) : '·'}
                  </span>,
                ],
                [
                  'Commission',
                  <span key="m" className="num">
                    {formatMoney(toNumber(m.totalCommission))}
                  </span>,
                ],
              ]}
            />
          </SideBox>
          {next && (
            <SideBox title="Next">
              <p className="m-0 text-[12.5px] leading-relaxed text-fg-2">
                {session
                  ? `${version} runs on your Alpaca ${session.mode} account. A range it hasn't been tested on is a useful next check.`
                  : `A range ${version} hasn't been tested on is a useful check before you start it.`}
              </p>
              <button
                type="button"
                className="btn btn-secondary mt-2.5 h-auto whitespace-normal py-1.5 text-left"
                onClick={() => onNext(next)}
              >
                Test on {monthYear(next.start)} to {monthYear(next.end)}
              </button>
            </SideBox>
          )}
          {long && meta.start && startsAtFloor(meta.start) && (
            <SideBox title="Earlier than 2016">
              <p className="m-0 text-[12.5px] leading-relaxed text-fg-2">
                Alpaca&apos;s daily history starts in January 2016, so earlier years can&apos;t be
                tested here.
              </p>
            </SideBox>
          )}
        </div>
      </div>
      {session?.href && (
        <p className="m-0 text-[12px] text-fg-3 lg:hidden">
          <Link to={session.href} className="text-accent hover:underline">
            {openSessionLabel(session)}
          </Link>
        </p>
      )}
      {worst && (
        <span className="sr-only">
          Worst drawdown {formatPct(worst.depth, { dp: 1 })} from {longDate(worst.peak)}
        </span>
      )}
    </div>
  );
}

function SideBox({
  title,
  aside,
  children,
}: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-panel border border-line bg-panel px-3.5 py-3">
      <header className="mb-1.5 flex items-center justify-between gap-2">
        <h2 className="m-0 font-sans text-[13px] font-semibold tracking-normal">{title}</h2>
        {aside && <span className="text-[11.5px] text-fg-3">{aside}</span>}
      </header>
      {children}
    </section>
  );
}

function BackToHigh({
  dates,
  values,
  bench,
  hasBench,
}: {
  dates: readonly Date[];
  values: readonly number[];
  bench: readonly number[] | null;
  hasBench: boolean;
}) {
  const stretch = { id: 'mar-2020', label: 'Mar 2020', start: '2020-02-19', end: '2020-03-23' };
  const run = daysBackToHigh(dates, values, stretch);
  const b = bench ? daysBackToHigh(dates, bench, stretch) : null;
  const fmt = (n: number | null) => (n === null ? 'Not yet' : `${formatNumber(n, { dp: 0 })} days`);
  return (
    <tr className="border-t border-line">
      <td className="py-[7px] text-fg-2">Back to the high after Mar 2020</td>
      <td className="py-[7px] text-right font-mono tabular-nums">{fmt(run)}</td>
      {hasBench && (
        <td className="py-[7px] text-right font-mono tabular-nums text-fg-2">{fmt(b)}</td>
      )}
    </tr>
  );
}
