import type { ActivityRow } from '@llamatrade/core/stores/activity';
import type { SleeveDetail } from '@llamatrade/core/stores/portfolio';
import { useMemo } from 'react';

import { formatMoney, formatNumber, formatPct } from '../../lib/format';
import { etClock } from '../../lib/marketClock';
import { weightRows } from '../../lib/portfolioView';
import { AnnotatedCurve, type CurveLane, type CurvePin } from '../charts';
import { etToday, isDaily, nextRun, relativeDay } from '../sessions/sessionRows';
import { StatList } from '../ui';

import {
  allocationSteps,
  byDay,
  estimateRebalance,
  etDayKey,
  maxDrawdown,
  valueAt,
  type SleeveFill,
} from './history';
import { shortDate, sleeveRunState } from './sleeveView';
import type { SleeveCurve as Curve } from './useEquityCurves';

const DAY = 86_400_000;
const MAX_HOLDING_LANES = 7;

interface SleeveCurveProps {
  sleeve: SleeveDetail;
  curve: Curve | null;
  fills: readonly SleeveFill[];
  rows: readonly ActivityRow[];
  now: Date;
}

const sharesText = (q: number) => formatNumber(q, { dp: q % 1 ? 2 : 0 });

/** One sleeve's value against SPY, a lane per holding and a cash lane (sleeve2 A). */
export function SleeveCurve({ sleeve, curve, fills, rows, now }: SleeveCurveProps) {
  const t = now.getTime();
  const today = etToday(now);
  const series = useMemo(() => {
    const points = [...(curve?.points ?? []), { t, v: sleeve.value }];
    const bench = curve?.benchmark ?? [];
    const benchmark = bench.length
      ? points.map((p) => valueAt(bench, p.t) ?? bench[0].v)
      : undefined;
    return {
      dates: points.map((p) => new Date(p.t)),
      values: points.map((p) => p.v),
      benchmark,
    };
  }, [curve, sleeve.value, t]);

  const state = sleeveRunState(sleeve);
  const next = state === 'running' ? nextRun(sleeve.rebalance, now) : null;
  const daily = isDaily(sleeve.rebalance);
  const futureEnd = new Date(
    Math.max(today.getTime() + 15 * DAY, (next?.getTime() ?? 0) + 3 * DAY)
  );
  const estimates = next ? estimateRebalance(sleeve.holdings, sleeve.targets, sleeve.value) : [];
  const estimateOf = new Map(estimates.map((e) => [e.symbol, e]));

  const rowsBy = weightRows(sleeve.holdings, sleeve.value, sleeve.targets);
  const held = new Set(sleeve.holdings.map((h) => h.symbol));
  const soldOut = [...new Set(fills.map((f) => f.symbol))].filter((s) => !held.has(s));
  const symbols = [...rowsBy.map((r) => r.holding.symbol), ...soldOut];
  const shownSymbols = symbols.slice(0, MAX_HOLDING_LANES);
  const folded = symbols.slice(MAX_HOLDING_LANES);

  const marks = (list: readonly SleeveFill[]) =>
    list.map((f) => ({
      at: f.at,
      shape: f.side === 'buy' ? ('dot' as const) : ('ring' as const),
      title: `${f.side === 'buy' ? 'Bought' : 'Sold'} ${sharesText(f.qty)} ${f.symbol} at ${formatMoney(f.price)}`,
    }));

  const lanes: CurveLane[] = shownSymbols.map((symbol) => {
    const row = rowsBy.find((r) => r.holding.symbol === symbol);
    const est = estimateOf.get(symbol);
    return {
      id: symbol,
      label: <span className="font-mono font-semibold">{symbol}</span>,
      sub: row ? `${sharesText(row.holding.qty)} sh` : 'Sold',
      value: row
        ? `${(row.weight * 100).toFixed(1)}${row.target !== undefined ? `/${Math.round(row.target * 100)}` : '%'}`
        : undefined,
      tone: row ? 'default' : 'muted',
      events: marks(fills.filter((f) => f.symbol === symbol)),
      future:
        next && est
          ? {
              events: [
                {
                  at: next,
                  shape: 'planned',
                  title: `Estimated ${est.side} of ${est.qty}`,
                },
              ],
            }
          : next
            ? {
                events: [
                  { at: next, shape: 'planned', title: `Rebalance ${relativeDay(next, today)}` },
                ],
              }
            : undefined,
    };
  });
  if (folded.length) {
    lanes.push({
      id: 'more',
      label: `${folded.length} more`,
      sub: folded.join(' '),
      tone: 'muted',
      events: marks(fills.filter((f) => folded.includes(f.symbol))),
    });
  }
  const allocations = allocationSteps(rows, sleeve.sleeveName || sleeve.name);
  lanes.push({
    id: 'cash',
    label: 'Cash',
    value: sleeve.cash !== null ? formatMoney(sleeve.cash) : undefined,
    events: allocations.map((a) => ({
      at: new Date(a.t),
      shape: 'diamondFilled',
      title: `${formatMoney(a.amount)} added`,
      text: `+${formatMoney(a.amount, { dp: 0 })}`,
    })),
  });

  const pins: CurvePin[] = allocations.map((a, i) => ({
    at: new Date(a.t),
    label: `${i === 0 ? 'Started with' : 'Topped up'} ${formatMoney(a.amount, { dp: 0 })}`,
  }));
  const todayKey = etDayKey(now);
  const todays = fills.filter((f) => etDayKey(f.at) === todayKey);
  if (todays.length) {
    pins.push({
      at: todays[todays.length - 1].at,
      label: `Fills at ${etClock(todays[todays.length - 1].at)}`,
      tone: 'accent',
      count: todays.length,
      guide: false,
    });
  }

  const first = series.values[0];
  const last = series.values[series.values.length - 1];
  const bench = series.benchmark;
  const vsSpy =
    bench && first > 0 && bench[0] > 0
      ? (last / first - bench[bench.length - 1] / bench[0]) * 100
      : null;
  const dd = maxDrawdown(series.values);
  const stats = [
    ...(vsSpy !== null
      ? [
          {
            label: 'vs SPY',
            value: `${formatNumber(vsSpy, { signed: true })} pts`,
            tone: vsSpy >= 0 ? ('gain' as const) : ('loss' as const),
          },
        ]
      : []),
    { label: 'Max drawdown', value: formatPct(dd) },
    { label: 'Rebalances', value: String(byDay(fills).length) },
    { label: 'Fills', value: String(fills.length) },
  ];

  if (series.dates.length < 2) {
    return (
      <p className="m-0 py-6 text-[12.5px] text-fg-3">
        The curve appears once this sleeve has a second day of history.
      </p>
    );
  }

  return (
    <AnnotatedCurve
      label={`${sleeve.name} value against SPY`}
      dates={series.dates}
      values={series.values}
      benchmark={bench}
      end={now}
      now={{ label: `Now ${etClock(now)}` }}
      future={{
        end: futureEnd,
        title: next
          ? daily
            ? `Each trading day, next ${relativeDay(next, today)}`
            : `Rebalance ${relativeDay(next, today)}`
          : state === 'stopped'
            ? 'Stopped'
            : 'Next',
        content: next ? (
          estimates.length ? (
            <div className="grid gap-1">
              <span className="text-fg-3">Estimated from {etClock(now)} prices</span>
              {estimates.map((e) => (
                <span key={e.symbol} className="flex items-center gap-1.5">
                  <span className="rounded-[3px] border border-line-strong px-1 font-mono text-[10px] uppercase">
                    {e.side}
                  </span>
                  {e.qty} {e.symbol} · {formatMoney(e.amount)}
                </span>
              ))}
            </div>
          ) : (
            <span className="text-fg-3">
              {Object.keys(sleeve.targets).length
                ? 'Weights are close to target, so little is expected to trade.'
                : 'The orders depend on the strategy’s signals on the day.'}
            </span>
          )
        ) : (
          <span className="text-fg-3">
            {state === 'stopped'
              ? 'Holding cash. No rebalances are scheduled.'
              : state === 'frozen'
                ? 'Held until the ledger and Alpaca agree.'
                : 'No fixed schedule.'}
          </span>
        ),
      }}
      pins={pins}
      side={<StatList items={stats} />}
      lanes={lanes}
      legend={[
        { shape: 'dot', label: 'Buy' },
        { shape: 'ring', label: 'Sell' },
        { shape: 'diamondFilled', label: 'Money in' },
      ]}
      tooltip={(i) => (
        <span className="num">
          {shortDate(series.dates[i])} · {formatMoney(series.values[i])}
          {bench && <span className="text-fg-3"> · SPY {formatMoney(bench[i])}</span>}
        </span>
      )}
    />
  );
}
