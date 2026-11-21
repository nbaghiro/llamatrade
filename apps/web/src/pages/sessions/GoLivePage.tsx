import { toDate, toNumber, useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useDeployStore } from '@llamatrade/core/stores/deploy';
import { readLiveAccount, type LiveAccount } from '@llamatrade/core/stores/funding';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { ArrowRight, Lock } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { Panel } from '../../components/backtest/parts';
import { AnnotatedCurve } from '../../components/charts';
import { buildSessionRow, etToday } from '../../components/sessions';
import { dayLabel } from '../../components/sessions/sessionRows';
import {
  asOf,
  curveStats,
  etDayLabel,
  etHm,
  fillDays,
  isFilled,
  nextRebalances,
  sharesFor,
  toSeries,
  windowed,
} from '../../components/sessions/timeline';
import { ModeBadge, PageHead } from '../../components/ui';
import { Money, Pct } from '../../components/ui/Num';
import { PanelError } from '../../components/ui/PanelError';
import { SkeletonChart } from '../../components/ui/Skeleton';
import { formatMoney, formatNumber, formatPct } from '../../lib/format';
import { alpacaAccountLabel } from '../../lib/scope';
import { DEFAULT_RISK_LIMITS } from '../../lib/sessionState';

const DAY_MS = 86_400_000;

type LiveState =
  | { kind: 'loading' }
  | { kind: 'none' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; account: LiveAccount };

/** /trading/:sessionId/live: the paper record, then one confirmation that starts a live session (golive2 A). */
export default function GoLivePage() {
  const { sessionId = '' } = useParams();
  const navigate = useNavigate();
  const detail = useTradingStore((s) => (s.detail?.session.id === sessionId ? s.detail : null));
  const detailError = useTradingStore((s) => s.detailError);
  const detailLoading = useTradingStore((s) => s.detailLoading);
  const loadSession = useTradingStore((s) => s.loadSession);
  const runCommand = useTradingStore((s) => s.runCommand);
  const performance = useTradingStore((s) => s.performance);
  const strategies = useBacktestStore((s) => s.strategies);
  const fetchStrategies = useBacktestStore((s) => s.fetchStrategies);
  const deploy = useDeployStore((s) => s.deploy);
  const deploying = useDeployStore((s) => s.deploying);
  const deployError = useDeployStore((s) => s.error);
  const clearError = useDeployStore((s) => s.clearError);
  const [live, setLive] = useState<LiveState>({ kind: 'loading' });
  const [draft, setDraft] = useState('');
  const [keepPaper, setKeepPaper] = useState(true);
  const [agreed, setAgreed] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  useEffect(() => {
    clearError();
    loadSession(sessionId, new Date(0)).catch(() => undefined);
    fetchStrategies().catch(() => undefined);
    let cancelled = false;
    readLiveAccount()
      .then((account) => {
        if (cancelled) return;
        setLive(account ? { kind: 'ready', account } : { kind: 'none' });
        if (account && account.unallocatedCash > 0) {
          setDraft(String(Math.floor(Math.min(account.unallocatedCash, 10000))));
        }
      })
      .catch(() => {
        if (!cancelled) setLive({ kind: 'error', message: 'Your live account could not be read.' });
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, loadSession, fetchStrategies, clearError]);

  const row = useMemo(
    () =>
      detail
        ? buildSessionRow(detail.session, {
            executions: detail.execution ? [detail.execution] : [],
            sleeves: detail.sleeve ? [detail.sleeve] : [],
            performance: detail.performance ? [detail.performance] : performance,
            strategies,
            orders: detail.orders,
          })
        : null,
    [detail, performance, strategies]
  );

  if (detailError && !detail) {
    return (
      <div className="page">
        <PageHead crumbs={[{ label: 'Sessions', to: '/trading' }]} title="Run on live" />
        <Panel>
          <PanelError
            title="This session couldn't be loaded"
            cause={detailError}
            onRetry={() => loadSession(sessionId, new Date(0))}
            retrying={detailLoading}
          />
        </Panel>
      </div>
    );
  }
  if (!detail || !row) {
    return (
      <div className="page" aria-busy="true">
        <SkeletonChart height={300} />
      </div>
    );
  }

  const { session, execution, positions, orders } = detail;
  const now = new Date();
  const started = toDate(session.startedAt);
  const f = row.figures;
  const series = windowed(
    toSeries(detail.curve),
    started ?? new Date(now.getTime() - 30 * DAY_MS),
    now,
    f.equity
  );
  const stats = curveStats(series.values);
  const bench = detail.benchmark.length ? asOf(toSeries(detail.benchmark), series.dates) : [];
  const benchmark = bench.some(Number.isFinite) ? bench : undefined;
  const benchStats = benchmark ? curveStats(benchmark.filter(Number.isFinite)) : null;
  const benchReturn =
    benchStats && benchStats.first > 0 ? benchStats.last / benchStats.first - 1 : null;
  const days = fillDays(orders);
  const filled = orders.filter(isFilled).length;
  const planned = nextRebalances(row.rebalance, etToday(now), 4);
  const futureEnd = new Date(
    Math.max(
      now.getTime() + 21 * DAY_MS,
      (planned[planned.length - 1]?.getTime() ?? 0) + 3 * DAY_MS
    )
  );
  const amount = Number(draft);
  const account = live.kind === 'ready' ? live.account : null;
  const holdings = positions
    .map((p) => ({
      symbol: p.symbol,
      value: toNumber(p.marketValue),
      price: toNumber(p.currentPrice),
    }))
    .filter((h) => h.value > 0)
    .sort((a, b) => b.value - a.value);
  const preview = sharesFor(amount, holdings);
  const tooMuch =
    account !== null && Math.round(amount * 100) > Math.round(account.unallocatedCash * 100);
  const invalid = !(amount > 0) || tooMuch;
  const canStart = account !== null && !invalid && agreed && !deploying;
  const symbols = holdings.map((h) => h.symbol);

  const onStart = async () => {
    if (!account || !canStart) return;
    setStartError(null);
    const result = await deploy({
      strategyId: session.strategyId,
      strategyName: row.name,
      strategyVersion: execution?.version ?? 0,
      allocation: amount,
      goLive: true,
      mode: 'live',
      name: `${row.name} (live)`,
      account: { credentialsId: account.credentialsId, unallocatedCash: account.unallocatedCash },
    });
    if (!result) return;
    if (result.liveError) {
      setStartError(result.liveError);
      return;
    }
    if (!keepPaper) await runCommand(sessionId, 'stop');
    navigate(result.sessionId ? `/trading/${result.sessionId}` : '/trading');
  };

  return (
    <div className="page">
      <PageHead
        crumbs={[
          { label: 'Sessions', to: '/trading' },
          { label: row.name, to: `/trading/${sessionId}` },
          { label: 'Run on live' },
        ]}
        title={`Run ${row.name} on live`}
        sub={[
          row.version ? `Version ${row.version}` : null,
          symbols.length ? `holds ${symbols.slice(0, 4).join(', ')}` : null,
          row.rebalance ? `rebalances ${row.rebalance.toLowerCase()}` : null,
        ]
          .filter(Boolean)
          .join(' · ')}
      />
      <div className="grid items-start gap-3.5 lg:grid-cols-[minmax(0,1fr)_420px]">
        <div className="grid min-w-0 gap-3.5">
          <div className="rounded-panel border border-line bg-panel px-5 pb-2 pt-4">
            <div className="text-[10.5px] font-medium uppercase tracking-[0.06em] text-fg-3">
              Paper record{started ? `, ${etDayLabel(started)} to today` : ''}
            </div>
            <div className="mb-3 mt-1 flex flex-wrap items-baseline gap-2">
              {f.equity !== null && (
                <Money value={f.equity} className="text-[28px] font-semibold tracking-[-0.03em]" />
              )}
              {f.total !== null && <Money value={f.total} pnl className="text-[12px]" />}
              {f.totalPct !== null && <Pct value={f.totalPct} pnl dp={1} className="text-[12px]" />}
              <ModeBadge mode="paper" size="sm" />
            </div>
            {series.dates.length > 1 ? (
              <AnnotatedCurve
                label={`${row.name} paper sleeve value`}
                dates={series.dates}
                values={series.values}
                benchmark={benchmark}
                end={now}
                now={{ label: `Now ${etHm(now)}` }}
                height={170}
                future={{
                  end: futureEnd,
                  title: 'Next rebalances',
                  content: (
                    <div className="grid gap-1">
                      {planned.length === 0 ? (
                        <span className="text-fg-3">At each rebalance</span>
                      ) : (
                        planned.map((d, i) => (
                          <div key={d.getTime()} className="flex gap-2">
                            <span className="num text-fg-3">{dayLabel(d)}</span>
                            <span className={i === 0 ? 'font-semibold text-fg' : ''}>
                              {i === 0 ? 'First live orders' : 'Rebalance'}
                            </span>
                          </div>
                        ))
                      )}
                    </div>
                  ),
                }}
                pins={[
                  ...(started && allocatedLabel(execution?.allocatedCapital)
                    ? [
                        {
                          at: started,
                          label: `Started, ${allocatedLabel(execution?.allocatedCapital)}`,
                        },
                      ]
                    : []),
                  { at: now, label: 'Live starts here', tone: 'accent' as const, guide: false },
                ]}
                lanes={[
                  {
                    id: 'paper',
                    label: 'Paper',
                    badge: <ModeBadge mode="paper" size="sm" />,
                    events: days.map((d) => ({
                      at: d.at,
                      shape: 'ring' as const,
                      title: etDayLabel(d.at),
                    })),
                    future: keepPaper
                      ? { events: planned.map((at) => ({ at, shape: 'planned' as const })) }
                      : { note: 'Stops when live starts' },
                  },
                  {
                    id: 'live',
                    label: 'Live',
                    badge: <ModeBadge mode="live" size="sm" />,
                    spans: [{ from: now, style: 'off' }],
                    events: [],
                    future: { events: planned.map((at) => ({ at, shape: 'planned' as const })) },
                  },
                ]}
                legend={[
                  { shape: 'ring', label: 'Rebalance' },
                  { shape: 'planned', label: 'Planned' },
                ]}
              />
            ) : (
              <p className="m-0 py-10 text-center text-[12.5px] text-fg-3">
                This session has no valued history yet.
              </p>
            )}
          </div>
          <dl
            className={`m-0 grid grid-cols-2 overflow-hidden rounded-panel border border-line bg-panel ${
              benchReturn !== null ? 'sm:grid-cols-5' : 'sm:grid-cols-4'
            }`}
          >
            <Cell label={started ? `Paper, since ${etDayLabel(started)}` : 'Paper, since start'}>
              {f.totalPct === null ? '·' : <Pct value={f.totalPct} pnl dp={1} />}
            </Cell>
            {benchReturn !== null && (
              <Cell label="SPY, same dates">
                <Pct value={benchReturn} signed dp={1} />
              </Cell>
            )}
            <Cell label="Largest drawdown">
              {stats ? <span>{formatPct(stats.maxDrawdown, { dp: 1 })}</span> : '·'}
            </Cell>
            <Cell label="Rebalances that traded">{days.length}</Cell>
            <Cell label="Orders filled">{filled}</Cell>
          </dl>
        </div>

        <Panel title="Review">
          <div className="grid gap-4 p-4">
            <div className="grid grid-cols-[1fr_16px_1fr] items-center gap-2 text-[12.5px]">
              <span className="flex items-center gap-2 rounded-[8px] border border-dashed border-line-strong px-3 py-2">
                <ModeBadge mode="paper" size="sm" />
                {keepPaper ? 'Keeps running' : 'Stops'}
              </span>
              <ArrowRight className="h-4 w-4 text-fg-3" aria-hidden="true" />
              <span className="flex items-center gap-2 rounded-[8px] border border-line px-3 py-2">
                <ModeBadge mode="live" size="sm" />
                New session
              </span>
            </div>

            {live.kind === 'loading' && (
              <p className="m-0 text-[12.5px] text-fg-3">Reading your live account…</p>
            )}
            {live.kind === 'error' && (
              <p role="alert" className="m-0 text-[12.5px] text-risk">
                {live.message}
              </p>
            )}
            {live.kind === 'none' && (
              <div className="rounded-[8px] border border-line bg-sunk px-3 py-2.5 text-[12.5px] text-fg-2">
                <b className="block font-semibold text-fg">No Alpaca live account is connected</b>
                Connect your live keys in Settings, then come back here to start a live session.{' '}
                <Link to="/settings/broker" className="text-accent hover:underline">
                  Open Settings
                </Link>
              </div>
            )}
            {account && (
              <label className="grid gap-1.5">
                <span className="text-[12.5px] text-fg-2">
                  Capital from {alpacaAccountLabel(true, account.accountNumber)}
                </span>
                <span className="flex items-center gap-2 rounded-[10px] border border-line-strong px-3 py-2">
                  <span className="text-fg-3">$</span>
                  <input
                    type="number"
                    inputMode="decimal"
                    min={0}
                    step={100}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    aria-invalid={invalid}
                    className="num min-w-0 flex-1 bg-transparent text-[18px] font-semibold outline-none"
                  />
                  <span className="whitespace-nowrap text-[11.5px] text-fg-3">
                    of {formatMoney(account.unallocatedCash)} free
                  </span>
                </span>
                <span className={`text-[11.5px] ${tooMuch ? 'text-risk' : 'text-fg-3'}`}>
                  {tooMuch
                    ? 'That is more than the free cash in your live account.'
                    : preview.buys.length
                      ? `At the last prices that buys about ${preview.buys
                          .map((b) => `${formatNumber(b.shares, { dp: 0 })} ${b.symbol}`)
                          .join(' and ')}, with ${formatMoney(preview.cash)} left as cash.`
                      : 'The first rebalance works out the orders.'}
                </span>
              </label>
            )}

            <dl className="m-0 grid gap-0 text-[12.5px]">
              <div className="flex justify-between border-b border-line py-2">
                <dt className="text-fg-2">First live orders</dt>
                <dd className="num m-0">
                  {planned[0] ? dayLabel(planned[0]) : 'At the next rebalance'}
                </dd>
              </div>
              <div className="flex justify-between py-2">
                <dt className="text-fg-2">Default limits</dt>
                <dd className="num m-0">
                  {formatMoney(DEFAULT_RISK_LIMITS.maxOrderValue, { dp: 0 })} an order,{' '}
                  {formatMoney(DEFAULT_RISK_LIMITS.maxDailyLoss, { dp: 0 })} a day
                </dd>
              </div>
            </dl>

            <fieldset className="m-0 grid gap-2.5 border-0 p-0">
              <legend className="mb-2 text-[12.5px] text-fg-2">The paper session</legend>
              <Radio
                on={keepPaper}
                onSelect={() => setKeepPaper(true)}
                title="Keep it running beside the live one"
              >
                Both follow the same rules, so you can compare them.
              </Radio>
              <Radio on={!keepPaper} onSelect={() => setKeepPaper(false)} title="Stop it">
                Its holdings move to Unmanaged on the paper account. Nothing is sold.
              </Radio>
            </fieldset>

            <div className="flex gap-3 rounded-[8px] border border-line border-l-[3px] border-l-fg bg-sunk px-3.5 py-3 text-[12.5px] text-fg-2">
              <Lock className="mt-0.5 h-3.5 w-3.5 flex-none" aria-hidden="true" />
              <span>
                <b className="font-semibold text-fg">This uses real money.</b> The live session
                places orders in your Alpaca live account automatically at every rebalance
                {planned[0] ? `, starting ${dayLabel(planned[0])}` : ''}. You can pause or stop it
                at any time.
              </span>
            </div>
            <label className="flex items-center gap-2 text-[12.5px]">
              <input
                type="checkbox"
                checked={agreed}
                onChange={(e) => setAgreed(e.target.checked)}
              />
              I understand these are real orders with my own money.
            </label>
            {(startError || deployError) && (
              <p role="alert" className="m-0 text-[12.5px] text-risk">
                {startError ?? deployError}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Link to={`/trading/${sessionId}`} className="btn btn-ghost">
                Cancel
              </Link>
              <button
                type="button"
                className="btn btn-primary"
                disabled={!canStart}
                onClick={onStart}
              >
                {deploying
                  ? 'Starting…'
                  : `Start live session${amount > 0 ? ` with ${formatMoney(amount, { dp: 0 })}` : ''}`}
              </button>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function allocatedLabel(d: Parameters<typeof toNumber>[0]): string | null {
  const v = toNumber(d);
  return v > 0 ? formatMoney(v) : null;
}

function Cell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border-b border-r border-line px-4 py-3 last:border-r-0">
      <dt className="text-[10.5px] font-medium uppercase tracking-[0.06em] text-fg-3">{label}</dt>
      <dd className="m-0 mt-1 font-mono text-[19px] font-semibold">{children}</dd>
    </div>
  );
}

function Radio({
  on,
  onSelect,
  title,
  children,
}: {
  on: boolean;
  onSelect: () => void;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <label className="grid cursor-pointer grid-cols-[18px_minmax(0,1fr)] gap-2.5 text-[12.5px]">
      <input type="radio" checked={on} onChange={onSelect} className="mt-0.5" />
      <span>
        <b className="block font-medium text-fg">{title}</b>
        <span className="text-fg-3">{children}</span>
      </span>
    </label>
  );
}
