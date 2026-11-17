import type { CurvePin, LaneEvent, LaneFuture, LaneSpan } from '../charts';

import {
  dayLabel,
  etDay,
  fillDays,
  rebalancesOn,
  schedules,
  type Fill,
  type HomeSession,
} from './homeModel';

const DAY = 86_400_000;

/** The date of a New York calendar day's close, for placing a day's mark on the time axis. */
const closeOf = (day: Date) => new Date(day.getTime() + 20 * 3_600_000);

export interface LaneWindow {
  start: Date;
  /** The end of the past: now while open, the last close otherwise. */
  end: Date;
  /** The New York date of `end`. */
  today: Date;
  /** The last day of the future column. */
  futureEnd: Date;
}

const within = (at: Date, w: LaneWindow) =>
  at.getTime() >= w.start.getTime() && at.getTime() <= w.end.getTime();

/** Rings on past days with fills, a numbered dot for today's, and the start and stop ticks. */
export function laneEvents(
  session: Pick<HomeSession, 'startedAt' | 'stoppedAt' | 'state'>,
  fills: readonly Fill[],
  w: LaneWindow
): LaneEvent[] {
  const risk = session.state === 'frozen';
  const events: LaneEvent[] = [];
  if (session.startedAt && within(session.startedAt, w)) {
    events.push({
      at: session.startedAt,
      shape: 'start',
      title: `Started ${dayLabel(etDay(session.startedAt))}`,
    });
  }
  for (const { day, count } of fillDays(fills)) {
    const isToday = day.getTime() === w.today.getTime();
    const at = isToday ? w.end : closeOf(day);
    if (!within(at, w)) continue;
    const words = `${count} ${count === 1 ? 'fill' : 'fills'}`;
    events.push(
      isToday
        ? { at, shape: 'dot', count, tone: risk ? 'risk' : 'accent', title: `${words} today` }
        : {
            at,
            shape: 'ring',
            tone: risk ? 'risk' : 'accent',
            title: `Rebalance on ${dayLabel(day)} · ${words}`,
          }
    );
  }
  if (session.stoppedAt && within(session.stoppedAt, w)) {
    events.push({
      at: session.stoppedAt,
      shape: 'stop',
      tone: 'muted',
      title: `Stopped ${dayLabel(etDay(session.stoppedAt))}`,
    });
  }
  return events;
}

/** The running line, cut at the stop, and amber from the moment a sleeve froze. */
export function laneSpans(
  session: Pick<HomeSession, 'startedAt' | 'stoppedAt' | 'frozenAt' | 'state'>,
  w: LaneWindow
): LaneSpan[] {
  const from =
    session.startedAt && session.startedAt.getTime() > w.start.getTime()
      ? session.startedAt
      : w.start;
  if (session.stoppedAt) {
    if (session.stoppedAt.getTime() < w.start.getTime()) return [];
    return [{ from, to: session.stoppedAt, style: 'off' }];
  }
  if (session.state === 'paused') return [{ from, style: 'off' }];
  if (session.state === 'frozen') {
    const frozen =
      session.frozenAt && session.frozenAt.getTime() > from.getTime() ? session.frozenAt : from;
    return [
      ...(frozen.getTime() > from.getTime() ? [{ from, to: frozen, style: 'on' as const }] : []),
      { from: frozen, style: 'on', tone: 'risk' },
    ];
  }
  return [{ from, style: 'on' }];
}

/** The first scheduled rebalance after `today`, looking up to a year ahead. */
export function nextRebalance(rebalance: string, today: Date): Date | null {
  if (!rebalance) return null;
  for (let i = 1; i <= 370; i++) {
    const d = new Date(today.getTime() + i * DAY);
    if (rebalancesOn(rebalance, d)) return d;
  }
  return null;
}

/** Planned marks for the next two weeks, or a short note when there is nothing to mark. */
export function laneFuture(session: HomeSession, w: LaneWindow): LaneFuture {
  if (session.state === 'stopped' || session.state === 'error') return { note: 'Stopped' };
  if (session.state === 'paused') return { note: 'Paused' };
  if (session.state === 'frozen') return { note: 'Waits for review' };
  if (!schedules(session)) return {};
  if (session.rebalance.toLowerCase() === 'daily') return { note: 'Each trading day' };
  const events: LaneEvent[] = [];
  for (
    let d = new Date(w.today.getTime() + DAY);
    d.getTime() <= w.futureEnd.getTime();
    d = new Date(d.getTime() + DAY)
  ) {
    if (rebalancesOn(session.rebalance, d)) {
      events.push({ at: d, shape: 'planned', title: `Rebalances ${dayLabel(d)}` });
    }
  }
  if (events.length) return { events };
  const next = nextRebalance(session.rebalance, w.today);
  return next ? { note: `Next ${dayLabel(next)}` } : {};
}

/** Several lanes' marks as one row: day counts added together, planned days merged. */
export function mergedEvents(lists: readonly (readonly LaneEvent[])[]): LaneEvent[] {
  const byKey = new Map<string, LaneEvent>();
  for (const list of lists) {
    for (const e of list) {
      if (e.shape === 'start' || e.shape === 'stop') continue;
      const k = `${e.shape}:${etDay(e.at).getTime()}`;
      const prev = byKey.get(k);
      if (prev && e.shape === 'dot') {
        byKey.set(k, { ...prev, count: (prev.count ?? 0) + (e.count ?? 0) });
      } else if (!prev) {
        byKey.set(k, { at: e.at, shape: e.shape, count: e.count });
      }
    }
  }
  return [...byKey.values()].sort((a, b) => a.at.getTime() - b.at.getTime());
}

/**
 * Pins for starts, stops and today's fills inside the window, at most `max`. A pin that would
 * crowd the one before it on the same line drops to the second line.
 */
export function curvePins(
  sessions: readonly HomeSession[],
  fillsToday: number,
  w: LaneWindow,
  max = 6
): CurvePin[] {
  const raw: CurvePin[] = [];
  for (const s of sessions) {
    if (s.startedAt && within(s.startedAt, w) && s.startedAt.getTime() > w.start.getTime() + DAY) {
      raw.push({ at: s.startedAt, label: `${s.name} started` });
    }
    if (s.stoppedAt && within(s.stoppedAt, w)) {
      raw.push({ at: s.stoppedAt, label: `${s.name} stopped ${dayLabel(etDay(s.stoppedAt))}` });
    }
  }
  const span = Math.max(1, w.end.getTime() - w.start.getTime());
  const picked = raw
    .sort((a, b) => b.at.getTime() - a.at.getTime())
    .slice(0, max - (fillsToday ? 1 : 0));
  const all = [
    ...picked.sort((a, b) => a.at.getTime() - b.at.getTime()),
    ...(fillsToday
      ? [
          {
            at: w.end,
            label: 'Fills today',
            tone: 'accent' as const,
            count: fillsToday,
            guide: false,
          },
        ]
      : []),
  ];
  const lastOnRow: [number, number] = [-Infinity, -Infinity];
  return all.map((p) => {
    const f = (p.at.getTime() - w.start.getTime()) / span;
    const row: 0 | 1 = f - lastOnRow[0] >= 0.2 ? 0 : 1;
    lastOnRow[row] = f;
    return { ...p, row };
  });
}
