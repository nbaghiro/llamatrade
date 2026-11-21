import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { useMemo, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { formatMoney, formatNumber, formatPct, moveTone, TONE_TEXT } from '../../lib/format';
import { dayLabel, etToday, type SessionRow } from '../sessions/sessionRows';
import { ModeBadge, Money, Pct, Skeleton } from '../ui';

import { rebase } from './detail/stressPeriods';
import { LineKey } from './LineKey';
import { MiniCurve } from './MiniCurve';
import {
  isLiveRow,
  notRunningAction,
  notRunningState,
  runningFigures,
  sharedRange,
  type NotRunningState,
  type RunningItem,
} from './runningModel';
import { backtestCell, strategySub } from './stageModel';
import { monthYear, runFigures } from './strategyView';
import { useLazyRun } from './useLazyRun';
import { useRunningCompare } from './useRunningCompare';

const pts = (v: number) => `${formatNumber(v, { dp: 1, signed: true })} pts`;

function SectionHead({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="mb-2.5 flex flex-wrap items-center gap-x-4 gap-y-1">
      <h2 className="m-0 text-[14px] font-semibold">{title}</h2>
      {children}
    </div>
  );
}

function Today({ row, suffix }: { row: SessionRow; suffix: boolean }) {
  const { today, todayPct } = row.figures;
  if (today === null) return null;
  const tone = TONE_TEXT[moveTone((todayPct ?? 0) * 100)];
  return (
    <span className={`font-mono text-[12px] ${tone}`}>
      {formatMoney(today, { signed: true })}
      {suffix ? ' today' : ''}
    </span>
  );
}

function Figure({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <span className="block truncate text-[11px] text-fg-3">{label}</span>
      <b className="mt-0.5 block font-mono text-[13.5px] font-semibold">{children}</b>
    </div>
  );
}

function RunningCard({ item, wide }: { item: RunningItem; wide: boolean }) {
  const { strategy, row } = item;
  const { curve, sameRun, same } = useRunningCompare(row);
  const f = runningFigures(row, same);
  const points = useMemo(() => (curve.status === 'ready' ? curve.value : []), [curve]);
  const dates = useMemo(() => points.map((p) => p.at), [points]);
  const values = useMemo(() => points.map((p) => p.value), [points]);
  const mode = isLiveRow(row) ? 'live' : 'paper';
  const href = `/strategies/${strategy.id}`;
  const noBacktest = sameRun === null || (sameRun !== undefined && !same);

  const chart =
    curve.status === 'loading' ? (
      <Skeleton className="w-full" style={{ height: wide ? 132 : 74 }} />
    ) : curve.status === 'error' || points.length < 2 ? (
      <div
        className="grid place-items-center rounded-[8px] border border-dashed border-line text-[12px] text-fg-3"
        style={{ height: wide ? 132 : 74 }}
      >
        {curve.status === 'error'
          ? 'The session’s curve couldn’t be loaded'
          : 'Too new for a curve'}
      </div>
    ) : (
      <MiniCurve
        label={`${strategy.name}: the session’s value${same ? ' and its backtest over the same dates' : ''}`}
        dates={dates}
        values={values}
        dashed={same?.backtestScaled}
        dashedDates={same?.dates}
        height={wide ? 110 : 64}
        axis={wide}
        endDot
      />
    );

  const head = (
    <div className="flex items-center justify-between gap-3">
      <Link
        to={href}
        className="min-w-0 truncate text-[14px] font-semibold after:absolute after:inset-0 hover:text-accent"
      >
        {strategy.name}
      </Link>
      <ModeBadge mode={mode} size="sm" />
    </div>
  );

  const value = (
    <div className="mt-1.5 flex items-baseline justify-between gap-3">
      <span className={`font-mono font-semibold ${wide ? 'text-[22px]' : 'text-[15px]'}`}>
        {row.figures.equity !== null ? <Money value={row.figures.equity} /> : row.view.label}
      </span>
      <Today row={row} suffix={wide} />
    </div>
  );

  if (!wide) {
    return (
      <article className="panel relative grid gap-2 px-4 py-3.5">
        {head}
        {value}
        {chart}
        <div className="flex items-baseline justify-between gap-3 font-mono text-[11.5px]">
          <span className="min-w-0 truncate">
            {f.session !== null && <Pct value={f.session} pnl dp={1} />}
            {f.backtest !== null ? (
              <span className="text-fg-3">
                {' '}
                vs {formatPct(f.backtest, { dp: 1, signed: true })} backtest
              </span>
            ) : noBacktest ? (
              <span className="text-fg-3"> · no backtest over these dates</span>
            ) : null}
          </span>
          {f.gap !== null && <b className="flex-none font-semibold">{pts(f.gap)}</b>}
        </div>
      </article>
    );
  }

  return (
    <article className="panel relative flex min-w-0 flex-col px-4 pb-3.5 pt-4">
      {head}
      {value}
      <div className="mt-3">{chart}</div>
      <div className="mt-3.5 grid grid-cols-3 gap-3 border-t border-line pt-3">
        <Figure label="Session">
          {f.session !== null ? <Pct value={f.session} pnl dp={1} /> : '–'}
        </Figure>
        {f.backtest !== null && f.gap !== null ? (
          <>
            <Figure label="Backtest, same dates">
              {formatPct(f.backtest, { dp: 1, signed: true })}
            </Figure>
            <Figure label="Gap">{pts(f.gap)}</Figure>
          </>
        ) : noBacktest ? (
          <div className="col-span-2 flex min-w-0 items-end justify-between gap-2">
            <span className="text-[11.5px] text-fg-3">No backtest over these dates</span>
            <Link
              to={`/backtest?strategy=${strategy.id}`}
              className="relative z-10 flex-none text-[12px] font-medium text-accent hover:underline"
            >
              Run a backtest
            </Link>
          </div>
        ) : (
          <div className="col-span-2 grid content-end">
            <Skeleton className="h-3 w-32" />
          </div>
        )}
      </div>
    </article>
  );
}

export function RunningSection({ items, wide }: { items: readonly RunningItem[]; wide: boolean }) {
  if (!items.length) return null;
  return (
    <section aria-label="Running" className="mb-7">
      <SectionHead title="Running">
        <LineKey>{wide ? 'Money in the session' : 'Session'}</LineKey>
        <LineKey dashed>
          {wide ? 'Its backtest over the same dates' : 'Backtest, same dates'}
        </LineKey>
      </SectionHead>
      <div className={wide ? 'grid grid-cols-2 gap-4 xl:grid-cols-3' : 'grid gap-3'}>
        {items.map((item) => (
          <RunningCard key={item.row.session.id} item={item} wide={wide} />
        ))}
      </div>
    </section>
  );
}

function stateLabel(s: NotRunningState): ReactNode {
  switch (s.kind) {
    case 'stopped':
      return (
        <span className="inline-flex items-center gap-1.5">
          <i aria-hidden="true" className="block h-[8px] w-[8px] rounded-[2px] bg-fg-3" />
          Stopped
        </span>
      );
    case 'neverRun':
      return 'Never run';
    case 'draft':
      return `Draft v${s.version}`;
    case 'loading':
      return null;
  }
}

function stateSub(s: NotRunningState): string {
  switch (s.kind) {
    case 'stopped':
      return s.at ? `Stopped ${dayLabel(etToday(s.at))}` : 'Stopped';
    case 'neverRun':
      return 'Never run';
    case 'draft':
      return `Draft v${s.version}`;
    case 'loading':
      return '';
  }
}

interface NotRunningProps {
  strategy: Strategy;
  sessions: readonly SessionRow[];
}

function NotRunningCard({ strategy, sessions }: NotRunningProps) {
  const { ref, run } = useLazyRun(strategy.id);
  const cell = backtestCell(strategy, run);
  const state = notRunningState(strategy, cell, sessions);
  const action = notRunningAction(strategy, cell);
  const figs = cell.kind === 'current' || cell.kind === 'stale' ? cell.figures : null;
  const bench = useMemo(
    () =>
      figs && figs.bench.length === figs.equity.length
        ? rebase(figs.bench, figs.equity[0])
        : undefined,
    [figs]
  );

  let right: ReactNode = null;
  if (action?.kind === 'backtest') {
    right = (
      <Link
        to={`/backtest?strategy=${strategy.id}`}
        className="relative z-10 font-sans text-[12px] font-medium text-accent hover:underline"
      >
        Backtest v{action.version}
      </Link>
    );
  } else if (action?.kind === 'first') {
    right = (
      <Link
        to={`/backtest?strategy=${strategy.id}`}
        className="relative z-10 font-sans text-[12px] font-medium text-accent hover:underline"
      >
        Run a backtest
      </Link>
    );
  } else if (state.kind === 'stopped' && state.sessionPct !== null) {
    right = (
      <span>
        {state.live ? 'Live' : 'Paper'} {formatPct(state.sessionPct, { dp: 1, signed: true })}
      </span>
    );
  } else if (figs) {
    right = <span>Sharpe {figs.sharpe.toFixed(2)}</span>;
  }

  return (
    <article ref={ref} className="panel relative flex min-w-0 flex-col px-4 pb-3 pt-3.5">
      <div className="flex items-center justify-between gap-3">
        <Link
          to={`/strategies/${strategy.id}`}
          className="min-w-0 truncate text-[13.5px] font-semibold after:absolute after:inset-0 hover:text-accent"
        >
          {strategy.name}
        </Link>
        <span className="flex-none text-[11.5px] text-fg-3">{stateLabel(state)}</span>
      </div>
      <div className="mt-2.5 flex-1">
        {cell.kind === 'loading' ? (
          <Skeleton className="h-[52px] w-full" />
        ) : figs ? (
          <MiniCurve
            label={`${strategy.name}: latest backtest against its benchmark`}
            dates={figs.dates}
            values={figs.equity}
            dashed={bench}
            height={52}
            tone="muted"
          />
        ) : (
          <div className="grid h-[52px] place-items-center rounded-[8px] border border-dashed border-line-strong text-[11.5px] text-fg-3">
            Not backtested yet
          </div>
        )}
      </div>
      <div className="mt-2.5 flex items-baseline justify-between gap-3 font-mono text-[11.5px] text-fg-2">
        <span className="min-w-0 truncate">
          {figs && cell.kind === 'current' && (
            <>
              <Pct value={figs.totalReturn} pnl dp={1} /> DD{' '}
              {formatPct(figs.maxDrawdown, { dp: 1 })}
            </>
          )}
          {figs && cell.kind === 'stale' && (
            <>
              {formatPct(figs.totalReturn, { dp: 1, signed: true })} for v{cell.version}
            </>
          )}
          {!figs && cell.kind === 'none' && (
            <span className="font-sans text-fg-3">{strategySub(strategy) || 'No rules yet'}</span>
          )}
        </span>
        <span className="flex-none">{right}</span>
      </div>
    </article>
  );
}

function NotRunningPhoneRow({ strategy, sessions }: NotRunningProps) {
  const { ref, run } = useLazyRun(strategy.id);
  const cell = backtestCell(strategy, run);
  const state = notRunningState(strategy, cell, sessions);
  return (
    <div
      ref={ref}
      className="relative flex items-center justify-between gap-3 border-t border-line px-4 py-3 first:border-t-0"
    >
      <div className="min-w-0">
        <Link
          to={`/strategies/${strategy.id}`}
          className="block truncate text-[14px] font-medium after:absolute after:inset-0"
        >
          {strategy.name}
        </Link>
        <span className="block text-[11.5px] text-fg-3">
          {stateSub(state) || strategySub(strategy)}
        </span>
      </div>
      <span className="flex-none font-mono text-[12.5px]">
        {cell.kind === 'loading' ? (
          <Skeleton className="h-3 w-12" />
        ) : cell.kind === 'current' ? (
          <Pct value={cell.figures.totalReturn} pnl dp={1} />
        ) : cell.kind === 'stale' ? (
          <span className="text-fg-3">
            {formatPct(cell.figures.totalReturn, { dp: 1, signed: true })}
          </span>
        ) : (
          <span className="font-sans text-[11.5px] text-fg-3">Not backtested</span>
        )}
      </span>
    </div>
  );
}

export function NotRunningSection({
  strategies,
  sessions,
  wide,
}: {
  strategies: readonly Strategy[];
  sessions: readonly SessionRow[];
  wide: boolean;
}) {
  const runs = useStrategiesStore((s) => s.runs);
  const range = useMemo(
    () => sharedRange(strategies.map((s) => runFigures(runs[s.id] ?? null))),
    [strategies, runs]
  );
  if (!strategies.length) return null;
  if (!wide) {
    return (
      <section aria-label="Not running">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="m-0 text-[14px] font-semibold">Not running</h2>
          <span className="text-[11.5px] text-fg-3">Backtest</span>
        </div>
        <div className="panel">
          {strategies.map((s) => (
            <NotRunningPhoneRow key={s.id} strategy={s} sessions={sessions} />
          ))}
        </div>
      </section>
    );
  }
  const sym = range?.benchmarkSymbol || 'SPY';
  return (
    <section aria-label="Not running">
      <SectionHead title="Not running">
        <LineKey muted>
          {range
            ? `Latest backtest, ${monthYear(range.start)} to ${monthYear(range.end)}`
            : 'Latest backtest of each'}
        </LineKey>
        <LineKey dashed>
          {range && range.benchmarkReturn !== null
            ? `${sym}, ${formatPct(range.benchmarkReturn, { dp: 1, signed: true })}`
            : `${sym} over the same dates`}
        </LineKey>
      </SectionHead>
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {strategies.map((s) => (
          <NotRunningCard key={s.id} strategy={s} sessions={sessions} />
        ))}
      </div>
    </section>
  );
}
