import { OrderStatus } from '@llamatrade/core/proto/trading_pb';
import { toDate, toNumber, useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useTradingStore, type SessionCommand } from '@llamatrade/core/stores/trading';
import { ArrowLeft } from 'lucide-react';
import { useCallback, useEffect, useMemo, type ReactNode } from 'react';
import { Link, useParams } from 'react-router-dom';

import { Cells, KvList, Panel, SideTag } from '../../components/backtest/parts';
import { T } from '../../components/backtest/tableStyles';
import { LineChart } from '../../components/charts';
import {
  buildSessionRow,
  etToday,
  railFacts,
  rowNextRebalance,
  SessionHeader,
  sideWord,
  sinceLabel,
  sortRows,
  StatusRail,
  statusSentence,
  useMarketLine,
} from '../../components/sessions';
import { Money, Pct } from '../../components/ui/Num';
import { PanelError } from '../../components/ui/PanelError';
import { SkeletonChart, SkeletonFigure, SkeletonRows } from '../../components/ui/Skeleton';
import { WeightBar } from '../../components/ui/WeightBar';
import { formatMoney, formatNumber, formatPct } from '../../lib/format';
import { asSentence } from '../../lib/format';
import { etParts, etToDate } from '../../lib/marketClock';
import { DEFAULT_RISK_LIMITS } from '../../lib/sessionState';

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

/** Midnight in New York today, the start of "today's curve". */
function startOfEtDay(now = new Date()): Date {
  const p = etParts(now);
  return etToDate(p.year, p.month, p.day, 0);
}

const etTime = (d: Date) =>
  d.toLocaleTimeString('en-US', {
    timeZone: 'America/New_York',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });

const etDay = (d: Date) => {
  const p = etParts(d);
  return `${MON[p.month]} ${p.day}`;
};

interface LogEntry {
  at: Date;
  text: ReactNode;
}

const qty = (v: number) => formatNumber(v, { dp: Number.isInteger(v) ? 0 : 2 });

/** /trading/:sessionId: one paper session on one screen. */
export default function SessionPage() {
  const { sessionId = '' } = useParams();
  const detail = useTradingStore((s) => (s.detail?.session.id === sessionId ? s.detail : null));
  const detailLoading = useTradingStore((s) => s.detailLoading);
  const detailError = useTradingStore((s) => s.detailError);
  const loadSession = useTradingStore((s) => s.loadSession);
  const loadBlotter = useTradingStore((s) => s.loadBlotter);
  const runCommand = useTradingStore((s) => s.runCommand);
  const commandPending = useTradingStore((s) => s.commandPending);
  const commandError = useTradingStore((s) => s.commandError);
  const sessions = useTradingStore((s) => s.sessions);
  const executions = useTradingStore((s) => s.executions);
  const sleeves = useTradingStore((s) => s.sleeves);
  const performance = useTradingStore((s) => s.performance);
  const orders = useTradingStore((s) => s.orders);
  const blotterError = useTradingStore((s) => s.error);
  const strategies = useBacktestStore((s) => s.strategies);
  const fetchStrategies = useBacktestStore((s) => s.fetchStrategies);
  const market = useMarketLine();

  const reload = useCallback(() => {
    loadSession(sessionId, startOfEtDay()).catch(() => undefined);
    loadBlotter().catch(() => undefined);
  }, [sessionId, loadSession, loadBlotter]);

  useEffect(() => {
    reload();
    fetchStrategies().catch(() => undefined);
  }, [reload, fetchStrategies]);

  const allRows = useMemo(
    () =>
      sortRows(
        sessions.map((s) =>
          buildSessionRow(s, { executions, sleeves, performance, strategies, orders })
        )
      ),
    [sessions, executions, sleeves, performance, strategies, orders]
  );
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

  const rail = (
    <StatusRail items={railFacts(blotterError ? null : allRows, market, sleeves.length > 0)} />
  );
  const back = (
    <Link
      to="/trading"
      className="inline-flex items-center gap-1 justify-self-start text-[12.5px] text-accent hover:underline"
    >
      <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
      Sessions
    </Link>
  );

  if (detailError && !detail) {
    return (
      <>
        {rail}
        <div className="page grid gap-3.5">
          {back}
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
      </>
    );
  }

  if (!detail || !row) {
    return (
      <>
        {rail}
        <div className="page grid gap-3.5" aria-busy="true">
          {back}
          <SkeletonFigure />
          <div className="grid gap-3.5 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <div className="rounded-panel border border-line bg-panel p-4">
              <SkeletonChart height={170} />
            </div>
            <div className="rounded-panel border border-line bg-panel">
              <SkeletonRows rows={4} cols={2} />
            </div>
          </div>
        </div>
      </>
    );
  }

  const { session, positions, orders: sessionOrders, execution, curve } = detail;
  const f = row.figures;
  const started = toDate(session.startedAt);
  const ended = toDate(session.endedAt) ?? (row.view.open ? null : toDate(execution?.stoppedAt));
  const meta = [
    row.version ? `Version ${row.version}` : null,
    row.rebalance ? row.rebalance.toLowerCase() : null,
    ended
      ? `ran ${sinceLabel(started)} to ${sinceLabel(ended)}`
      : row.state === 'running' || row.state === 'frozen'
        ? `running since ${sinceLabel(started)}`
        : `started ${sinceLabel(started)}`,
  ]
    .filter(Boolean)
    .join(' · ');

  const held = positions
    .map((p) => ({ p, value: toNumber(p.marketValue) }))
    .filter((x) => toNumber(x.p.quantity) !== 0)
    .sort((a, b) => b.value - a.value);
  const filled = sessionOrders
    .filter((o) => o.status === OrderStatus.FILLED || o.status === OrderStatus.PARTIAL)
    .map((o) => ({ o, at: toDate(o.filledAt) ?? toDate(o.submittedAt) ?? toDate(o.createdAt) }))
    .filter((x): x is { o: (typeof sessionOrders)[number]; at: Date } => x.at !== null)
    .sort((a, b) => b.at.getTime() - a.at.getTime());
  const lastDay = filled[0] ? etDay(filled[0].at) : null;
  const lastRebalance = filled.filter((x) => etDay(x.at) === lastDay).reverse();
  const cash = row.sleeve?.cash ? toNumber(row.sleeve.cash.balance) : null;
  const equityForWeights = f.equity ?? held.reduce((s, x) => s + x.value, 0) + (cash ?? 0);

  const curvePoints = curve
    .map((p) => ({ d: toDate(p.timestamp), v: toNumber(p.equity) }))
    .filter((x): x is { d: Date; v: number } => x.d !== null && Number.isFinite(x.v) && x.v > 0);

  const log: LogEntry[] = [
    ...(started
      ? [{ at: started, text: <b className="font-medium text-fg">Session started.</b> }]
      : []),
    ...sessionOrders
      .map((o): LogEntry | null => {
        const at = toDate(o.filledAt) ?? toDate(o.submittedAt) ?? toDate(o.createdAt);
        if (!at) return null;
        const side = sideWord(o.side);
        const n = qty(toNumber(o.filledQuantity) || toNumber(o.quantity));
        const notSent = o.status === OrderStatus.REJECTED && !o.submittedAt?.seconds;
        const text = notSent ? (
          <>
            <b className="font-medium text-risk">
              {side} {n} {o.symbol} not sent.
            </b>{' '}
            {asSentence(o.statusMessage)}
          </>
        ) : o.status === OrderStatus.FILLED ? (
          <>
            {side} {n} {o.symbol} filled at {formatNumber(toNumber(o.averageFillPrice))}.
          </>
        ) : (
          <>
            {side} {qty(toNumber(o.quantity))} {o.symbol}:{' '}
            {asSentence(o.statusMessage) || 'placed.'}
          </>
        );
        return { at, text };
      })
      .filter((x): x is LogEntry => x !== null),
    ...(ended
      ? [{ at: ended, text: <b className="font-medium text-fg">Session stopped.</b> }]
      : []),
  ]
    .sort((a, b) => b.at.getTime() - a.at.getTime())
    .slice(0, 12);

  const largest = held[0]?.value ?? 0;

  return (
    <>
      {rail}
      <div className="page grid gap-3.5">
        {back}
        <SessionHeader
          name={row.name}
          meta={meta}
          state={row.state}
          view={row.view}
          reason={row.state === 'error' ? execution?.errorMessage || undefined : undefined}
          aside={
            row.state === 'paused' || row.state === 'frozen'
              ? `${held.length} ${held.length === 1 ? 'position' : 'positions'} held`
              : undefined
          }
          strategyId={session.strategyId}
          pending={commandPending}
          onCommand={onCommand}
        />
        {commandError && (
          <p role="alert" className="m-0 text-[12.5px] text-risk">
            {commandError}
          </p>
        )}
        <p className="m-0 max-w-[980px] text-[13.5px] text-fg-2">
          {statusSentence({
            holdings: held.map((x) => ({ symbol: x.p.symbol, value: x.value })),
            rebalance: row.rebalance,
            open: row.view.open,
            lastOrder: filled[0]?.at ?? null,
            next: rowNextRebalance(row, etToday()),
          })}
        </p>

        <div className="grid items-start gap-3.5 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <div className="grid min-w-0 gap-3.5">
            <Panel>
              <Cells
                cols={4}
                cells={[
                  {
                    label: 'Sleeve equity',
                    value: f.equity === null ? '·' : <Money value={f.equity} />,
                    sub: execution?.allocatedCapital
                      ? `allocated ${formatMoney(toNumber(execution.allocatedCapital))}`
                      : undefined,
                  },
                  {
                    label: 'Today',
                    value: f.today === null ? '·' : <Money value={f.today} pnl />,
                    sub: f.todayPct === null ? undefined : <Pct value={f.todayPct} pnl />,
                  },
                  {
                    label: 'Total P&L',
                    value: f.total === null ? '·' : <Money value={f.total} pnl />,
                    sub: f.totalPct === null ? undefined : <Pct value={f.totalPct} pnl />,
                  },
                  {
                    label: 'Cash',
                    value: cash === null ? '·' : <Money value={cash} />,
                    sub:
                      f.cashShare === null
                        ? undefined
                        : `${formatPct(f.cashShare, { dp: 1 })} of sleeve`,
                  },
                ]}
              />
              <div className="px-3.5 py-3">
                {curvePoints.length > 1 ? (
                  <LineChart
                    label={`${row.name} equity today`}
                    dates={curvePoints.map((x) => x.d)}
                    series={[{ values: curvePoints.map((x) => x.v), kind: 'main', area: true }]}
                    height={170}
                    xFormat={(d) => etTime(d).slice(0, 5)}
                    yFormat={(v) => formatMoney(v, { dp: 0 })}
                    tooltip={(i) => (
                      <>
                        <b className="block font-medium text-fg-3">{etTime(curvePoints[i].d)} ET</b>
                        {formatMoney(curvePoints[i].v)}
                      </>
                    )}
                  />
                ) : (
                  <p className="m-0 grid h-[120px] place-items-center text-center text-[12.5px] text-fg-3">
                    No equity points yet today. They appear once the market opens and the session is
                    valued.
                  </p>
                )}
              </div>
            </Panel>

            <Panel title="Positions" aside="ledger quantities, IEX marks">
              {held.length === 0 ? (
                <p className="m-0 px-3.5 py-4 text-[12.5px] text-fg-3">
                  {row.view.open
                    ? 'No positions yet. The session holds cash until it rebalances.'
                    : 'No positions are held.'}
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className={T.table}>
                    <thead>
                      <tr>
                        <th className={T.th}>Symbol</th>
                        <th className={T.thN}>Qty</th>
                        <th className={T.thN}>Avg cost</th>
                        <th className={T.thN}>Last</th>
                        <th className={T.thN}>Market value</th>
                        <th className={T.thN}>Unrealised</th>
                      </tr>
                    </thead>
                    <tbody>
                      {held.map(({ p, value }) => (
                        <tr key={p.symbol}>
                          <td className={`${T.td} ${T.sym}`}>{p.symbol}</td>
                          <td className={T.tdN}>{qty(toNumber(p.quantity))}</td>
                          <td className={T.tdN}>{formatNumber(toNumber(p.averageEntryPrice))}</td>
                          <td className={T.tdN}>{formatNumber(toNumber(p.currentPrice))}</td>
                          <td className={T.tdN}>{formatNumber(value)}</td>
                          <td className={T.tdN}>
                            <Money value={toNumber(p.unrealizedPnl)} pnl />
                          </td>
                        </tr>
                      ))}
                      {cash !== null && (
                        <tr className="text-fg-3">
                          <td className={T.td}>Cash</td>
                          <td className={T.tdN} colSpan={3} />
                          <td className={T.tdN}>{formatNumber(cash)}</td>
                          <td className={T.tdN} />
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>

            <Panel
              title="Last rebalance"
              aside={
                lastRebalance.length
                  ? `${DAYS[etParts(lastRebalance[0].at).weekday]} ${etDay(lastRebalance[0].at)} · ${lastRebalance.length} ${lastRebalance.length === 1 ? 'order' : 'orders'} filled`
                  : undefined
              }
            >
              {lastRebalance.length === 0 ? (
                <p className="m-0 px-3.5 py-4 text-[12.5px] text-fg-3">No filled orders yet.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className={T.table}>
                    <thead>
                      <tr>
                        <th className={T.th}>Time, ET</th>
                        <th className={T.th}>Side</th>
                        <th className={T.th}>Symbol</th>
                        <th className={T.thN}>Filled</th>
                        <th className={T.thN}>Avg fill</th>
                      </tr>
                    </thead>
                    <tbody>
                      {lastRebalance.map(({ o, at }) => (
                        <tr key={o.id} className="cursor-pointer hover:bg-sunk">
                          <td className={`${T.td} num text-fg-3`}>
                            <Link to={`/trading/orders/${o.id}`} className="hover:underline">
                              {etTime(at)}
                            </Link>
                          </td>
                          <td className={T.td}>
                            <SideTag side={sideWord(o.side)} />
                          </td>
                          <td className={`${T.td} ${T.sym}`}>{o.symbol}</td>
                          <td className={T.tdN}>
                            {qty(toNumber(o.filledQuantity))} / {qty(toNumber(o.quantity))}
                          </td>
                          <td className={T.tdN}>{formatNumber(toNumber(o.averageFillPrice))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
          </div>

          <div className="grid min-w-0 gap-3.5">
            <Panel title="Weights" aside="share of sleeve equity">
              <div className="grid gap-1 px-3.5 py-3">
                {equityForWeights > 0 && (held.length > 0 || cash) ? (
                  <>
                    {[
                      ...held.map((x) => ({ k: x.p.symbol, v: x.value, cash: false })),
                      ...(cash ? [{ k: 'Cash', v: cash, cash: true }] : []),
                    ].map((w) => (
                      <div
                        key={w.k}
                        className="grid grid-cols-[46px_minmax(0,1fr)_52px] items-center gap-2.5 py-1.5 text-xs"
                      >
                        <span className={w.cash ? 'text-fg-2' : T.sym}>{w.k}</span>
                        <WeightBar
                          weight={w.v / equityForWeights}
                          height={6}
                          label={`${w.k} weight`}
                          color={w.cash ? 'rgb(var(--chart-4))' : 'rgb(var(--chart-2))'}
                        />
                        <span className="num text-right">
                          {formatPct(w.v / equityForWeights, { dp: 1 })}
                        </span>
                      </div>
                    ))}
                    <p className="m-0 mt-2 text-[11px] text-fg-3">
                      Target weights aren&apos;t available yet, so the bars show current weights
                      only.
                    </p>
                  </>
                ) : (
                  <p className="m-0 text-[12.5px] text-fg-3">
                    Weights appear once the sleeve holds something.
                  </p>
                )}
              </div>
            </Panel>

            <Panel title="Session limits">
              <div className="px-3.5 py-1">
                <KvList
                  rows={[
                    [
                      'Order value',
                      `up to ${formatMoney(DEFAULT_RISK_LIMITS.maxOrderValue, { dp: 0 })}`,
                    ],
                    [
                      'Largest position',
                      <span key="p" className="num">
                        {formatMoney(largest, { dp: 0 })} of{' '}
                        {formatMoney(DEFAULT_RISK_LIMITS.maxPositionSize, { dp: 0 })}
                      </span>,
                    ],
                    [
                      'Daily loss',
                      `up to ${formatMoney(DEFAULT_RISK_LIMITS.maxDailyLoss, { dp: 0 })}`,
                    ],
                    ['Order rate', `${DEFAULT_RISK_LIMITS.ordersPerMinute} a minute`],
                  ]}
                />
                <p className="m-0 pb-2 pt-1 text-[11px] text-fg-3">
                  Default limits. If your account has its own, those apply; they can&apos;t be
                  viewed here yet.
                </p>
              </div>
            </Panel>

            <Panel title="Session log" aside="from orders and session events">
              {log.length === 0 ? (
                <p className="m-0 px-3.5 py-4 text-[12.5px] text-fg-3">
                  Nothing has happened in this session yet.
                </p>
              ) : (
                <ol className="m-0 list-none p-0 text-xs">
                  {log.map((l, i) => (
                    <li
                      key={i}
                      className="grid grid-cols-[86px_1fr] gap-2.5 border-b border-line px-3.5 py-1.5 last:border-b-0"
                    >
                      <span className="num text-[11.5px] text-fg-3">
                        {etDay(l.at)} {etTime(l.at).slice(0, 5)}
                      </span>
                      <span className="text-fg-2">{l.text}</span>
                    </li>
                  ))}
                </ol>
              )}
            </Panel>
          </div>
        </div>
      </div>
    </>
  );
}
