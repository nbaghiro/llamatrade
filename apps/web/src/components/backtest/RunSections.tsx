import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { toNumber } from '@llamatrade/core/stores/backtest';
import { DSL_INDICATORS, DSL_METRICS } from '@llamatrade/core/strategy/vocabulary';
import { AlertTriangle } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import {
  figuresFromCurve,
  longDate,
  monthlyReturnsFromMap,
  namesUsed,
  recoveryDays,
  type RunPhase,
} from '../../lib/backtestView';
import { formatMoney, formatNumber, formatPct } from '../../lib/format';
import { MonthlyGrid } from '../charts';
import { Pct } from '../ui/Num';

import { KvList, Panel } from './parts';
import { runMeta, toCurve } from './runData';
import { RunProgressFrame } from './RunProgressFrame';

/** In place of the result column: what stopped the run, how far it got and how to run it again. */
export function RunFailure({
  phase,
  message,
  strategyId,
  onBack,
  run,
}: {
  phase: Extract<RunPhase, 'failed' | 'cancelled'>;
  message: string;
  strategyId: string;
  onBack: () => void;
  /** The stored run, for how far it got before it stopped. */
  run?: BacktestRun | null;
}) {
  const cancelled = phase === 'cancelled';
  const meta = runMeta(run ?? null);
  const through = run?.currentDate ? new Date(`${run.currentDate}T00:00:00Z`) : null;
  const reason = message.trim();
  const [copied, setCopied] = useState(false);

  if (!run || !meta.start || !meta.end) {
    return (
      <div className="grid min-h-[420px] content-center justify-items-center px-6 py-16 text-center">
        <span
          className={`mb-4 grid h-[52px] w-[52px] place-items-center rounded-full border border-dashed ${
            cancelled ? 'border-line-strong text-fg-3' : 'border-risk-line text-risk'
          }`}
        >
          <AlertTriangle className="h-5 w-5" aria-hidden="true" />
        </span>
        <h2 className="m-0 mb-1.5 font-sans text-base font-semibold tracking-normal">
          {cancelled ? 'This run was cancelled' : "This run couldn't finish"}
        </h2>
        <p className="m-0 mb-4 max-w-[460px] text-[13px] text-fg-2">
          {cancelled
            ? 'Nothing was saved from it. Change the setup if you like and run it again.'
            : reason ||
              'The engine stopped without a reason. Open the strategy to check it, then run it again.'}
        </p>
        {!cancelled && reason && (
          <p className="m-0 mb-4 max-w-[460px] text-[12px] text-fg-3">
            The editor validates the strategy again and marks the line that needs a change.
          </p>
        )}
        <div className="flex flex-wrap justify-center gap-2">
          {!cancelled && strategyId && (
            <Link to={`/strategies/${strategyId}/edit`} className="btn btn-primary">
              Open in the editor
            </Link>
          )}
          <button type="button" onClick={onBack} className="btn btn-secondary">
            Back to setup
          </button>
        </div>
      </div>
    );
  }

  const where = through
    ? `on ${longDate(through)}`
    : `at ${formatNumber(run.progressPercent, { dp: 0 })}%`;
  const copy = () => {
    const text = [`Backtest ${run.id}`, `Stopped ${where}`, reason].filter(Boolean).join('\n');
    navigator.clipboard
      ?.writeText(text)
      .then(() => setCopied(true))
      .catch(() => setCopied(false));
  };
  const steps: { title: string; body: string; action: ReactNode }[] = [
    ...(!cancelled && strategyId
      ? [
          {
            title: 'Change the strategy',
            body: 'The editor validates it again and marks the line that needs a change.',
            action: (
              <Link to={`/strategies/${strategyId}/edit`} className="btn btn-secondary">
                Open in the editor
              </Link>
            ),
          },
        ]
      : []),
    {
      title: 'Run it again',
      body: 'Runs start from the beginning, with the same settings unless you change them.',
      action: (
        <Link to={`/backtest?rerun=${run.id}`} className="btn btn-secondary">
          {cancelled ? 'Run again' : 'Edit settings'}
        </Link>
      ),
    },
  ];

  return (
    <div className="grid content-start gap-3.5 p-3.5">
      <p
        className={`m-0 flex gap-2 rounded-[6px] border px-3 py-2.5 text-[12.5px] ${
          cancelled ? 'border-line bg-sunk text-fg-2' : 'border-risk-line bg-risk-soft text-fg'
        }`}
      >
        <AlertTriangle
          className={`mt-0.5 h-3.5 w-3.5 flex-none ${cancelled ? 'text-fg-3' : 'text-risk'}`}
          aria-hidden="true"
        />
        <span>
          <b className="font-semibold">
            {cancelled ? `The run was cancelled ${where}.` : `The run stopped ${where}.`}
          </b>{' '}
          {cancelled
            ? 'Nothing was saved from it.'
            : reason || 'The engine stopped without giving a reason.'}
        </span>
      </p>
      <RunProgressFrame
        start={meta.start}
        end={meta.end}
        through={through}
        tone="stopped"
        marker={through ? `${cancelled ? 'Cancelled' : 'Stopped'} ${longDate(through)}` : undefined}
        doneNote="The service doesn't keep the curve of a run that stopped."
        aheadNote={`Not simulated. A new run starts again from ${longDate(meta.start)}.`}
      />
      <div className="grid gap-3.5 lg:grid-cols-2">
        <section>
          <h2 className="m-0 mb-1.5 font-sans text-[13px] font-semibold tracking-normal">
            Ways to run it again
          </h2>
          <ol className="m-0 list-none p-0">
            {steps.map((st, i) => (
              <li
                key={st.title}
                className="flex items-start gap-3 border-b border-line py-2.5 last:border-b-0"
              >
                <span className="grid h-5 w-5 flex-none place-items-center rounded-full border border-line-strong font-mono text-[10.5px] text-fg-2">
                  {i + 1}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[12.5px] font-medium">{st.title}</span>
                  <span className="block text-[12px] text-fg-3">{st.body}</span>
                </span>
                {st.action}
              </li>
            ))}
          </ol>
        </section>
        <section>
          <h2 className="m-0 mb-1.5 font-sans text-[13px] font-semibold tracking-normal">
            From the backtest service
          </h2>
          <pre className="m-0 whitespace-pre-wrap break-words rounded-[6px] bg-sunk px-3 py-2.5 font-mono text-[11.5px] text-fg-2">
            {reason || 'No message was recorded.'}
          </pre>
          <button
            type="button"
            onClick={copy}
            className="mt-2 text-[12px] text-accent hover:underline"
          >
            {copied ? 'Copied' : 'Copy details for support'}
          </button>
        </section>
      </div>
    </div>
  );
}

/** One sentence that reads the result against the benchmark. */
export function RunSummary({ run, strategyName }: { run: BacktestRun; strategyName: string }) {
  const m = run.results?.metrics;
  if (!m) return null;
  const meta = runMeta(run);
  const total = toNumber(m.totalReturn);
  const benchCurve = toCurve(run.results?.benchmarkEquityCurve);
  const benchFig = figuresFromCurve(benchCurve.values);
  const bench = meta.benchmark;
  const benchTotal = bench ? toNumber(m.benchmarkReturn) : null;
  const years =
    meta.start && meta.end ? (meta.end.getTime() - meta.start.getTime()) / (365.25 * 864e5) : null;
  const span =
    years === null
      ? ''
      : years >= 1.5
        ? ` over ${formatNumber(years, { dp: 0 })} years`
        : ` over ${formatNumber(years * 12, { dp: 0 })} months`;
  const gap = benchTotal === null ? null : (total - benchTotal) * 100;
  const recovery = recoveryDays(toCurve(run.results?.equityCurve).values);
  const mdd = -Math.abs(toNumber(m.maxDrawdown));

  return (
    <p className="m-0 max-w-[980px] text-[13.5px] text-fg-2">
      {strategyName} returned <Pct value={total} pnl dp={1} />
      {span}
      {gap !== null && (
        <>
          , <span className="num text-fg">{formatNumber(Math.abs(gap), { dp: 1 })}</span> points{' '}
          {gap >= 0 ? 'ahead of' : 'behind'} {bench}
        </>
      )}
      . Its largest drawdown was <Pct value={mdd} pnl dp={1} />
      {benchFig && bench && (
        <>
          {' '}
          against {bench}&apos;s <Pct value={benchFig.maxDrawdown} pnl dp={1} />
        </>
      )}
      {recovery === null ? (
        ", and it hadn't recovered by the end of the run."
      ) : recovery === 0 ? (
        '.'
      ) : (
        <>
          , and it was back at its previous high <span className="num text-fg">{recovery}</span>{' '}
          trading days after the low.
        </>
      )}
    </p>
  );
}

/** Monthly returns, the trade summary and the indicators the run used. */
export function RunSections({
  run,
  dsl,
  onOpenTrades,
}: {
  run: BacktestRun;
  /** Source of the version that ran; null while loading or when unavailable. */
  dsl: string | null | undefined;
  onOpenTrades: () => void;
}) {
  const m = run.results?.metrics;
  const months = monthlyReturnsFromMap(run.results?.monthlyReturns ?? {});
  const closing = (m?.winningTrades ?? 0) + (m?.losingTrades ?? 0);
  const indicators = dsl ? namesUsed(dsl, DSL_INDICATORS) : [];
  const metricNames = dsl ? namesUsed(dsl, DSL_METRICS) : [];

  return (
    <div className="grid gap-3.5 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,0.85fr)_minmax(0,1fr)]">
      <Panel title="Monthly returns, %" aside="year compounds months">
        <div className="px-3.5 py-3">
          {months.length ? (
            <MonthlyGrid months={months} />
          ) : (
            <p className="m-0 text-[12.5px] text-fg-3">This run has no monthly returns.</p>
          )}
        </div>
      </Panel>
      <Panel
        title="Trades"
        aside={
          <button type="button" onClick={onOpenTrades} className="text-accent hover:underline">
            Month by month
          </button>
        }
      >
        <div className="px-3.5 py-1">
          <KvList
            rows={[
              ['Simulated trades', formatNumber(m?.totalTrades ?? 0, { dp: 0 })],
              [
                'Win rate',
                closing
                  ? `${formatPct(toNumber(m?.winRate), { dp: 0 })} of ${closing} closing trades`
                  : '·',
              ],
              ['Profit factor', closing ? formatNumber(toNumber(m?.profitFactor), { dp: 2 }) : '·'],
              [
                'Average hold',
                closing
                  ? `${formatNumber(toNumber(m?.averageHoldingPeriodDays), { dp: 0 })} days`
                  : '·',
              ],
              [
                'Commission',
                <span key="c" className="num">
                  {formatMoney(-toNumber(m?.totalCommission))}
                </span>,
              ],
            ]}
          />
        </div>
      </Panel>
      <Panel
        title="Indicators this run used"
        aside={dsl ? `${indicators.length} of ${DSL_INDICATORS.length}` : undefined}
      >
        <div className="px-3.5 py-3">
          {dsl === undefined ? (
            <p className="m-0 text-[12.5px] text-fg-3">Reading the strategy…</p>
          ) : dsl === null ? (
            <p className="m-0 text-[12.5px] text-fg-3">
              The source for this version couldn&apos;t be loaded.
            </p>
          ) : (
            <ul className="m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(76px,1fr))] gap-[5px] p-0">
              {DSL_INDICATORS.map((x) => (
                <li
                  key={x}
                  className={`rounded px-1 py-1.5 text-center font-mono text-[11px] font-medium ${
                    indicators.includes(x) ? 'bg-accent-fill text-accent-ink' : 'bg-sunk text-fg-3'
                  }`}
                >
                  {x}
                </li>
              ))}
              {DSL_METRICS.map((x) => (
                <li
                  key={x}
                  className={`rounded px-1 py-1.5 text-center font-mono text-[11px] font-medium ring-1 ring-inset ${
                    metricNames.includes(x)
                      ? 'bg-accent-fill text-accent-ink ring-transparent'
                      : 'text-fg-3 ring-line-strong'
                  }`}
                >
                  {x}
                </li>
              ))}
            </ul>
          )}
        </div>
      </Panel>
    </div>
  );
}
