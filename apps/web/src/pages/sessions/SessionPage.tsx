import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { OrderSide, type Order } from '@llamatrade/core/proto/trading_pb';
import { toDate, toNumber, useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { useTradingStore, type SessionCommand } from '@llamatrade/core/stores/trading';
import { MoreHorizontal, Pause, Play, Square } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { Panel } from '../../components/backtest/parts';
import { AnnotatedCurve, type CurveLane, type CurvePin } from '../../components/charts';
import { Blotter, buildSessionRow, etToday, rowNextRebalance } from '../../components/sessions';
import { FrozenPanel } from '../../components/sessions/FrozenPanel';
import { dayLabel } from '../../components/sessions/sessionRows';
import { StopDialog } from '../../components/sessions/StopDialog';
import {
  asOf,
  curveStats,
  etDayKey,
  etDayLabel,
  etHm,
  fillDays,
  isFilled,
  orderTime,
  RANGE_OPTIONS,
  rangeStart,
  symbolLanes,
  toSeries,
  windowed,
  type TimeRange,
} from '../../components/sessions/timeline';
import {
  Menu,
  ModeBadge,
  PageHead,
  Segmented,
  StatList,
  StatusMark,
  WeightBar,
} from '../../components/ui';
import { Money, Pct } from '../../components/ui/Num';
import { PanelError } from '../../components/ui/PanelError';
import { SkeletonChart, SkeletonFigure } from '../../components/ui/Skeleton';
import { formatMoney, formatNumber, formatPct } from '../../lib/format';
import { maskedKey } from '../../lib/scope';

const DAY_MS = 86_400_000;
const MAX_LANES = 6;
const qty = (v: number) => formatNumber(v, { dp: Number.isInteger(v) ? 0 : 2 });

/** /trading/:sessionId: the session on its own annotated curve (detail2 A), amber when frozen (frozen2 A). */
export default function SessionPage() {
  const { sessionId = '' } = useParams();
  const detail = useTradingStore((s) => (s.detail?.session.id === sessionId ? s.detail : null));
  const detailLoading = useTradingStore((s) => s.detailLoading);
  const detailError = useTradingStore((s) => s.detailError);
  const loadSession = useTradingStore((s) => s.loadSession);
  const runCommand = useTradingStore((s) => s.runCommand);
  const commandPending = useTradingStore((s) => s.commandPending);
  const commandError = useTradingStore((s) => s.commandError);
  const performance = useTradingStore((s) => s.performance);
  const strategies = useBacktestStore((s) => s.strategies);
  const fetchStrategies = useBacktestStore((s) => s.fetchStrategies);
  const credentials = useBrokerStore((s) => s.credentials);
  const fetchCredentials = useBrokerStore((s) => s.fetch);
  const [range, setRange] = useState<TimeRange>('all');
  const [stopping, setStopping] = useState(false);

  const reload = useCallback(() => {
    loadSession(sessionId, new Date(0)).catch(() => undefined);
  }, [sessionId, loadSession]);

  useEffect(() => {
    reload();
    fetchStrategies().catch(() => undefined);
    fetchCredentials().catch(() => undefined);
  }, [reload, fetchStrategies, fetchCredentials]);

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

  const onCommand = async (command: SessionCommand) => {
    if (await runCommand(sessionId, command)) reload();
  };

  const crumbs = [{ label: 'Sessions', to: '/trading' }];

  if (detailError && !detail) {
    return (
      <div className="page">
        <PageHead crumbs={crumbs} title="Session" />
        <Panel>
          <PanelError
            title="This session couldn't be loaded"
            cause={detailError}
            unaffected="The session keeps trading on schedule either way."
            onRetry={reload}
            retrying={detailLoading}
          />
        </Panel>
      </div>
    );
  }

  if (!detail || !row) {
    return (
      <div className="page grid gap-3.5" aria-busy="true">
        <SkeletonFigure />
        <div className="rounded-panel border border-line bg-panel p-4">
          <SkeletonChart height={260} />
        </div>
      </div>
    );
  }

  const { session, positions, orders, execution } = detail;
  const mode = session.mode === ExecutionMode.LIVE ? 'live' : 'paper';
  const f = row.figures;
  const now = new Date();
  const today = etToday(now);
  const started = toDate(session.startedAt);
  const ended = row.view.open ? null : (toDate(session.endedAt) ?? toDate(execution?.stoppedAt));
  const end = ended ?? now;
  const next = rowNextRebalance(row, today);
  const frozen = row.state === 'frozen';
  const cred = credentials.find((c) => c.id === execution?.credentialsId);
  const account = `Alpaca ${mode}${cred ? ` ${maskedKey(cred.apiKeyPrefix)}` : ''}`;
  const allocated = execution?.allocatedCapital ? toNumber(execution.allocatedCapital) : null;
  const cash = row.sleeve?.cash ? toNumber(row.sleeve.cash.balance) : null;

  const held = positions
    .map((p) => ({ p, q: toNumber(p.quantity), value: toNumber(p.marketValue) }))
    .filter((x) => x.q !== 0)
    .sort((a, b) => b.value - a.value);
  const equityForWeights = f.equity ?? held.reduce((s, x) => s + x.value, 0) + (cash ?? 0);

  const full = toSeries(detail.curve);
  const start = rangeStart(range, end, started);
  const series = windowed(full, start, end, row.view.open ? f.equity : null);
  const bench = detail.benchmark.length ? asOf(toSeries(detail.benchmark), series.dates) : [];
  const benchmark = bench.some(Number.isFinite) ? bench : undefined;
  const stats = curveStats(series.values);
  const benchStats = benchmark ? curveStats(benchmark) : null;
  const sinceStart = f.totalPct;
  const benchReturn =
    benchStats && benchStats.first > 0 ? benchStats.last / benchStats.first - 1 : null;

  const filled = orders
    .filter(isFilled)
    .map((o) => ({ o, at: orderTime(o) }))
    .filter((x): x is { o: Order; at: Date } => x.at !== null);
  const days = fillDays(orders);
  const todayKey = etDayKey(now);
  const todays = filled
    .filter((x) => etDayKey(x.at) === todayKey)
    .sort((a, b) => a.at.getTime() - b.at.getTime());
  const value = (o: Order) => toNumber(o.filledQuantity) * toNumber(o.averageFillPrice);
  const largest = [...filled].sort((a, b) => value(b.o) - value(a.o))[0];
  const inWindow = (d: Date) => d >= start && d <= end;

  const pins: CurvePin[] = [
    ...(started && inWindow(started)
      ? [
          {
            at: started,
            label: allocated ? `Started · ${formatMoney(allocated, { dp: 0 })}` : 'Started',
          },
        ]
      : []),
    ...(largest && inWindow(largest.at) && filled.length > 1
      ? [{ at: largest.at, label: `Largest trade · ${etDayLabel(largest.at)}`, row: 1 as const }]
      : []),
    ...(todays.length
      ? [
          {
            at: end,
            label: 'Fills today',
            tone: 'accent' as const,
            count: todays.length,
            guide: false,
          },
        ]
      : []),
  ];

  const lanesFor = symbolLanes(
    orders,
    held.map((x) => x.p.symbol)
  );
  const planned = next
    ? [{ at: next, shape: 'planned' as const, title: `Rebalance ${dayLabel(next)}` }]
    : [];
  const fillEvents = (fills: (typeof lanesFor)[number]['fills']) =>
    fills.map((x) => ({
      at: x.at,
      shape: x.side === 'buy' ? ('dot' as const) : ('ring' as const),
      title: `${x.side === 'buy' ? 'Buy' : 'Sell'} ${qty(toNumber(x.order.filledQuantity))} ${x.order.symbol}, ${etDayLabel(x.at)}`,
    }));
  const lanes: CurveLane[] =
    lanesFor.length > MAX_LANES
      ? [
          {
            id: 'orders',
            label: 'Orders',
            sub: `${lanesFor.length} symbols · ${filled.length} fills`,
            tone: frozen ? 'risk' : row.view.open ? 'default' : 'muted',
            events: fillEvents(lanesFor.flatMap((l) => l.fills)),
            future: { events: planned },
          },
        ]
      : lanesFor.map((l) => {
          const h = held.find((x) => x.p.symbol === l.symbol);
          return {
            id: l.symbol,
            label: <span className="font-mono">{l.symbol}</span>,
            sub: h
              ? `${qty(h.q)} shares${equityForWeights > 0 ? ` · ${formatPct(h.value / equityForWeights, { dp: 1 })}` : ''}`
              : 'not held',
            tone: frozen ? 'risk' : h ? 'default' : 'muted',
            spans: [
              {
                from: started && started > start ? started : start,
                to: ended ?? undefined,
                style: h ? 'on' : 'off',
              },
            ],
            events: fillEvents(l.fills),
            future: row.view.open ? { events: planned } : { note: 'Stopped' },
          };
        });

  const futureEnd = new Date(end.getTime() + 14 * DAY_MS);
  const futureRows = row.view.open
    ? frozen
      ? [
          ['Waiting on you', ''],
          ...(next ? [[dayLabel(next), 'Rebalance runs once resolved']] : []),
        ]
      : row.state === 'paused'
        ? [['Paused', 'Rebalances are skipped until you resume']]
        : next && next.getTime() <= futureEnd.getTime()
          ? [[dayLabel(next), `${row.rebalance || 'Scheduled'} rebalance`]]
          : [
              [
                next ? dayLabel(next) : '·',
                next ? 'Next rebalance, after this window' : 'Nothing scheduled',
              ],
            ]
    : [];

  const meta = [
    row.version ? `Version ${row.version}` : null,
    account,
    started
      ? `started ${etDayLabel(started)}${allocated ? ` with ${formatMoney(allocated)}` : ''}`
      : null,
    row.rebalance ? `rebalances ${row.rebalance.toLowerCase()}` : null,
    ended
      ? `stopped ${etDayLabel(ended)}`
      : next && row.state === 'running'
        ? `next ${dayLabel(next)}`
        : null,
  ]
    .filter(Boolean)
    .join(' · ');

  const canPause = row.view.actions.includes('pause');
  const canResume = row.view.actions.includes('resume');
  const canStop = row.view.actions.includes('stop');
  const canGoLive = mode === 'paper' && row.state === 'running';

  const stateLabel = frozen ? 'Frozen' : row.view.label;

  return (
    <div className="page">
      <PageHead
        crumbs={[...crumbs, { label: mode === 'live' ? 'Live' : 'Paper' }]}
        title={row.name}
        badges={
          <>
            <ModeBadge mode={mode} />
            <StatusMark state={row.view.mark} label={stateLabel} />
          </>
        }
        sub={meta}
        actions={
          <>
            <div className="hidden flex-wrap items-center gap-2 md:flex">
              <Link to={`/trading/${sessionId}/rebalances`} className="btn btn-ghost">
                Rebalances
              </Link>
              {canPause && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={commandPending !== null}
                  onClick={() => onCommand('pause')}
                >
                  <Pause className="h-3.5 w-3.5" aria-hidden="true" />
                  {commandPending === 'pause' ? 'Pausing…' : 'Pause'}
                </button>
              )}
              {canResume && (
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={commandPending !== null}
                  onClick={() => onCommand('resume')}
                >
                  <Play className="h-3.5 w-3.5" aria-hidden="true" />
                  {commandPending === 'resume' ? 'Resuming…' : 'Resume'}
                </button>
              )}
              {canStop && (
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={commandPending !== null}
                  onClick={() => setStopping(true)}
                >
                  {commandPending === 'stop' ? 'Stopping…' : 'Stop'}
                </button>
              )}
              {canGoLive && (
                <Link to={`/trading/${sessionId}/live`} className="btn btn-primary">
                  Go live
                </Link>
              )}
              {!row.view.open && (
                <Link to={`/strategies/${session.strategyId}`} className="btn btn-secondary">
                  Open the strategy
                </Link>
              )}
            </div>
            {(canPause || canResume || canStop) && (
              <div className="md:hidden">
                <Menu
                  label="Session actions"
                  width={220}
                  trigger={(props) => (
                    <button type="button" className="btn btn-secondary" {...props}>
                      <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
                      Manage
                    </button>
                  )}
                  items={[
                    ...(canPause
                      ? [
                          {
                            kind: 'action' as const,
                            label: 'Pause',
                            icon: Pause,
                            onSelect: () => onCommand('pause'),
                          },
                        ]
                      : []),
                    ...(canResume
                      ? [
                          {
                            kind: 'action' as const,
                            label: 'Resume',
                            icon: Play,
                            onSelect: () => onCommand('resume'),
                          },
                        ]
                      : []),
                    ...(canStop
                      ? [
                          {
                            kind: 'action' as const,
                            label: 'Stop session',
                            icon: Square,
                            onSelect: () => setStopping(true),
                          },
                        ]
                      : []),
                  ]}
                />
              </div>
            )}
          </>
        }
      />

      {commandError && (
        <p role="alert" className="-mt-2 mb-3 text-[12.5px] text-risk">
          {commandError}
        </p>
      )}
      {row.state === 'paused' && (
        <div className="mb-3.5 flex flex-wrap items-center gap-3 rounded-[8px] border border-line bg-sunk px-3.5 py-2.5 text-[12.5px]">
          <Pause className="h-4 w-4 text-fg-3" aria-hidden="true" />
          <span className="min-w-0 flex-1 text-fg-2">
            <b className="font-semibold text-fg">Paused.</b> The sleeve and its holdings stay as
            they are, and rebalances are skipped until you resume.
          </span>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={commandPending !== null}
            onClick={() => onCommand('resume')}
          >
            Resume
          </button>
        </div>
      )}
      {row.state === 'error' && (
        <p className="mb-3.5 rounded-[8px] border border-risk-line bg-risk-soft px-3.5 py-2.5 text-[12.5px]">
          <b className="font-semibold text-risk">Stopped by an error.</b>{' '}
          {execution?.errorMessage || 'It places no new orders.'}
        </p>
      )}

      <div
        className={`grid items-start gap-3.5 ${frozen ? 'lg:grid-cols-[minmax(0,1fr)_380px]' : ''}`}
      >
        <div className="grid min-w-0 gap-3.5">
          <div className="panel-rim px-5 pb-2 pt-4">
            <div className="mb-3 flex flex-wrap items-start justify-between gap-4">
              <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
                <div>
                  <div className="text-[10.5px] font-medium uppercase tracking-[0.06em] text-fg-3">
                    Sleeve equity · {mode}
                  </div>
                  <div className="mt-1 flex flex-wrap items-baseline gap-2">
                    {f.equity === null ? (
                      <span className="text-[30px] text-fg-3">·</span>
                    ) : (
                      <Money
                        value={f.equity}
                        className="text-[30px] font-semibold tracking-[-0.03em]"
                      />
                    )}
                    {f.today !== null && row.view.open && (
                      <span className="flex items-center gap-1.5 text-[12px]">
                        <span
                          className={`rounded px-1.5 py-0.5 ${f.today < 0 ? 'bg-loss/10' : 'bg-gain/10'}`}
                        >
                          <Money value={f.today} pnl />
                        </span>
                        {f.todayPct !== null && (
                          <span
                            className={`rounded px-1.5 py-0.5 ${f.today < 0 ? 'bg-loss/10' : 'bg-gain/10'}`}
                          >
                            <Pct value={f.todayPct} pnl />
                          </span>
                        )}
                        <span className="text-fg-3">today</span>
                      </span>
                    )}
                  </div>
                </div>
                {sinceStart !== null && (
                  <Figure label={started ? `Since ${etDayLabel(started)}` : 'Since start'}>
                    <Pct value={sinceStart} pnl dp={1} />
                  </Figure>
                )}
                {benchReturn !== null && (
                  <Figure label="SPY, same period">
                    <Pct value={benchReturn} signed dp={1} />
                  </Figure>
                )}
                {cash !== null && (
                  <Figure label="Cash">
                    <Money value={cash} />
                  </Figure>
                )}
              </div>
              <Segmented<TimeRange>
                label="Time range"
                value={range}
                onChange={setRange}
                options={RANGE_OPTIONS}
              />
            </div>
            {series.dates.length > 1 ? (
              <AnnotatedCurve
                label={`${row.name} sleeve equity`}
                dates={series.dates}
                values={series.values}
                benchmark={benchmark}
                start={start}
                end={end}
                now={row.view.open ? { label: `Now ${etHm(now)}` } : undefined}
                future={
                  row.view.open
                    ? {
                        end: futureEnd,
                        title: 'Next two weeks',
                        content: (
                          <div className="grid gap-1">
                            {futureRows.map(([a, b]) => (
                              <div key={a} className="flex gap-2">
                                <span className="num flex-none text-fg-3">{a}</span>
                                <span className={frozen ? 'text-risk' : ''}>{b}</span>
                              </div>
                            ))}
                          </div>
                        ),
                      }
                    : undefined
                }
                pins={pins}
                side={
                  stats && (
                    <StatList
                      items={[
                        { label: 'High', value: formatMoney(stats.high, { dp: 0 }) },
                        { label: 'Low', value: formatMoney(stats.low, { dp: 0 }) },
                        {
                          label: 'Max drawdown',
                          value: formatPct(stats.maxDrawdown, { dp: 1 }),
                          tone: stats.maxDrawdown < 0 ? 'loss' : undefined,
                        },
                        { label: 'Fills', value: String(filled.length) },
                      ]}
                    />
                  )
                }
                lanes={lanes}
                legend={[
                  { shape: 'dot', label: 'Buy' },
                  { shape: 'ring', label: 'Sell' },
                  { shape: 'planned', label: 'Planned' },
                ]}
                tooltip={(i) => (
                  <>
                    <b className="block font-medium text-fg-3">{etDayLabel(series.dates[i])}</b>
                    {formatMoney(series.values[i])}
                  </>
                )}
              />
            ) : (
              <p className="m-0 grid h-[160px] place-items-center text-center text-[12.5px] text-fg-3">
                The curve appears once the sleeve has been valued.
              </p>
            )}
          </div>

          <div className="grid gap-3.5 md:grid-cols-3">
            <Panel title="Mix now" aside="share of the sleeve">
              <div className="grid gap-2 px-3.5 py-3">
                {equityForWeights > 0 && (held.length > 0 || cash) ? (
                  <>
                    {[
                      ...held.map((x) => ({ k: x.p.symbol, v: x.value, cash: false })),
                      ...(cash ? [{ k: 'Cash', v: cash, cash: true }] : []),
                    ].map((w) => (
                      <div
                        key={w.k}
                        className="grid grid-cols-[42px_minmax(0,1fr)_48px] items-center gap-2.5 text-xs"
                      >
                        <span className={w.cash ? 'text-fg-2' : 'font-mono font-semibold'}>
                          {w.k}
                        </span>
                        <WeightBar
                          weight={w.v / equityForWeights}
                          height={5}
                          frozen={frozen}
                          label={`${w.k} weight`}
                          color={w.cash ? 'rgb(var(--fg-3))' : undefined}
                        />
                        <span className="num text-right text-fg-2">
                          {formatPct(w.v / equityForWeights, { dp: 1 })}
                        </span>
                      </div>
                    ))}
                    <p className="m-0 text-[11.5px] text-fg-3">
                      The target mix isn&apos;t recorded, so these are current weights only.
                    </p>
                  </>
                ) : (
                  <p className="m-0 text-[12.5px] text-fg-3">
                    {row.view.open
                      ? 'The sleeve holds cash until its first rebalance.'
                      : 'No positions are held.'}
                  </p>
                )}
              </div>
            </Panel>
            <Panel
              title="Today"
              aside={
                todays.length
                  ? `${todays.length} ${todays.length === 1 ? 'fill' : 'fills'}`
                  : undefined
              }
            >
              {todays.length === 0 ? (
                <p className="m-0 px-3.5 py-3 text-[12.5px] text-fg-3">
                  Nothing traded today.
                  {next && row.state === 'running'
                    ? ` The next rebalance is ${dayLabel(next)}.`
                    : ''}
                </p>
              ) : (
                <ol className="m-0 list-none p-0">
                  {todays.map(({ o, at }) => (
                    <li key={o.id} className="border-b border-line last:border-b-0">
                      <Link
                        to={`/trading/orders/${o.id}`}
                        className="flex items-center gap-3 px-3.5 py-2.5 hover:bg-sunk"
                      >
                        <span className="rounded-sm px-[5px] py-[3px] font-mono text-[10px] font-semibold leading-none ring-1 ring-inset ring-line-strong">
                          {o.side === OrderSide.SELL ? 'SELL' : 'BUY'}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-[12.5px]">
                          {qty(toNumber(o.filledQuantity))} {o.symbol} at{' '}
                          {formatMoney(toNumber(o.averageFillPrice))}
                        </span>
                        <span className="text-right">
                          <Money value={value(o)} className="block text-[12px]" />
                          <span className="num text-[11px] text-fg-3">{etHm(at)}</span>
                        </span>
                      </Link>
                    </li>
                  ))}
                </ol>
              )}
            </Panel>
            <Panel title="Sleeve">
              <div className="px-3.5 py-1">
                <StatList
                  items={[
                    ...(allocated !== null
                      ? [{ label: 'Started with', value: formatMoney(allocated) }]
                      : []),
                    ...(f.total !== null
                      ? [
                          {
                            label: 'Since start',
                            value: formatMoney(f.total, { signed: true }),
                            tone:
                              f.total < 0
                                ? ('loss' as const)
                                : f.total > 0
                                  ? ('gain' as const)
                                  : undefined,
                          },
                        ]
                      : []),
                    { label: 'Rebalances that traded', value: String(days.length) },
                  ]}
                />
              </div>
            </Panel>
          </div>

          <div className="hidden md:block">
            <Blotter orders={orders} sessionNames={{ [session.id]: row.name }} limit={8} />
          </div>
        </div>

        {frozen && (
          <FrozenPanel
            name={row.name}
            holdings={held.map((x) => ({ symbol: x.p.symbol, quantity: x.q, value: x.value }))}
            next={next}
            onStop={() => setStopping(true)}
          />
        )}
      </div>

      <StopDialog
        open={stopping}
        onClose={() => setStopping(false)}
        name={row.name}
        mode={mode}
        holdings={held.map((x) => ({ symbol: x.p.symbol, quantity: x.q, value: x.value }))}
        cash={cash}
        recent={days.map((d) => d.at)}
        nextLabel={next && row.state === 'running' ? `${dayLabel(next)} rebalance` : null}
        now={now}
        onPause={
          canPause
            ? () => {
                setStopping(false);
                onCommand('pause');
              }
            : undefined
        }
        onStop={() => {
          setStopping(false);
          onCommand('stop');
        }}
      />
    </div>
  );
}

function Figure({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10.5px] font-medium uppercase tracking-[0.06em] text-fg-3">{label}</div>
      <div className="mt-1 text-[15px] font-semibold">{children}</div>
    </div>
  );
}
