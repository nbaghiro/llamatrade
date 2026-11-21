import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { OrderSide, type Order } from '@llamatrade/core/proto/trading_pb';
import { toDate, toNumber, useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { useFundingStore } from '@llamatrade/core/stores/funding';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { Plus } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { Panel } from '../../components/backtest/parts';
import { liveFreeCash, useLiveAccount } from '../../components/portfolio/useLiveAccount';
import {
  Blotter,
  buildSessionRow,
  etToday,
  ReadyToDeploy,
  rowNextRebalance,
  sortRows,
  type SessionRow,
} from '../../components/sessions';
import { needsYou } from '../../components/sessions/needs';
import { NeedsYou } from '../../components/sessions/NeedsYou';
import { relativeDay, rowNextRun } from '../../components/sessions/sessionRows';
import { SessionsPhoneList } from '../../components/sessions/SessionsPhoneList';
import { SessionTimeline, type TimelineGroup } from '../../components/sessions/SessionTimeline';
import {
  etDayKey,
  etHm,
  fillDays,
  isFilled,
  nowLabel,
  orderTime,
  RANGE_OPTIONS,
  rangeStart,
  toSeries,
  type TimeRange,
  windowed,
} from '../../components/sessions/timeline';
import { usePageScope } from '../../components/shell/usePageScope';
import { ModeBadge, PageHead, ScopeControl, Segmented, StatList } from '../../components/ui';
import { Money } from '../../components/ui/Num';
import { PanelError } from '../../components/ui/PanelError';
import { SkeletonRows } from '../../components/ui/Skeleton';
import { formatMoney, formatNumber } from '../../lib/format';
import { alpacaAccountLabel, inScope } from '../../lib/scope';

const COMPACT_OVER = 12;
const qty = (v: number) => formatNumber(v, { dp: Number.isInteger(v) ? 0 : 2 });
const isLive = (r: SessionRow) => r.session.mode === ExecutionMode.LIVE;

/** /trading: every session on one timeline, what needs you, today's fills (list2 A, phone2 B). */
export default function TradingPage() {
  const [params] = useSearchParams();
  const wantsDeploy = params.has('deploy');
  const sessions = useTradingStore((s) => s.sessions);
  const orders = useTradingStore((s) => s.orders);
  const executions = useTradingStore((s) => s.executions);
  const sleeves = useTradingStore((s) => s.sleeves);
  const performance = useTradingStore((s) => s.performance);
  const curves = useTradingStore((s) => s.curves);
  const loading = useTradingStore((s) => s.loading);
  const loaded = useTradingStore((s) => s.loaded);
  const error = useTradingStore((s) => s.error);
  const loadBlotter = useTradingStore((s) => s.loadBlotter);
  const loadCurves = useTradingStore((s) => s.loadCurves);
  const strategies = useBacktestStore((s) => s.strategies);
  const fetchStrategies = useBacktestStore((s) => s.fetchStrategies);
  const credentials = useBrokerStore((s) => s.credentials);
  const paperFree = useFundingStore((s) => s.unallocatedCash);
  const fundingResolved = useFundingStore((s) => s.resolved);
  const resolveAccount = useFundingStore((s) => s.resolveAccount);
  const [range, setRange] = useState<TimeRange>('3M');
  const liveAccount = useLiveAccount();
  const liveFree = liveFreeCash(liveAccount);

  useEffect(() => {
    loadBlotter()
      .then(() => loadCurves())
      .catch(() => undefined);
    fetchStrategies().catch(() => undefined);
    resolveAccount().catch(() => undefined);
  }, [loadBlotter, loadCurves, fetchStrategies, resolveAccount]);

  const allRows = useMemo(
    () =>
      sortRows(
        sessions.map((s) =>
          buildSessionRow(s, { executions, sleeves, performance, strategies, orders })
        )
      ),
    [sessions, executions, sleeves, performance, strategies, orders]
  );

  const sum = (rs: readonly SessionRow[]) =>
    rs.some((r) => r.figures.equity !== null)
      ? rs.reduce((n, r) => n + (r.figures.equity ?? 0), 0)
      : undefined;
  const openRows = allRows.filter((r) => r.view.open);
  const { scope, setScope, options } = usePageScope('sessions', {
    all: sum(openRows),
    live: sum(openRows.filter(isLive)),
    paper: sum(openRows.filter((r) => !isLive(r))),
  });
  const rows = allRows.filter((r) => inScope(scope, isLive(r)));
  const names = useMemo(
    () => Object.fromEntries(allRows.map((r) => [r.session.id, r.name])),
    [allRows]
  );

  const now = new Date();
  const today = etToday(now);
  const todayKey = etDayKey(now);
  const needs = needsYou(rows, orders, now);
  const ordersBySession = useMemo(() => {
    const m = new Map<string, Order[]>();
    for (const o of orders) m.set(o.sessionId, [...(m.get(o.sessionId) ?? []), o]);
    return m;
  }, [orders]);
  const todaysFills = orders
    .filter((o) => isFilled(o) && rows.some((r) => r.session.id === o.sessionId))
    .map((o) => ({ o, at: orderTime(o) }))
    .filter((x): x is { o: Order; at: Date } => x.at !== null && etDayKey(x.at) === todayKey)
    .sort((a, b) => a.at.getTime() - b.at.getTime());

  const earliest = rows
    .map((r) => r.startedAt)
    .filter((d): d is Date => d !== null)
    .sort((a, b) => a.getTime() - b.getTime())[0];
  const start = rangeStart(range, now, earliest ?? null);

  const numberOf = (live: boolean) =>
    credentials.find((c) => c.isActive && c.isPaper === !live)?.accountNumber;
  const accountLabel = (live: boolean) => alpacaAccountLabel(live, numberOf(live), numberOf(!live));
  const groups: TimelineGroup[] = [true, false]
    .map((live) => {
      const rs = rows.filter((r) => isLive(r) === live);
      return {
        key: live ? 'live' : 'paper',
        heading: (
          <>
            <ModeBadge mode={live ? 'live' : 'paper'} size="sm" />
            {accountLabel(live)}
          </>
        ),
        total: sum(rs.filter((r) => r.view.open)) ?? null,
        sessions: rs.map((row) => {
          const curve = row.execution ? curves[row.execution.id] : undefined;
          const sessionOrders = ordersBySession.get(row.session.id) ?? [];
          const days = fillDays(sessionOrders);
          const todayDay = days.find((d) => d.key === todayKey);
          return {
            row,
            series: windowed(toSeries(curve?.points ?? []), start, now, row.figures.equity),
            days: days.filter((d) => d.key !== todayKey),
            fillsToday: todayDay?.orders.length ?? 0,
            next: rowNextRebalance(row, today),
            ended: row.view.open ? null : (toDate(row.session.endedAt) ?? null),
          };
        }),
      };
    })
    .filter((g) => g.sessions.length > 0);

  const empty = loaded && !error && sessions.length === 0;
  const accounts = new Set(rows.map(isLive)).size;
  const running = rows.filter((r) => r.view.open).length;
  const stopped = rows.length - running;
  const nextRun = rows
    .map((r) => rowNextRun(r, now))
    .filter((d): d is Date => d !== null)
    .sort((a, b) => a.getTime() - b.getTime())[0];
  const sub = loaded && !error && !empty && (
    <>
      {[
        needs.length
          ? `${needs.length} ${needs.length === 1 ? 'thing needs' : 'things need'} you`
          : null,
        `${rows.length} ${rows.length === 1 ? 'session' : 'sessions'} on ${accounts} Alpaca ${accounts === 1 ? 'account' : 'accounts'}`,
        `${running} open${stopped ? `, ${stopped} stopped` : ''}`,
        nextRun ? `next rebalance ${relativeDay(nextRun, today)}` : null,
      ]
        .filter(Boolean)
        .join(' · ')}
    </>
  );

  const liveRows = rows.filter((r) => isLive(r) && r.view.open);
  const paperRows = rows.filter((r) => !isLive(r) && r.view.open);
  const totals = [
    ...(liveRows.length
      ? [
          {
            label: `Live, ${liveRows.length} ${liveRows.length === 1 ? 'session' : 'sessions'}`,
            value: <AccountFigure rows={liveRows} />,
          },
        ]
      : []),
    ...(paperRows.length
      ? [
          {
            label: `Paper, ${paperRows.length} ${paperRows.length === 1 ? 'session' : 'sessions'}`,
            value: <AccountFigure rows={paperRows} />,
          },
        ]
      : []),
    ...(liveFree !== null && scope !== 'paper'
      ? [{ label: 'Free cash, live', value: formatMoney(liveFree) }]
      : []),
    ...(fundingResolved && scope !== 'live'
      ? [{ label: 'Free cash, paper', value: formatMoney(paperFree) }]
      : []),
  ];

  return (
    <div className="page relative isolate">
      <PageHead
        title="Sessions"
        sub={sub}
        scope={
          !empty && options.length > 0 ? (
            <ScopeControl options={options} value={scope} onChange={setScope} />
          ) : undefined
        }
        actions={
          !empty && (
            <>
              <Segmented<TimeRange>
                label="Time range"
                value={range}
                onChange={setRange}
                options={RANGE_OPTIONS}
                className="hidden md:inline-flex"
              />
              <Link to="/trading?deploy=1" className="btn btn-primary">
                <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                Start a strategy
              </Link>
            </>
          )
        }
      />
      {empty ? (
        <ReadyToDeploy />
      ) : error && !sessions.length ? (
        <Panel>
          <PanelError
            title="Sessions couldn't be loaded"
            cause={error}
            unaffected="Running sessions keep trading on schedule."
            onRetry={() => loadBlotter()}
            retrying={loading}
          />
        </Panel>
      ) : (
        <div className="grid gap-3.5">
          {wantsDeploy && <ReadyToDeploy />}
          <NeedsYou items={needs} />
          {!loaded ? (
            <Panel>
              <SkeletonRows rows={4} cols={6} />
            </Panel>
          ) : (
            <>
              <div className="hidden md:block">
                <SessionTimeline
                  groups={groups}
                  start={start}
                  now={now}
                  nowLabel={nowLabel(now)}
                  compact={rows.length > COMPACT_OVER}
                />
              </div>
              <div className="md:hidden">
                <SessionsPhoneList rows={rows} today={today} />
              </div>
              <div className="hidden gap-3.5 md:grid md:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)]">
                <Panel
                  title="Today's fills"
                  aside={todaysFills.length ? `${todaysFills.length} filled` : undefined}
                >
                  {todaysFills.length === 0 ? (
                    <p className="m-0 px-3.5 py-4 text-[12.5px] text-fg-3">
                      Nothing has filled today. Fills appear here as rebalances trade.
                    </p>
                  ) : (
                    <ol className="m-0 list-none p-0">
                      {todaysFills.map(({ o, at }) => (
                        <li key={o.id} className="border-b border-line last:border-b-0">
                          <Link
                            to={`/trading/orders/${o.id}`}
                            className="grid grid-cols-[42px_minmax(0,1fr)_auto_52px] items-center gap-3 px-3.5 py-2.5 hover:bg-sunk"
                          >
                            <span className="rounded-sm px-[5px] py-[3px] text-center font-mono text-[10px] font-semibold leading-none ring-1 ring-inset ring-line-strong">
                              {o.side === OrderSide.SELL ? 'SELL' : 'BUY'}
                            </span>
                            <span className="min-w-0">
                              <span className="block truncate text-[13px] text-fg">
                                {qty(toNumber(o.filledQuantity))} {o.symbol} at{' '}
                                {formatMoney(toNumber(o.averageFillPrice))}
                              </span>
                              <span className="block truncate text-[11.5px] text-fg-3">
                                {names[o.sessionId] ?? 'Session'}
                              </span>
                            </span>
                            <Money
                              value={toNumber(o.filledQuantity) * toNumber(o.averageFillPrice)}
                              className="text-[12.5px]"
                            />
                            <span className="num text-right text-[11.5px] text-fg-3">
                              {etHm(at)}
                            </span>
                          </Link>
                        </li>
                      ))}
                    </ol>
                  )}
                </Panel>
                <Panel title="Not added together" aside="each account on its own">
                  <div className="px-3.5 py-1">
                    {totals.length ? (
                      <StatList items={totals} />
                    ) : (
                      <p className="m-0 py-3 text-[12.5px] text-fg-3">No open sessions.</p>
                    )}
                  </div>
                </Panel>
              </div>
              <div className="hidden md:block">
                <Blotter
                  orders={orders.filter((o) => names[o.sessionId] !== undefined)}
                  sessionNames={names}
                />
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function AccountFigure({ rows }: { rows: readonly SessionRow[] }) {
  const value = rows.reduce((n, r) => n + (r.figures.equity ?? 0), 0);
  const known = rows.filter((r) => r.figures.today !== null);
  const today = known.reduce((n, r) => n + (r.figures.today ?? 0), 0);
  return (
    <span className="whitespace-nowrap">
      {formatMoney(value)}
      {known.length > 0 && (
        <>
          {' · '}
          <Money value={today} pnl />
        </>
      )}
    </span>
  );
}
