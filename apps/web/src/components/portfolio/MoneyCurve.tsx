import type { ActivityRow } from '@llamatrade/core/stores/activity';
import type { SleeveSummary } from '@llamatrade/core/stores/portfolio';
import { useMemo } from 'react';

import { formatMoney } from '../../lib/format';
import { etClock } from '../../lib/marketClock';
import { nextRebalanceDate } from '../../lib/sessionState';
import { AnnotatedCurve, type CurveLane, type LaneEvent } from '../charts';
import { dayLabel, etToday } from '../sessions/sessionRows';
import { ModeBadge } from '../ui';

import {
  accountHistory,
  allocationSteps,
  byDay,
  freeCashSteps,
  windowFrom,
  type CashStep,
  type SleeveFill,
} from './history';
import { shortDate, sleeveColor, sleeveRunState } from './sleeveView';
import type { CurveMap } from './useEquityCurves';

export type MoneyRange = '1M' | '3M' | 'all';

const DAY = 86_400_000;
const RANGE_DAYS: Record<Exclude<MoneyRange, 'all'>, number> = { '1M': 31, '3M': 92 };
const MAX_LANES = 8;

interface MoneyCurveProps {
  sleeves: readonly SleeveSummary[];
  /** Paper unallocated cash, or null when unallocated cash isn't part of this view. */
  unallocated: number | null;
  rows: readonly ActivityRow[];
  fills: readonly SleeveFill[];
  curves: CurveMap;
  range: MoneyRange;
  now: Date;
}

const money0 = (v: number) => formatMoney(v, { dp: 0 });

function sleeveLane(
  s: SleeveSummary,
  index: number,
  rows: readonly ActivityRow[],
  fills: readonly SleeveFill[],
  today: Date,
  futureEnd: Date
): CurveLane {
  const state = sleeveRunState(s);
  const allocations = allocationSteps(rows, s.name);
  const own = fills.filter((f) => f.sleeveId === s.sleeveId);
  const events: LaneEvent[] = [
    ...allocations.map((a, i) => ({
      at: new Date(a.t),
      shape: 'diamondFilled' as const,
      title: `${formatMoney(a.amount)} in`,
      text: i === 0 ? `+${money0(a.amount)}` : undefined,
    })),
    ...byDay(own).map((d) => ({
      at: d.at,
      shape: 'ring' as const,
      title: `Rebalance, ${d.items.length} ${d.items.length === 1 ? 'fill' : 'fills'}`,
    })),
  ];
  const next = state === 'running' ? nextRebalanceDate(s.rebalance, today) : null;
  const stopped = state === 'stopped';
  return {
    id: s.executionId,
    label: (
      <span className="inline-flex min-w-0 items-center gap-1.5">
        <i
          aria-hidden="true"
          className="h-2 w-2 flex-none rounded-[2px]"
          style={{ background: sleeveColor(index) }}
        />
        <span className="truncate">{s.name}</span>
      </span>
    ),
    badge: <ModeBadge mode={s.live ? 'live' : 'paper'} size="sm" />,
    tone: state === 'frozen' ? 'risk' : stopped ? 'muted' : 'default',
    href: s.sleeveId ? `/portfolio/sleeves/${s.sleeveId}` : undefined,
    spans: s.startedAt ? [{ from: s.startedAt, style: stopped ? 'off' : 'on' }] : undefined,
    events,
    future: stopped
      ? { note: 'Stopped, holding cash' }
      : state === 'frozen'
        ? { note: 'Frozen until the counts agree' }
        : next && next <= futureEnd
          ? { events: [{ at: next, shape: 'planned', title: `Rebalance ${dayLabel(next)}` }] }
          : { note: next ? `Next ${dayLabel(next)}` : undefined },
  };
}

/** Total equity over a dashed step line of money added, with a lane per sleeve (overview2 A). */
export function MoneyCurve({
  sleeves,
  unallocated,
  rows,
  fills,
  curves,
  range,
  now,
}: MoneyCurveProps) {
  const today = etToday(now);
  const futureEnd = new Date(today.getTime() + 15 * DAY);

  const history = useMemo(() => {
    const t = now.getTime();
    const histories = sleeves.map((s) => ({
      points: [...(curves[s.executionId]?.points ?? []), { t, v: s.value }],
      allocations: allocationSteps(rows, s.name),
    }));
    let cash: CashStep[] = [];
    if (unallocated !== null) {
      cash = freeCashSteps(rows);
      const known = cash.reduce((sum, c) => sum + c.amount, 0);
      if (Math.abs(known - unallocated) >= 0.01) cash.push({ t, amount: unallocated - known });
    }
    return accountHistory(histories, cash, t);
  }, [sleeves, unallocated, rows, curves, now]);

  const shown = useMemo(() => {
    if (range === 'all' || history.dates.length === 0) return history;
    return windowFrom(history, new Date(now.getTime() - RANGE_DAYS[range] * DAY));
  }, [history, range, now]);

  const deposits = rows.filter((r) => r.kind === 'deposit' || r.kind === 'withdrawal');
  const ordered = [...sleeves].map((s, i) => ({ s, i })).sort((a, b) => b.s.value - a.s.value);
  const folded = ordered.length > MAX_LANES ? ordered.slice(MAX_LANES - 1) : [];
  const lanes: CurveLane[] = (folded.length ? ordered.slice(0, MAX_LANES - 1) : ordered).map(
    ({ s, i }) => sleeveLane(s, i, rows, fills, today, futureEnd)
  );
  if (folded.length) {
    const ids = new Set(folded.map(({ s }) => s.sleeveId));
    lanes.push({
      id: 'more',
      label: `${folded.length} more sleeves`,
      tone: 'muted',
      events: byDay(fills.filter((f) => ids.has(f.sleeveId))).map((d) => ({
        at: d.at,
        shape: 'ring',
        title: `${d.items.length} fills`,
      })),
    });
  }
  if (unallocated !== null) {
    lanes.push({
      id: 'unallocated',
      label: 'Unallocated',
      value: formatMoney(unallocated),
      tone: 'muted',
      events: rows
        .filter((r) => r.signed !== 0)
        .map((r) => ({
          at: r.at,
          shape: r.signed > 0 ? ('diamondFilled' as const) : ('diamond' as const),
          tone: 'muted' as const,
          title: `${r.label} ${formatMoney(r.amount)}`,
        })),
    });
  }

  const upcoming = sleeves
    .filter((s) => sleeveRunState(s) === 'running')
    .map((s) => ({ s, at: nextRebalanceDate(s.rebalance, today) }))
    .filter((x): x is { s: SleeveSummary; at: Date } => x.at !== null && x.at <= futureEnd)
    .sort((a, b) => a.at.getTime() - b.at.getTime());

  if (shown.dates.length < 2) {
    return (
      <p className="m-0 px-1 py-6 text-[12.5px] text-fg-3">
        The curve appears once the ledger has a second day of history.
      </p>
    );
  }

  return (
    <AnnotatedCurve
      label="Total equity and money added"
      dates={shown.dates}
      values={shown.equity}
      benchmark={shown.added}
      end={now}
      now={{ label: `Now ${etClock(now)}` }}
      future={{
        end: futureEnd,
        title: 'Next two weeks',
        content: upcoming.length ? (
          <ul className="m-0 grid list-none gap-0.5 p-0">
            {upcoming.map(({ s, at }) => (
              <li key={s.executionId} className="truncate">
                <span className="num text-fg-3">{dayLabel(at)}</span> {s.name}
              </li>
            ))}
          </ul>
        ) : (
          <span className="text-fg-3">No rebalances scheduled.</span>
        ),
      }}
      pins={deposits.map((r, i) => ({
        at: r.at,
        label: `${r.kind === 'deposit' ? 'Paper funds' : 'Withdrawn'} ${money0(r.amount)}`,
        row: (i % 2) as 0 | 1,
      }))}
      side={
        <div className="grid gap-1.5 text-[12px] text-fg-2">
          <span className="inline-flex items-center gap-2">
            <i aria-hidden="true" className="h-0 w-4 border-t-2 border-accent" />
            Total equity
          </span>
          <span className="inline-flex items-center gap-2">
            <i aria-hidden="true" className="h-0 w-4 border-t-2 border-dashed border-fg-3" />
            Money added
          </span>
          <span className="text-[11.5px] text-fg-3">
            The space between them is what the sleeves earned.
          </span>
        </div>
      }
      lanes={lanes}
      legend={[
        { shape: 'diamondFilled', label: 'In' },
        { shape: 'diamond', label: 'Out' },
        { shape: 'ring', label: 'Rebalance' },
      ]}
      tooltip={(i) => (
        <span className="num">
          {shortDate(shown.dates[i])} · {formatMoney(shown.equity[i])}
          <span className="text-fg-3"> · added {formatMoney(shown.added[i])}</span>
        </span>
      )}
    />
  );
}
