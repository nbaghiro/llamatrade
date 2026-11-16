import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { useMemo, type MouseEvent } from 'react';

import {
  gridCellKey,
  groupRebalances,
  longDate,
  monthLabel,
  monthlyReturnsFromMap,
  rebalancesInMonth,
  tradesToOrders,
  type TradeInput,
} from '../../lib/backtestView';
import { formatMoney, formatNumber } from '../../lib/format';
import { MonthlyGrid } from '../charts';
import { EmptyState } from '../ui/EmptyState';
import { Money, Pct } from '../ui/Num';
import { SkeletonRows } from '../ui/Skeleton';

import { Panel, SideTag } from './parts';
import { T } from './tableStyles';

interface MonthByMonthProps {
  run: BacktestRun;
  /** Every trade of the run; null while loading. */
  trades: readonly TradeInput[] | null;
  month: string | null;
  onMonth: (month: string) => void;
}

const day = (iso: string) => longDate(new Date(`${iso}T00:00:00Z`));

/** The monthly grid as an index: pick a month to list its rebalances and orders. */
export function MonthByMonth({ run, trades, month, onMonth }: MonthByMonthProps) {
  const months = useMemo(
    () => monthlyReturnsFromMap(run.results?.monthlyReturns ?? {}),
    [run.results?.monthlyReturns]
  );
  const returnOf = (key: string) => run.results?.monthlyReturns?.[key];
  const rebalances = useMemo(
    () => (trades ? groupRebalances(tradesToOrders(trades)) : []),
    [trades]
  );
  const picked = month ? rebalancesInMonth(rebalances, month) : [];
  const orders = picked.flatMap((r) => r.orders);
  const realised = picked.reduce((s, r) => s + r.realised, 0);
  const totalOrders = rebalances.reduce((s, r) => s + r.orders.length, 0);

  // MonthlyGrid renders year rows with twelve month cells after the year header.
  const onGridClick = (e: MouseEvent<HTMLDivElement>) => {
    const td = (e.target as HTMLElement).closest('td');
    const year = td?.parentElement?.querySelector('th')?.textContent;
    const m = td ? td.cellIndex - 1 : -1;
    if (!td?.title || !year || m < 0 || m > 11) return;
    onMonth(`${year}-${String(m + 1).padStart(2, '0')}`);
  };

  const monthReturn = month ? returnOf(month) : undefined;

  return (
    <div className="grid gap-3.5">
      <Panel title="Monthly returns, %" aside="pick a month to see its rebalances and orders">
        <div
          className="cursor-pointer px-3.5 py-3 [&_td[title]:hover]:outline [&_td[title]:hover]:outline-1 [&_td[title]:hover]:outline-line-strong"
          onClick={onGridClick}
        >
          {months.length ? (
            <MonthlyGrid months={months} selected={month ? gridCellKey(month) : undefined} />
          ) : (
            <p className="m-0 text-[12.5px] text-fg-3">This run has no monthly returns.</p>
          )}
        </div>
      </Panel>
      <div className="grid items-start gap-3.5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)]">
        <Panel title="Rebalances" aside="newest first">
          {trades === null ? (
            <SkeletonRows rows={6} cols={4} />
          ) : rebalances.length === 0 ? (
            <EmptyState
              title="No orders in this run"
              body="The strategy held its starting position throughout."
            />
          ) : (
            <div className="max-h-[420px] overflow-y-auto">
              <div className="grid grid-cols-[92px_minmax(0,1fr)_52px_70px] gap-2.5 px-3.5 py-2 text-[11px] text-fg-3">
                <span>Date</span>
                <span>Branch</span>
                <span className="text-right">Orders</span>
                <span className="text-right">Month</span>
              </div>
              <ul className="m-0 list-none p-0">
                {rebalances.map((r) => {
                  const ret = returnOf(r.month);
                  const on = r.month === month;
                  return (
                    <li key={r.date}>
                      <button
                        type="button"
                        aria-pressed={on}
                        onClick={() => onMonth(r.month)}
                        className={`grid h-[34px] w-full grid-cols-[92px_minmax(0,1fr)_52px_70px] items-center gap-2.5 border-t border-line px-3.5 text-left text-[12.5px] hover:bg-sunk ${
                          on ? 'bg-accent-soft shadow-[inset_2px_0_0_rgb(var(--accent))]' : ''
                        }`}
                      >
                        <span className="num text-fg-2">{r.date}</span>
                        <span className="truncate text-fg-2">{r.branch || '·'}</span>
                        <span className="num text-right">{r.orders.length}</span>
                        <span className="text-right">
                          {ret === undefined ? (
                            <span className="text-fg-3">·</span>
                          ) : (
                            <Pct value={ret} pnl dp={1} />
                          )}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </Panel>
        <Panel
          title={
            !month
              ? 'Pick a month'
              : picked.length === 1
                ? `${day(picked[0].date)}${picked[0].branch ? ` · ${picked[0].branch}` : ''}`
                : `${monthLabel(month)}${picked.length ? ` · ${picked.length} rebalances` : ''}`
          }
          aside={
            month && (
              <span className="num">
                {orders.length} orders
                {monthReturn !== undefined && (
                  <>
                    {' · '}
                    {monthLabel(month)} <Pct value={monthReturn} pnl dp={1} />
                  </>
                )}
              </span>
            )
          }
          footer={
            month && orders.length > 0 ? (
              <span className="flex justify-between gap-3">
                <span>
                  Realised this month <Money value={realised} pnl />
                </span>
                <span className="text-fg-3">
                  {formatNumber(totalOrders, { dp: 0 })} orders in the run
                </span>
              </span>
            ) : undefined
          }
        >
          {trades === null ? (
            <SkeletonRows rows={4} cols={5} />
          ) : !month ? (
            <p className="m-0 px-3.5 py-4 text-[12.5px] text-fg-3">
              Choose a month in the grid or the list to see the orders it placed.
            </p>
          ) : orders.length === 0 ? (
            <p className="m-0 px-3.5 py-4 text-[12.5px] text-fg-2">
              No orders in {monthLabel(month)}. The strategy held its positions that month.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className={T.table}>
                <thead>
                  <tr>
                    <th className={T.th}>Date</th>
                    <th className={T.th}>Branch</th>
                    <th className={T.th}>Side</th>
                    <th className={T.th}>Symbol</th>
                    <th className={T.thN}>Qty</th>
                    <th className={T.thN}>Fill</th>
                    <th className={T.thN}>Value</th>
                    <th className={T.thN}>P&amp;L</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((o, i) => (
                    <tr key={`${o.date}-${o.symbol}-${o.side}-${i}`}>
                      <td className={`${T.td} num text-fg-2`}>{o.date}</td>
                      <td className={`${T.td} text-fg-2`}>{o.reason || '·'}</td>
                      <td className={T.td}>
                        <SideTag side={o.side} />
                      </td>
                      <td className={`${T.td} ${T.sym}`}>{o.symbol}</td>
                      <td className={T.tdN}>
                        {formatNumber(o.quantity, { dp: Number.isInteger(o.quantity) ? 0 : 2 })}
                      </td>
                      <td className={T.tdN}>{formatNumber(o.price)}</td>
                      <td className={T.tdN}>{formatMoney(o.value)}</td>
                      <td className={T.tdN}>
                        {o.pnl === null ? (
                          <span className="text-fg-3">·</span>
                        ) : (
                          <Money value={o.pnl} pnl />
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
