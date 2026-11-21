import { OrderStatus } from '@llamatrade/core/proto/trading_pb';

import { etParts } from '../../lib/marketClock';

/** The regular session in New York minutes; the bell's lanes run from the open to the close. */
export const OPEN_MIN = 9 * 60 + 30;
export const CLOSE_MIN = 16 * 60;
/** Fills closer together than this share one dot with a count. */
export const MERGE_MIN = 10;

export interface LaneSessionInput {
  id: string;
  name: string;
  isActive: boolean;
  sleeveId: string;
  /** The session's schedule rebalances today. */
  rebalancesToday?: boolean;
  /** When the sleeve froze, where known. */
  frozenAt?: Date | null;
}

export interface LaneOrderInput {
  sessionId: string;
  status: OrderStatus;
  filledAt: Date | null;
}

export interface LaneFill {
  /** Minutes after midnight in New York, of the first fill in the group. */
  minute: number;
  count: number;
}

export interface TodayLane {
  id: string;
  name: string;
  frozen: boolean;
  fills: LaneFill[];
  /** A rebalance is still to come before the close. */
  planned: boolean;
  /** The New York minute the sleeve froze, when that was today. */
  frozenMinute: number | null;
}

const sameEtDay = (a: Date, b: Date) => {
  const x = etParts(a);
  const y = etParts(b);
  return x.year === y.year && x.month === y.month && x.day === y.day;
};

/** "9:05" from minutes after midnight. */
export function minuteLabel(minute: number): string {
  return `${Math.floor(minute / 60)}:${String(minute % 60).padStart(2, '0')}`;
}

/** Where a New York minute sits between the open and the close, from 0 to 1. */
export function dayFraction(minute: number): number {
  return Math.min(1, Math.max(0, (minute - OPEN_MIN) / (CLOSE_MIN - OPEN_MIN)));
}

/**
 * One lane per running session, plus any stopped session that filled today, with today's
 * fills grouped into dots (notifications2 A). Frozen sessions sort first.
 */
export function todayLanes(
  sessions: readonly LaneSessionInput[],
  orders: readonly LaneOrderInput[],
  frozenSleeveIds: ReadonlySet<string>,
  now: Date
): TodayLane[] {
  const fillsBySession = new Map<string, number[]>();
  for (const o of orders) {
    if (o.status !== OrderStatus.FILLED || !o.filledAt || !sameEtDay(o.filledAt, now)) continue;
    const list = fillsBySession.get(o.sessionId) ?? [];
    list.push(etParts(o.filledAt).minutes);
    fillsBySession.set(o.sessionId, list);
  }

  const lanes: TodayLane[] = [];
  for (const s of sessions) {
    const minutes = (fillsBySession.get(s.id) ?? []).sort((a, b) => a - b);
    if (!s.isActive && minutes.length === 0) continue;
    const fills: LaneFill[] = [];
    for (const m of minutes) {
      const last = fills[fills.length - 1];
      if (last && m - last.minute < MERGE_MIN) last.count += 1;
      else fills.push({ minute: m, count: 1 });
    }
    const frozen = s.sleeveId !== '' && frozenSleeveIds.has(s.sleeveId);
    const frozenToday = frozen && s.frozenAt && sameEtDay(s.frozenAt, now) ? s.frozenAt : null;
    lanes.push({
      id: s.id,
      name: s.name,
      frozen,
      fills,
      planned: Boolean(s.rebalancesToday) && s.isActive && etParts(now).minutes < CLOSE_MIN,
      frozenMinute: frozenToday ? etParts(frozenToday).minutes : null,
    });
  }
  return lanes.sort((a, b) => Number(b.frozen) - Number(a.frozen));
}
