import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toDate, toNumber, useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { ArrowUpRight } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { toCurve, toTradeInputs } from '../../components/backtest/runData';
import { AnnotatedCurve, type CurveLane } from '../../components/charts';
import {
  LoadingLabel,
  PanelError,
  Pct,
  SkeletonChart,
  SkeletonFigure,
  StatList,
} from '../../components/ui';
import { groupRebalances, tradesToOrders, type TradeInput } from '../../lib/backtestView';
import { formatMoney, formatPct } from '../../lib/format';
import { getStrategy } from '../../services/strategy';

import {
  dropComparison,
  heldPeriods,
  heldSets,
  switchesOf,
  symbolsLabel,
  worstDrop,
} from './firstResult';
import { OnboardingLayout, StepTitle } from './OnboardingLayout';
import { useBacktestRun } from './useBacktestRun';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const day = (d: Date | null) =>
  d ? `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}` : '';
const shortDay = (d: Date, withYear: boolean) =>
  `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}${withYear ? `, ${d.getUTCFullYear()}` : ''}`;

function useRunTrades(run: BacktestRun): TradeInput[] | null {
  const fullTrades = useBacktestStore((s) => s.fullTrades);
  const tradesLoading = useBacktestStore((s) => s.tradesLoading);
  const loadAllTrades = useBacktestStore((s) => s.loadAllTrades);
  const loadedFor = useRef('');
  const inline = useMemo(() => run.results?.trades ?? [], [run.results]);

  useEffect(() => {
    if (inline.length > 0 || loadedFor.current === run.id) return;
    loadedFor.current = run.id;
    loadAllTrades(run.id).catch(() => undefined);
  }, [run.id, inline.length, loadAllTrades]);

  return useMemo(() => {
    if (inline.length > 0) return toTradeInputs(inline);
    if (loadedFor.current !== run.id || tradesLoading || !fullTrades) return null;
    return toTradeInputs(fullTrades);
  }, [inline, fullTrades, tradesLoading, run.id]);
}

/** One finished run as Home's annotated curve: switches as pins, holdings and trades as lanes. */
function RunSummary({ run, name }: { run: BacktestRun; name: string }) {
  const results = run.results;
  const m = results?.metrics;
  const bench = results?.benchmarkSymbol || run.config?.benchmarkSymbol || '';
  const trades = useRunTrades(run);
  const curve = useMemo(() => toCurve(results?.equityCurve), [results]);
  const benchValues = useMemo(() => {
    const b = toCurve(results?.benchmarkEquityCurve);
    return b.values.length === curve.values.length ? b.values : undefined;
  }, [results, curve.values.length]);

  const end = useMemo(() => curve.dates[curve.dates.length - 1] ?? new Date(), [curve.dates]);
  const periods = useMemo(() => (trades ? heldPeriods(trades, end) : []), [trades, end]);
  const switches = switchesOf(periods);
  const sets = heldSets(periods).slice(0, 3);
  const drop = worstDrop(curve.dates, curve.values);
  const rebalances = useMemo(
    () => (trades ? groupRebalances(tradesToOrders(trades)) : []),
    [trades]
  );
  const benchDrop = dropComparison(bench, benchValues, drop?.depth ?? null, name);
  const switchDays = new Set(switches.map((s) => s.from.toISOString().slice(0, 10)));

  const start = toNumber(run.config?.initialCapital);
  const final = curve.values[curve.values.length - 1] ?? 0;
  const total = toNumber(m?.totalReturn);
  const benchTotal = toNumber(m?.benchmarkReturn);
  const mdd = -Math.abs(toNumber(m?.maxDrawdown));

  const pins = switches.slice(0, 6).map((p, i) => ({
    at: p.from,
    label: `${shortDay(p.from, i === 0 || p.from.getUTCFullYear() !== switches[i - 1].from.getUTCFullYear())} · to ${symbolsLabel(p.symbols)}`,
    tone: (i % 2 === 0 ? 'accent' : 'neutral') as 'accent' | 'neutral',
    row: (i % 2) as 0 | 1,
  }));

  const lanes: CurveLane[] = [
    ...sets.map((set) => ({
      id: `held-${set.key}`,
      label: <span title={set.key}>Held {symbolsLabel(set.key.split(' · '), 2)}</span>,
      spans: periods
        .filter((p) => p.key === set.key)
        .map((p) => ({ from: p.from, to: p.to, style: 'bar' as const })),
    })),
    {
      id: 'trades',
      label: 'Trades',
      value: <span className="num">{m?.totalTrades ?? rebalances.length}</span>,
      spans: [{ from: curve.dates[0] ?? end, to: end, style: 'off' as const }],
      events: rebalances.map((r) => {
        const switched = switchDays.has(r.date);
        return {
          at: new Date(`${r.date}T00:00:00Z`),
          shape: switched ? ('dot' as const) : ('ring' as const),
          tone: switched ? ('accent' as const) : ('muted' as const),
          title: `${r.date}: ${r.orders.length} order${r.orders.length === 1 ? '' : 's'}`,
        };
      }),
    },
  ];

  return (
    <section className="panel-rim grid w-full max-w-[1080px] grid-cols-[minmax(0,1fr)] gap-4 p-4 md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-[560px]">
          <span className="text-[11px] font-medium text-fg-3">Your first backtest</span>
          <h2 className="m-0 mt-1 text-[20px] font-semibold tracking-[-0.015em]">{name}</h2>
          <div className="mt-[3px] text-[12px] text-fg-3">
            {day(toDate(run.config?.startDate))} to {day(toDate(run.config?.endDate))} ·{' '}
            {formatMoney(start, { dp: 0 })}
            {bench && ` · benchmark ${bench}`}
          </div>
          {m && start > 0 && final > 0 && (
            <p className="m-0 mt-3 text-[14px] text-fg-2">
              {formatMoney(start, { dp: 0 })} would have become{' '}
              <b className="num text-fg">{formatMoney(final, { dp: 0 })}</b>, a{' '}
              <Pct value={total} pnl dp={1} /> return.
              {bench && (
                <>
                  {' '}
                  {bench} returned <Pct value={benchTotal} signed dp={1} /> over the same dates.
                </>
              )}
              {benchDrop && ` ${benchDrop}`}
              {switches.length > 0 &&
                ` It switched holdings ${switches.length === 1 ? 'once' : switches.length === 2 ? 'twice' : `${switches.length} times`}, marked on the curve.`}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            to={`/strategies/${encodeURIComponent(run.strategyId)}/edit`}
            className="btn btn-secondary"
          >
            Change the rules
          </Link>
          <Link to={`/backtest/${encodeURIComponent(run.id)}`} className="btn btn-secondary">
            Open full results
            <ArrowUpRight aria-hidden="true" className="h-4 w-4" />
          </Link>
        </div>
      </div>
      {curve.values.length > 1 && (
        <AnnotatedCurve
          label={`Equity of ${name}${benchValues ? ` against ${bench}` : ''}`}
          dates={curve.dates}
          values={curve.values}
          benchmark={benchValues}
          pins={pins}
          bands={drop ? [{ from: drop.from, to: drop.to, tone: 'loss', through: true }] : []}
          lanes={trades ? lanes : []}
          height={230}
          side={
            m && (
              <StatList
                items={[
                  {
                    label: 'CAGR',
                    value: formatPct(toNumber(m.annualizedReturn)),
                  },
                  { label: 'Sharpe', value: toNumber(m.sharpeRatio).toFixed(2) },
                  { label: 'Max drawdown', value: formatPct(mdd) },
                  { label: 'Trades', value: String(m.totalTrades) },
                ]}
              />
            )
          }
          legend={[
            { shape: 'dot', label: 'Switch between holdings' },
            { shape: 'ring', label: 'Rebalance', tone: 'muted' },
          ]}
        />
      )}
      <p className="m-0 text-[11.5px] text-fg-3">
        {drop &&
          `The shaded stretch is the worst drop, ${shortDay(drop.from, true)} to ${shortDay(drop.to, true)}. `}
        Backtests use past prices and assume fills at the close. Real results will differ.
      </p>
    </section>
  );
}

function NextStep({ strategyId }: { strategyId: string }) {
  const credentials = useBrokerStore((s) => s.credentials);
  const loaded = useBrokerStore((s) => s.loaded);
  const fetchCredentials = useBrokerStore((s) => s.fetch);
  useEffect(() => {
    fetchCredentials().catch(() => undefined);
  }, [fetchCredentials]);
  const connected = credentials.some((c) => c.isPaper && c.isActive);

  return (
    <div className="grid w-full max-w-[880px] gap-3 rounded-panel border border-line bg-panel p-4 md:flex md:items-center md:justify-between md:p-5">
      <div>
        <b className="block text-[14px] font-semibold">Run it on paper next</b>
        <span className="text-[12.5px] text-fg-2">
          {connected
            ? 'Your Alpaca paper account is connected, so you can start this strategy in a paper session.'
            : 'A paper session places orders in your own Alpaca paper account. Connect it whenever you are ready.'}
        </span>
      </div>
      <div className="flex flex-col gap-2.5 md:flex-row">
        <Link to="/dashboard" className="btn btn-secondary btn-lg">
          Go to Home
        </Link>
        {loaded &&
          (connected ? (
            <Link
              to={`/strategies/${encodeURIComponent(strategyId)}/session`}
              className="btn btn-primary btn-lg"
            >
              Start on paper
            </Link>
          ) : (
            <Link to="/connect/alpaca?next=/dashboard" className="btn btn-primary btn-lg">
              Connect Alpaca
            </Link>
          ))}
      </div>
    </div>
  );
}

/** /welcome/result/:runId: the template's backtest, read only, before any broker ask. */
export default function WelcomeResultPage() {
  const { runId = '' } = useParams();
  const { run, error, retry } = useBacktestRun(runId);
  const [name, setName] = useState('');

  const strategyId = run?.strategyId ?? '';
  useEffect(() => {
    if (!strategyId) return;
    let live = true;
    getStrategy(strategyId)
      .then((r) => {
        if (live) setName(r.strategy?.name ?? '');
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [strategyId]);

  const title = name || 'Your strategy';
  let body;
  if (error && !run) {
    body = (
      <div className="w-full max-w-[880px] rounded-panel border border-line bg-panel">
        <PanelError title="The backtest couldn't be loaded" cause={error} onRetry={retry} />
      </div>
    );
  } else if (
    !run ||
    run.status === BacktestStatus.PENDING ||
    run.status === BacktestStatus.RUNNING
  ) {
    const pct = run?.progressPercent ?? 0;
    body = (
      <section className="grid w-full max-w-[880px] grid-cols-[minmax(0,1fr)] gap-4 rounded-panel border border-line bg-panel p-4 md:p-6">
        <LoadingLabel>Backtest running</LoadingLabel>
        <div className="flex items-center justify-between gap-3 text-[12.5px]">
          <span className="text-fg-2">
            {run?.currentDate ? `Replaying ${run.currentDate}` : 'Starting the backtest'}
          </span>
          <span className="num text-fg-3">{Math.round(pct)}%</span>
        </div>
        <div className="h-1 overflow-hidden rounded-[2px] bg-sunk" aria-hidden="true">
          <div
            className="h-full bg-accent transition-[width]"
            style={{ width: `${Math.max(2, pct)}%` }}
          />
        </div>
        <SkeletonFigure />
        <SkeletonChart height={240} />
      </section>
    );
  } else if (run.status !== BacktestStatus.COMPLETED) {
    body = (
      <div className="w-full max-w-[880px] rounded-panel border border-line bg-panel">
        <PanelError
          title={
            run.status === BacktestStatus.CANCELLED
              ? 'The backtest was cancelled'
              : "The backtest didn't finish"
          }
          cause={run.statusMessage || undefined}
          unaffected="The strategy is saved, so you can open it and try again."
        />
        <div className="flex justify-center gap-2.5 pb-6">
          <Link to="/welcome" className="btn btn-secondary">
            Try another template
          </Link>
          <Link
            to={`/strategies/${encodeURIComponent(run.strategyId)}`}
            className="btn btn-primary"
          >
            Open the strategy
          </Link>
        </div>
      </div>
    );
  } else {
    body = (
      <>
        <RunSummary run={run} name={title} />
        <NextStep strategyId={run.strategyId} />
      </>
    );
  }

  return (
    <OnboardingLayout step={3}>
      <StepTitle
        title="See how it would have done"
        lead="This is the real result from the backtest engine. It's saved with your strategy."
      />
      {body}
    </OnboardingLayout>
  );
}
