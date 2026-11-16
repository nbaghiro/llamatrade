import { OrderType, TimeInForce } from '@llamatrade/core/proto/trading_pb';
import { toDate, toNumber, useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { ArrowLeft } from 'lucide-react';
import { useEffect, useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';

import { KvList, PageHead, Panel, SideTag } from '../../components/backtest/parts';
import {
  buildSessionRow,
  CheckLadder,
  outcomeOf,
  placedAt,
  sideWord,
} from '../../components/sessions';
import { PanelError } from '../../components/ui/PanelError';
import { SkeletonFigure, SkeletonRows } from '../../components/ui/Skeleton';
import { asSentence, formatMoney, formatNumber } from '../../lib/format';
import {
  DEFAULT_RISK_LIMITS,
  ORDER_OUTCOME_LABEL,
  stoppingChecks,
  type OrderOutcome,
} from '../../lib/sessionState';

const TYPE_LABEL: Partial<Record<OrderType, string>> = {
  [OrderType.MARKET]: 'market',
  [OrderType.LIMIT]: 'limit',
  [OrderType.STOP]: 'stop',
  [OrderType.STOP_LIMIT]: 'stop limit',
  [OrderType.TRAILING_STOP]: 'trailing stop',
};

const TIF_LABEL: Partial<Record<TimeInForce, string>> = {
  [TimeInForce.DAY]: 'day',
  [TimeInForce.GTC]: 'good till cancelled',
  [TimeInForce.IOC]: 'immediate or cancel',
  [TimeInForce.FOK]: 'fill or kill',
  [TimeInForce.OPG]: 'at the open',
  [TimeInForce.CLS]: 'at the close',
};

const TITLE: Record<OrderOutcome, string> = {
  stopped: 'Order not sent',
  rejected: 'Order rejected by Alpaca',
  filled: 'Order filled',
  partial: 'Order partly filled',
  open: 'Order open',
  closed: 'Order closed',
};

const qty = (v: number) => formatNumber(v, { dp: Number.isInteger(v) ? 0 : 2 });

/** /trading/orders/:orderId: the order on top, then the risk-check ladder. */
export default function OrderCheckPage() {
  const { orderId = '' } = useParams();
  const order = useTradingStore((s) => (s.order?.id === orderId ? s.order : null));
  const orderLoading = useTradingStore((s) => s.orderLoading);
  const orderError = useTradingStore((s) => s.orderError);
  const loadOrder = useTradingStore((s) => s.loadOrder);
  const loadBlotter = useTradingStore((s) => s.loadBlotter);
  const sessions = useTradingStore((s) => s.sessions);
  const orders = useTradingStore((s) => s.orders);
  const executions = useTradingStore((s) => s.executions);
  const sleeves = useTradingStore((s) => s.sleeves);
  const performance = useTradingStore((s) => s.performance);
  const strategies = useBacktestStore((s) => s.strategies);
  const fetchStrategies = useBacktestStore((s) => s.fetchStrategies);

  useEffect(() => {
    loadOrder(orderId).catch(() => undefined);
    loadBlotter().catch(() => undefined);
    fetchStrategies().catch(() => undefined);
  }, [orderId, loadOrder, loadBlotter, fetchStrategies]);

  const session = sessions.find((s) => s.id === order?.sessionId);
  const row = useMemo(
    () =>
      session
        ? buildSessionRow(session, { executions, sleeves, performance, strategies, orders })
        : null,
    [session, executions, sleeves, performance, strategies, orders]
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

  if (orderError && !order) {
    return (
      <div className="page grid gap-3.5">
        {back}
        <Panel>
          <PanelError
            title="This order couldn't be loaded"
            cause={orderError}
            onRetry={() => loadOrder(orderId)}
            retrying={orderLoading}
          />
        </Panel>
      </div>
    );
  }

  if (!order) {
    return (
      <div className="page grid gap-3.5" aria-busy="true">
        {back}
        <SkeletonFigure />
        <Panel>
          <SkeletonRows rows={7} cols={3} />
        </Panel>
      </div>
    );
  }

  const outcome = outcomeOf(order);
  const stopped = outcome === 'stopped';
  const checks = stopped ? stoppingChecks(order.statusMessage) : [];
  const quantity = toNumber(order.quantity);
  const price = toNumber(order.averageFillPrice) || toNumber(order.limitPrice);
  const placed = toDate(order.submittedAt) ?? toDate(order.createdAt);
  const name = row?.name ?? 'Session';
  const next = orders
    .filter((o) => o.sessionId === order.sessionId && o.id !== order.id)
    .map((o) => ({ o, at: toDate(o.submittedAt) ?? toDate(o.createdAt) }))
    .filter(
      (x): x is { o: (typeof orders)[number]; at: Date } =>
        x.at !== null && placed !== null && x.at >= placed
    )
    .sort((a, b) => a.at.getTime() - b.at.getTime())
    .slice(0, 5);

  return (
    <div className="page grid gap-3.5">
      {back}
      <PageHead
        title={TITLE[outcome]}
        meta={`${name}${row?.version ? ` · version ${row.version}` : ''} · ${placedAt(order)} ET`}
        actions={
          order.sessionId && (
            <Link to={`/trading/${order.sessionId}`} className="btn btn-secondary">
              View session
            </Link>
          )
        }
      />
      <div className="grid items-start gap-3.5 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <Panel
          tone={stopped ? 'risk' : 'plain'}
          footer={
            stopped ? (
              <>
                <b className="font-semibold text-risk">Not sent.</b>{' '}
                {asSentence(order.statusMessage) ||
                  'The order was stopped before it reached Alpaca.'}{' '}
                The full list of check results isn&apos;t recorded yet, so only the stopping check
                is marked.
              </>
            ) : outcome === 'rejected' ? (
              <>
                <b className="font-semibold text-risk">Rejected by Alpaca.</b>{' '}
                {asSentence(order.statusMessage)}
              </>
            ) : (
              <>
                {ORDER_OUTCOME_LABEL[outcome]}. Per-check results aren&apos;t recorded yet, so the
                ladder lists the checks without marking them.
              </>
            )
          }
        >
          <div className="flex flex-wrap items-center gap-4 border-b border-line px-3.5 py-3 text-[13px]">
            <SideTag side={sideWord(order.side)} />
            <b className="font-mono font-semibold">{order.symbol}</b>
            <span className="num">
              {qty(quantity)}
              {price ? ` × ${formatMoney(price)}` : ''}
            </span>
            {price > 0 && (
              <span className="num text-fg-3">order {formatMoney(quantity * price)}</span>
            )}
            <span className="num ml-auto text-fg-3">
              {[TYPE_LABEL[order.type], TIF_LABEL[order.timeInForce]].filter(Boolean).join(' · ')}
            </span>
          </div>
          <CheckLadder stopped={checks} />
        </Panel>
        <div className="grid gap-3.5">
          <Panel title="Session limits" aside={name}>
            <div className="px-3.5 py-1">
              <KvList
                rows={[
                  ['Order value', formatMoney(DEFAULT_RISK_LIMITS.maxOrderValue, { dp: 0 })],
                  ['Position size', formatMoney(DEFAULT_RISK_LIMITS.maxPositionSize, { dp: 0 })],
                  ['Daily loss', formatMoney(DEFAULT_RISK_LIMITS.maxDailyLoss, { dp: 0 })],
                  ['Order rate', `${DEFAULT_RISK_LIMITS.ordersPerMinute} a minute`],
                ]}
              />
              <p className="m-0 pb-2 pt-1 text-[11px] text-fg-3">
                Default limits. If your account has its own, those apply; they can&apos;t be viewed
                here yet.
              </p>
            </div>
          </Panel>
          <Panel title="What happened next">
            {next.length === 0 ? (
              <p className="m-0 px-3.5 py-4 text-[12.5px] text-fg-3">
                No later orders in this session.
              </p>
            ) : (
              <ol className="m-0 list-none p-0 text-xs">
                {next.map(({ o }) => {
                  const out = outcomeOf(o);
                  const risk = out === 'stopped' || out === 'rejected';
                  return (
                    <li
                      key={o.id}
                      className={`grid grid-cols-[96px_1fr] gap-2.5 border-b border-line px-3.5 py-1.5 last:border-b-0 ${risk ? 'bg-risk-soft' : ''}`}
                    >
                      <span className="num text-[11.5px] text-fg-3">
                        {placedAt(o).split(' ').slice(2).join(' ')}
                      </span>
                      <Link
                        to={`/trading/orders/${o.id}`}
                        className={`hover:underline ${risk ? 'font-medium text-risk' : 'text-fg-2'}`}
                      >
                        {sideWord(o.side)} {qty(toNumber(o.quantity))} {o.symbol}:{' '}
                        {ORDER_OUTCOME_LABEL[out].toLowerCase()}
                        {out === 'filled'
                          ? ` at ${formatNumber(toNumber(o.averageFillPrice))}`
                          : ''}
                        .
                      </Link>
                    </li>
                  );
                })}
              </ol>
            )}
          </Panel>
          <p className="m-0 text-xs text-fg-3">
            If the ledger can&apos;t confirm the sleeve&apos;s state, the order is stopped. A
            missing answer never counts as a pass.
          </p>
        </div>
      </div>
    </div>
  );
}
