import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toDate, toNumber } from '@llamatrade/core/stores/backtest';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { ArrowUpRight } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { LineChart } from '../../components/charts';
import {
  LoadingLabel,
  Num,
  PanelError,
  Pct,
  SkeletonChart,
  SkeletonFigure,
} from '../../components/ui';
import { formatMoney } from '../../lib/format';
import { getStrategy } from '../../services/strategy';

import { OnboardingLayout, StepTitle } from './OnboardingLayout';
import { useBacktestRun } from './useBacktestRun';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const day = (d: Date | null) =>
  d ? `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}` : '';

function Figure({
  label,
  value,
  sub,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
}) {
  return (
    <div className="grid gap-0.5 py-2.5 text-[11.5px] [&+&]:border-l [&+&]:border-line [&+&]:pl-3.5">
      <span className="text-[11px] font-medium text-fg-3">{label}</span>
      <div className="text-[22px] leading-tight tracking-[-0.02em]">{value}</div>
      {sub && <span className="num text-fg-3">{sub}</span>}
    </div>
  );
}

/** A read-only summary of one finished run: the figures and the equity line against its benchmark. */
function RunSummary({ run, name }: { run: BacktestRun; name: string }) {
  const results = run.results;
  const m = results?.metrics;
  const bench = results?.benchmarkSymbol || run.config?.benchmarkSymbol || '';
  const series = useMemo(() => {
    const pts = results?.equityCurve ?? [];
    const dates = pts.map((p) => toDate(p.timestamp) ?? new Date(0));
    const main = pts.map((p) => toNumber(p.equity));
    const benchPts = results?.benchmarkEquityCurve ?? [];
    const benchVals =
      benchPts.length === pts.length ? benchPts.map((p) => toNumber(p.equity)) : null;
    return { dates, main, benchVals };
  }, [results]);

  return (
    <section className="grid w-full max-w-[880px] grid-cols-[minmax(0,1fr)] gap-[18px] rounded-panel border border-line bg-panel p-4 md:p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <span className="text-[11px] font-medium text-fg-3">Backtest result</span>
          <h2 className="m-0 mt-1 text-[20px] font-semibold tracking-[-0.015em]">{name}</h2>
          <div className="mt-[3px] text-[12px] text-fg-3">
            {day(toDate(run.config?.startDate))} to {day(toDate(run.config?.endDate))} ·{' '}
            {formatMoney(toNumber(run.config?.initialCapital), { dp: 0 })}
            {bench && ` · benchmark ${bench}`}
          </div>
        </div>
        <Link to={`/backtest/${encodeURIComponent(run.id)}`} className="btn btn-secondary">
          Open full results
          <ArrowUpRight aria-hidden="true" className="h-4 w-4" />
        </Link>
      </div>
      {m && (
        <div className="grid grid-cols-3 border-y border-line">
          <Figure
            label="Total return"
            value={<Pct value={toNumber(m.totalReturn)} pnl dp={1} />}
            sub={
              bench && (
                <>
                  {bench} <Pct value={toNumber(m.benchmarkReturn)} signed dp={1} />
                </>
              )
            }
          />
          <Figure label="Sharpe" value={<Num value={toNumber(m.sharpeRatio)} />} />
          <Figure
            label="Max drawdown"
            value={<Pct value={-Math.abs(toNumber(m.maxDrawdown))} pnl dp={1} />}
          />
        </div>
      )}
      {series.main.length > 1 && (
        <LineChart
          label={`Equity of ${name}${series.benchVals ? ` against ${bench}` : ''}`}
          dates={series.dates}
          series={[
            { values: series.main, kind: 'main', area: true },
            ...(series.benchVals ? [{ values: series.benchVals, kind: 'bench' as const }] : []),
          ]}
          height={240}
          yFormat={(v) => `${Math.round(v / 1000)}k`}
        />
      )}
      <p className="m-0 text-[11.5px] text-fg-3">
        A backtest replays history with the same engine that runs paper sessions. Past results
        don&apos;t predict future returns.
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
            ? 'Your Alpaca paper account is connected, so you can deploy this strategy to a paper session.'
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
              Deploy to paper
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
