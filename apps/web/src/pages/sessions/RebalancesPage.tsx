import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { OrderSide } from '@llamatrade/core/proto/trading_pb';
import { toDate, toNumber, useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useEffect, useMemo } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';

import { Panel } from '../../components/backtest/parts';
import { AnnotatedCurve } from '../../components/charts';
import { buildSessionRow } from '../../components/sessions';
import {
  etDayLabel,
  etHm,
  fillDays,
  orderTime,
  quantitiesBefore,
  toSeries,
  windowed,
} from '../../components/sessions/timeline';
import { ModeBadge, PageHead } from '../../components/ui';
import { Money } from '../../components/ui/Num';
import { PanelError } from '../../components/ui/PanelError';
import { SkeletonChart } from '../../components/ui/Skeleton';
import { formatMoney, formatNumber } from '../../lib/format';

const DAY_MS = 86_400_000;
const qty = (v: number) => formatNumber(v, { dp: Number.isInteger(v) ? 0 : 2 });

/**
 * /trading/:sessionId/rebalances: every rebalance that traded on one axis, one opened beside it
 * (rebalance2 A). Weight history and the rule's inputs aren't stored, so the opened rebalance shows
 * shares before and after, rebuilt from fills.
 */
export default function RebalancesPage() {
  const { sessionId = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const detail = useTradingStore((s) => (s.detail?.session.id === sessionId ? s.detail : null));
  const detailError = useTradingStore((s) => s.detailError);
  const detailLoading = useTradingStore((s) => s.detailLoading);
  const loadSession = useTradingStore((s) => s.loadSession);
  const performance = useTradingStore((s) => s.performance);
  const strategies = useBacktestStore((s) => s.strategies);
  const fetchStrategies = useBacktestStore((s) => s.fetchStrategies);

  useEffect(() => {
    loadSession(sessionId, new Date(0)).catch(() => undefined);
    fetchStrategies().catch(() => undefined);
  }, [sessionId, loadSession, fetchStrategies]);

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
        <PageHead crumbs={[{ label: 'Sessions', to: '/trading' }]} title="Rebalances" />
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

  const { session, orders } = detail;
  const mode = session.mode === ExecutionMode.LIVE ? 'live' : 'paper';
  const now = new Date();
  const started = toDate(session.startedAt);
  const ended = row.view.open ? null : toDate(session.endedAt);
  const end = ended ?? now;
  const start = started ?? new Date(end.getTime() - 90 * DAY_MS);
  const series = windowed(
    toSeries(detail.curve),
    start,
    end,
    row.view.open ? row.figures.equity : null
  );
  const days = fillDays(orders);
  const wanted = params.get('day');
  const index = Math.max(0, wanted ? days.findIndex((d) => d.key === wanted) : days.length - 1);
  const day = days[index] ?? null;
  const select = (i: number) => {
    const d = days[i];
    if (!d) return;
    setParams(
      (p) => {
        const n = new URLSearchParams(p);
        n.set('day', d.key);
        return n;
      },
      { replace: true }
    );
  };
  const fillValue = (o: (typeof orders)[number]) =>
    toNumber(o.filledQuantity) * toNumber(o.averageFillPrice);
  const traded = days.reduce((n, d) => n + d.orders.reduce((m, o) => m + fillValue(o), 0), 0);

  const dayStart = day ? new Date(day.at.getTime() - 60_000) : null;
  const before = dayStart ? quantitiesBefore(orders, dayStart) : new Map<string, number>();
  const after = day
    ? quantitiesBefore(
        orders,
        new Date(Math.max(...day.orders.map((o) => orderTime(o)?.getTime() ?? 0)) + 1)
      )
    : new Map<string, number>();
  const symbols = [...new Set([...before.keys(), ...after.keys()])]
    .filter((s) => (before.get(s) ?? 0) !== 0 || (after.get(s) ?? 0) !== 0)
    .sort();

  return (
    <div className="page">
      <PageHead
        crumbs={[
          { label: 'Sessions', to: '/trading' },
          { label: row.name, to: `/trading/${sessionId}` },
          { label: 'Rebalances' },
        ]}
        title="Rebalances"
        documentTitle={`Rebalances · ${row.name}`}
        badges={<ModeBadge mode={mode} />}
        sub={`${days.length} ${days.length === 1 ? 'rebalance' : 'rebalances'} placed orders${
          started ? ` since ${etDayLabel(started)}` : ''
        }. Rebalances that placed no orders aren't recorded.`}
      />
      <div className="grid items-start gap-3.5 lg:grid-cols-[minmax(0,1fr)_400px]">
        <div className="panel-rim px-5 pb-3 pt-4">
          <div className="mb-2 text-[10.5px] font-medium uppercase tracking-[0.06em] text-fg-3">
            Sleeve value
          </div>
          {series.dates.length > 1 ? (
            <AnnotatedCurve
              label={`${row.name} sleeve value with its rebalances`}
              dates={series.dates}
              values={series.values}
              start={start}
              end={end}
              height={180}
              now={row.view.open ? { label: `Now ${etHm(now)}` } : undefined}
              pins={day ? [{ at: day.at, label: etDayLabel(day.at), tone: 'accent' }] : []}
              lanes={[
                {
                  id: 'rebalances',
                  label: 'Rebalances',
                  sub: `${days.length} placed orders`,
                  events: days.map((d, i) => ({
                    at: d.at,
                    shape: i === index ? ('dot' as const) : ('ring' as const),
                    count: i === index ? d.orders.length : undefined,
                    title: `${etDayLabel(d.at)}: ${d.orders.length} ${d.orders.length === 1 ? 'order' : 'orders'}`,
                  })),
                },
              ]}
              legend={[{ shape: 'ring', label: 'Rebalance that traded' }]}
            />
          ) : (
            <p className="m-0 py-10 text-center text-[12.5px] text-fg-3">
              The sleeve hasn&apos;t been valued yet.
            </p>
          )}
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-1.5">
              {days.map((d, i) => (
                <button
                  key={d.key}
                  type="button"
                  onClick={() => select(i)}
                  aria-pressed={i === index}
                  className={`rounded-full border px-2.5 py-0.5 font-mono text-[11px] ${
                    i === index
                      ? 'border-accent bg-accent-soft text-fg'
                      : 'border-line text-fg-2 hover:text-fg'
                  }`}
                >
                  {etDayLabel(d.at)}
                </button>
              ))}
            </div>
            {days.length > 1 && (
              <div className="flex gap-2">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={index === 0}
                  onClick={() => select(index - 1)}
                >
                  <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
                  Earlier
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={index >= days.length - 1}
                  onClick={() => select(index + 1)}
                >
                  Later
                  <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </div>
            )}
          </div>
          <dl className="m-0 mt-3 grid gap-3 sm:grid-cols-2">
            <div className="rounded-[8px] bg-sunk px-4 py-3">
              <dt className="text-[10.5px] font-medium uppercase tracking-[0.06em] text-fg-3">
                Traded{started ? ` since ${etDayLabel(started)}` : ''}
              </dt>
              <dd className="m-0 mt-1 font-mono text-[15px] font-semibold">
                {formatMoney(traded)}
              </dd>
            </div>
            <div className="rounded-[8px] bg-sunk px-4 py-3">
              <dt className="text-[10.5px] font-medium uppercase tracking-[0.06em] text-fg-3">
                Orders filled
              </dt>
              <dd className="m-0 mt-1 font-mono text-[15px] font-semibold">
                {days.reduce((n, d) => n + d.orders.length, 0)}
              </dd>
            </div>
          </dl>
        </div>

        <Panel
          title={day ? `${etDayLabel(day.at)}, ${etHm(day.at)}` : 'No rebalances yet'}
          aside={day ? `${day.orders.length} filled` : undefined}
        >
          {!day ? (
            <p className="m-0 px-3.5 py-4 text-[12.5px] text-fg-3">
              Nothing has traded yet. The first rebalance that places orders appears here.
            </p>
          ) : (
            <>
              <table className="w-full border-collapse text-[12.5px]">
                <thead>
                  <tr className="text-[10.5px] uppercase tracking-[0.06em] text-fg-3">
                    <th className="px-3.5 py-2 text-left font-medium">Shares</th>
                    <th className="px-3.5 py-2 text-right font-medium">Before</th>
                    <th className="px-3.5 py-2 text-right font-medium">After</th>
                  </tr>
                </thead>
                <tbody>
                  {symbols.map((s) => (
                    <tr key={s} className="border-t border-line">
                      <td className="px-3.5 py-2 font-mono font-semibold">{s}</td>
                      <td className="num px-3.5 py-2 text-right text-fg-2">
                        {qty(before.get(s) ?? 0)}
                      </td>
                      <td className="num px-3.5 py-2 text-right">{qty(after.get(s) ?? 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <ol className="m-0 list-none border-t border-line p-0">
                {day.orders.map((o) => (
                  <li key={o.id} className="border-b border-line last:border-b-0">
                    <Link
                      to={`/trading/orders/${o.id}`}
                      className="flex items-center gap-3 px-3.5 py-2.5 hover:bg-sunk"
                    >
                      <span className="rounded-sm px-[5px] py-[3px] font-mono text-[10px] font-semibold leading-none ring-1 ring-inset ring-line-strong">
                        {o.side === OrderSide.SELL ? 'SELL' : 'BUY'}
                      </span>
                      <span className="min-w-0 flex-1 truncate">
                        {qty(toNumber(o.filledQuantity))} {o.symbol} at{' '}
                        {formatMoney(toNumber(o.averageFillPrice))}
                      </span>
                      <Money value={fillValue(o)} className="text-[12.5px]" />
                    </Link>
                  </li>
                ))}
              </ol>
              <p className="m-0 border-t border-line px-3.5 py-2.5 text-[11.5px] text-fg-3">
                Shares are rebuilt from fills. The weights at the time, the target and the rule
                inputs for this check aren&apos;t stored yet.
              </p>
            </>
          )}
        </Panel>
      </div>
    </div>
  );
}
