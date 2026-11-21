import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { useMemo, type ReactNode } from 'react';

import {
  groupRebalances,
  longDate,
  monthLabel,
  tradesToOrders,
  type Rebalance,
  type SimOrder,
  type TradeInput,
} from '../../lib/backtestView';
import { formatMoney, formatNumber } from '../../lib/format';
import { EmptyState } from '../ui/EmptyState';
import { Money, Pct } from '../ui/Num';
import { PageHead } from '../ui/PageHead';
import { SkeletonRows } from '../ui/Skeleton';
import { Segmented } from '../ui/Tabs';

import { Panel, SideTag } from './parts';
import { runMeta } from './runData';
import { YearCurve } from './YearCurve';
import {
  changesLine,
  kindOf,
  monthBounds,
  monthDetailTitle,
  monthGroups,
  periodReturn,
  reasonsOf,
  sliceYear,
  switchDays,
  useFullCurve,
  yearBounds,
  yearCounts,
  type MonthGroup,
  type RebalanceKind,
} from './yearView';

interface MonthPartsProps {
  /** Twelve months of the shown year; null while the trades load. */
  groups: readonly MonthGroup[] | null;
  switches: ReadonlySet<string>;
  month: string | null;
  /** The picked month's return, when the run reports one. */
  monthReturn: number | null;
  onMonth: (month: string) => void;
}

const MAX_CARD_LINES = 4;
const KV = 'flex justify-between gap-3 border-b border-line py-[7px] text-[12.5px] last:border-b-0';
const asDay = (iso: string) => new Date(`${iso}T00:00:00Z`);
const shortDay = (iso: string) =>
  asDay(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
const shortMonth = (month: string) =>
  asDay(`${month}-01`).toLocaleDateString('en-US', { month: 'short', timeZone: 'UTC' });
const shares = (n: number) => formatNumber(n, { dp: Number.isInteger(n) ? 0 : 2 });
const signedShares = (n: number) => `${n > 0 ? '+' : '−'}${shares(Math.abs(n))}`;

function KindTag({ kind }: { kind: RebalanceKind }) {
  return (
    <span
      className={`rounded-sm px-[5px] py-[3px] font-mono text-[10px] font-semibold uppercase leading-none ring-1 ring-inset ${
        kind === 'switch' ? 'text-accent ring-accent/45' : 'text-fg-2 ring-line-strong'
      }`}
    >
      {kind}
    </span>
  );
}

/** "Mar 1" for one rebalance, "Mar · 6 days" for several. */
function groupTitle(g: MonthGroup): string {
  if (g.rebalances.length === 1) return shortDay(g.rebalances[0].date);
  return `${shortMonth(g.month)}${g.rebalances.length ? ` · ${g.rebalances.length} days` : ''}`;
}

function OrderRows({ orders }: { orders: readonly SimOrder[] }) {
  return (
    <ul className="m-0 list-none p-0">
      {orders.map((o, i) => (
        <li
          key={`${o.symbol}-${o.side}-${i}`}
          className="flex items-center justify-between gap-3 py-[5px] text-[12.5px]"
        >
          <span className="flex items-center gap-2">
            <SideTag side={o.side} />
            <span className="num">{shares(o.quantity)}</span>
            <span className="font-mono font-semibold">{o.symbol}</span>
          </span>
          <span className="num text-fg-2">{formatMoney(o.value)}</span>
        </li>
      ))}
    </ul>
  );
}

function RebalanceBlock({ r, kind }: { r: Rebalance; kind: RebalanceKind }) {
  const reasons = reasonsOf([r]);
  return (
    <div className="border-b border-line px-3.5 py-2.5 last:border-b-0">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="num text-[12.5px] font-semibold">{longDate(asDay(r.date))}</span>
        <KindTag kind={kind} />
      </div>
      {reasons.length > 0 && (
        <p className="m-0 mb-1 text-[12px] leading-[1.5] text-fg-2">{reasons.join(' · ')}</p>
      )}
      <OrderRows orders={r.orders} />
    </div>
  );
}

/** The picked month's rebalances, closed P&L and return. */
export function MonthDetail({
  group,
  switches,
  monthReturn,
}: {
  group: MonthGroup;
  switches: ReadonlySet<string>;
  monthReturn: number | null;
}) {
  return (
    <>
      {group.rebalances.length === 0 ? (
        <p className="m-0 px-3.5 py-4 text-[12.5px] text-fg-2">
          No orders in {monthLabel(group.month)}. The strategy held its positions that month.
        </p>
      ) : (
        <div className="max-h-[460px] overflow-y-auto">
          {group.rebalances.map((r) => (
            <RebalanceBlock key={r.date} r={r} kind={kindOf(r, switches)} />
          ))}
        </div>
      )}
      <dl className="m-0 border-t border-line px-3.5 py-1">
        <div className={KV}>
          <dt className="text-fg-2">Closed P&amp;L</dt>
          <dd className="m-0">
            <Money value={group.realised} pnl />
          </dd>
        </div>
        <div className={KV}>
          <dt className="text-fg-2">{monthLabel(group.month)} return</dt>
          <dd className="m-0">
            {monthReturn === null ? (
              <span className="text-fg-3">·</span>
            ) : (
              <Pct value={monthReturn} pnl dp={1} />
            )}
          </dd>
        </div>
      </dl>
      <p className="m-0 border-t border-line px-3.5 py-2.5 text-[11.5px] leading-[1.5] text-fg-3">
        The backtest doesn&apos;t record indicator values at each rebalance, so the ranking behind
        these orders isn&apos;t shown. Commission is in the run&apos;s totals on the results page.
      </p>
    </>
  );
}

/** One card per month, summing that month's rebalance days, under the year curve. */
export function MonthCards({ groups, month, onMonth }: MonthPartsProps) {
  if (groups === null) return <SkeletonRows rows={2} cols={6} />;
  return (
    <div className="grid grid-cols-[112px_minmax(0,1fr)] gap-2">
      <p className="m-0 text-[11px] leading-[1.45] text-fg-3">
        Orders placed, in shares: + bought, − sold. One card per month.
      </p>
      <div className="grid grid-cols-6 gap-1.5 xl:grid-cols-12">
        {groups.map((g) => {
          const on = g.month === month;
          const more = g.changes.length - MAX_CARD_LINES;
          return (
            <button
              key={g.month}
              type="button"
              aria-pressed={on}
              disabled={g.orders === 0}
              onClick={() => onMonth(g.month)}
              className={`min-h-[96px] rounded-md border bg-panel px-2 py-1.5 text-left hover:border-line-strong disabled:cursor-default disabled:hover:border-line ${
                on ? 'border-accent shadow-[0_0_0_1px_rgb(var(--accent))]' : 'border-line'
              }`}
            >
              <span className="num block text-[11.5px] font-semibold">
                {g.rebalances.length === 1 ? shortDay(g.rebalances[0].date) : shortMonth(g.month)}
              </span>
              <span className="block text-[11px] text-fg-3">
                {g.kind === null ? (
                  'No orders'
                ) : (
                  <>
                    <span className={g.kind === 'switch' ? 'text-accent' : ''}>
                      {g.kind === 'switch' ? 'Switch' : 'Resize'}
                    </span>
                    {g.rebalances.length > 1 && ` · ${g.rebalances.length} days`}
                  </>
                )}
              </span>
              <span className="mt-1 block font-mono text-[11px] leading-[1.45] text-fg-2">
                {g.changes.slice(0, MAX_CARD_LINES).map((c) => (
                  <span key={c.symbol} className="block whitespace-nowrap">
                    {signedShares(c.shares)} {c.symbol}
                  </span>
                ))}
                {more > 0 && <span className="block text-fg-3">{more} more</span>}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** Phones: the year's months with orders, the picked one opened. */
export function MonthList({ groups, switches, month, monthReturn, onMonth }: MonthPartsProps) {
  if (groups === null) return <SkeletonRows rows={4} cols={2} />;
  const traded = groups.filter((g) => g.orders > 0);
  if (!traded.length) {
    return (
      <EmptyState title="No orders this year" body="The strategy held its positions all year." />
    );
  }
  return (
    <ul className="m-0 list-none p-0">
      {traded.map((g) => {
        const on = g.month === month;
        return (
          <li key={g.month} className="border-b border-line last:border-b-0">
            <button
              type="button"
              aria-expanded={on}
              onClick={() => onMonth(g.month)}
              className="flex w-full items-start justify-between gap-3 px-3.5 py-2.5 text-left"
            >
              <span className="min-w-0">
                <span className="block text-[13px] font-semibold">
                  {groupTitle(g)} · {g.kind === 'switch' ? 'switch' : 'resize'}
                </span>
                <span className="block truncate text-[11.5px] text-fg-3">
                  {changesLine(g.changes)}
                </span>
              </span>
              {on && monthReturn !== null && <Pct value={monthReturn} pnl dp={1} />}
            </button>
            {on && (
              <div className="border-t border-line">
                <MonthDetail group={g} switches={switches} monthReturn={monthReturn} />
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

interface MonthByMonthProps {
  run: BacktestRun;
  /** Every trade of the run; null while loading. */
  trades: readonly TradeInput[] | null;
  /** "2025-03"; the year shown is this month's. */
  month: string | null;
  onMonth: (month: string) => void;
  strategyName?: string;
  /** Buttons at the right of the header, e.g. CSV. */
  actions?: ReactNode;
}

/** One year of the run: the year's sentence, its curve with monthly returns and every rebalance. */
export function MonthByMonth({
  run,
  trades,
  month,
  onMonth,
  strategyName = 'Strategy',
  actions,
}: MonthByMonthProps) {
  const full = useFullCurve(run);
  const bench = runMeta(run).benchmark;
  const years = useMemo(
    () => [...new Set(full.dates.map((d) => String(d.getUTCFullYear())))],
    [full.dates]
  );
  const year = month?.slice(0, 4) ?? years[years.length - 1] ?? '';

  const rebalances = useMemo(
    () => (trades ? groupRebalances(tradesToOrders(trades)) : null),
    [trades]
  );
  const switches = useMemo(() => (trades ? switchDays(trades) : new Set<string>()), [trades]);
  const groups = useMemo(
    () => (rebalances ? monthGroups(rebalances, year, switches) : null),
    [rebalances, year, switches]
  );
  const picked = groups?.find((g) => g.month === month) ?? null;

  const monthReturnOf = (m: string): number | null => {
    const reported = run.results?.monthlyReturns?.[m];
    if (reported !== undefined) return reported;
    const { from, to } = monthBounds(m);
    return periodReturn(full.dates, full.values, from, to);
  };
  const monthReturn = month ? monthReturnOf(month) : null;

  const { from, to } = yearBounds(year);
  const yearReturn = periodReturn(full.dates, full.values, from, to);
  const benchReturn = full.bench ? periodReturn(full.dates, full.bench, from, to) : null;
  const yearRebalances = groups?.flatMap((g) => g.rebalances) ?? [];
  const switchCount = yearRebalances.filter((r) => switches.has(r.date)).length;
  const orderCount = groups?.reduce((s, g) => s + g.orders, 0) ?? 0;

  const sentence = (
    <span>
      {year} in this backtest
      {yearReturn !== null && (
        <>
          : <Pct value={yearReturn} pnl dp={1} />
          {benchReturn !== null && bench && (
            <>
              {' '}
              against {bench}&apos;s <Pct value={benchReturn} pnl dp={1} />
            </>
          )}
        </>
      )}
      .{' '}
      {groups === null
        ? 'Loading the orders…'
        : yearCounts(switchCount, yearRebalances.length - switchCount, orderCount)}
    </span>
  );

  const firstMonthOf = (y: string) => {
    const traded = rebalances
      ?.filter((r) => r.month.startsWith(y))
      .map((r) => r.month)
      .sort()[0];
    if (traded) return traded;
    const slice = sliceYear(full, y);
    return slice ? slice.dates[0].toISOString().slice(0, 7) : `${y}-01`;
  };

  return (
    <div className="grid gap-3.5">
      <PageHead
        title={strategyName}
        documentTitle={`${strategyName} · ${year}`}
        badges={
          <>
            <span className="rounded-sm px-[5px] py-[3px] font-mono text-[11px] leading-none text-fg-2 ring-1 ring-inset ring-line-strong">
              v{run.strategyVersion}
            </span>
            <span className="text-[12px] text-fg-3">Backtest</span>
          </>
        }
        sub={sentence}
        actions={
          <>
            {years.length > 1 && (
              <Segmented
                label="Year"
                value={year}
                onChange={(y) => onMonth(firstMonthOf(y))}
                options={years.map((y) => ({ key: y, label: y }))}
              />
            )}
            {actions}
          </>
        }
      />
      <div className="grid items-start gap-3.5 md:grid-cols-[minmax(0,1fr)_300px]">
        <div className="grid min-w-0 gap-3">
          <YearCurve
            run={run}
            full={full}
            trades={trades}
            year={year}
            month={month}
            strategyName={strategyName}
          />
          <div className="hidden md:block">
            <MonthCards
              groups={groups}
              switches={switches}
              month={month}
              monthReturn={monthReturn}
              onMonth={onMonth}
            />
          </div>
        </div>
        <Panel
          className="hidden md:block"
          title={picked ? monthDetailTitle(picked) : 'Pick a month'}
          aside={picked?.kind ? <KindTag kind={picked.kind} /> : undefined}
        >
          {groups === null ? (
            <SkeletonRows rows={4} cols={2} />
          ) : picked ? (
            <MonthDetail group={picked} switches={switches} monthReturn={monthReturn} />
          ) : (
            <p className="m-0 px-3.5 py-4 text-[12.5px] text-fg-3">
              Choose a month under the curve to see the orders it placed.
            </p>
          )}
        </Panel>
        <Panel title="Rebalances, by month" className="md:hidden">
          <MonthList
            groups={groups}
            switches={switches}
            month={month}
            monthReturn={monthReturn}
            onMonth={onMonth}
          />
        </Panel>
      </div>
    </div>
  );
}
