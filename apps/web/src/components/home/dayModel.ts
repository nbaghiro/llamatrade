/** Words for Home's day panels: the summary under what moved, and the steps that come next. */

import { formatMoney } from '../../lib/format';

import {
  etDay,
  signedPct,
  weekdayLabel,
  type HomeSession,
  type MarketPhase,
  type ScheduleRow,
} from './homeModel';

const COUNT = ['No', 'One', 'Both', 'All three', 'All four', 'All five'];

/** The sentence under the chart, from the figures it draws. */
export function movedSummary(
  rows: readonly { usd: number }[],
  spy: number | null,
  closed: boolean
): string {
  if (rows.length === 0) return 'No running session has a figure for the day yet.';
  const word = COUNT[rows.length] ?? `All ${rows.length}`;
  const usd = rows.map((r) => r.usd);
  const lo = Math.min(...usd);
  const hi = Math.max(...usd);
  const verb = closed ? 'moved' : 'have moved';
  const spyPart =
    spy === null ? '' : `, while SPY ${closed ? 'moved' : 'is'} ${signedPct(spy * 100)}`;
  if (rows.length === 1)
    return `One running session ${closed ? 'moved' : 'has moved'} ${formatMoney(lo, { signed: true })}${spyPart}.`;
  return `${word} running sessions ${verb} between ${formatMoney(lo, { signed: true })} and ${formatMoney(hi, { signed: true })}${spyPart}.`;
}

export interface NextEntry {
  key: string;
  day: Date;
  when: string;
  at: string;
  title: string;
  detail: string;
  risk: boolean;
  sessions: readonly HomeSession[];
}

const names = (list: readonly string[]) =>
  list.length <= 2
    ? list.join(' and ')
    : `${list.slice(0, -1).join(', ')} and ${list[list.length - 1]}`;

/** What comes next, in order: the open when closed, today's rebalances, then the schedule. */
export function nextEntries(
  schedule: readonly ScheduleRow[],
  due: readonly HomeSession[],
  phase: MarketPhase,
  today: Date
): NextEntry[] {
  const out: NextEntry[] = [];
  if (!phase.open && phase.nextOpen) {
    const day = etDay(phase.nextOpen);
    out.push({
      key: 'open',
      day,
      when: day.getTime() === today.getTime() ? 'Today' : weekdayLabel(day),
      at: '09:30',
      title: 'The market opens',
      detail: 'Running sessions trade again from the open.',
      risk: false,
      sessions: [],
    });
  }
  if (due.length) {
    out.push({
      key: 'today',
      day: today,
      when: 'Today',
      at: '',
      title: `${names(due.map((s) => s.name))} ${due.length === 1 ? 'rebalances' : 'rebalance'}`,
      detail: `Before the close at ${phase.closeClock} ET.`,
      risk: false,
      sessions: due,
    });
  }
  for (const r of schedule) {
    const frozen = r.sessions.filter((s) => s.state === 'frozen');
    const title =
      r.kind === 'closed'
        ? 'The market is closed'
        : r.kind === 'early'
          ? 'The market closes early'
          : `${names(r.sessions.map((s) => s.name))} ${r.sessions.length === 1 ? 'rebalances' : 'rebalance'}`;
    const detail =
      r.kind === 'closed'
        ? `Closed for ${r.name ?? 'a market holiday'}.`
        : r.kind === 'early'
          ? `Closes at 13:00 for ${r.name ?? 'an early close'}.`
          : frozen.length
            ? `${frozen.length === 1 ? `${frozen[0].name} waits` : 'Frozen sessions wait'} until the difference with Alpaca is reviewed.`
            : r.sessions.length === 1
              ? `${r.sessions[0].rebalance || 'Scheduled'} rebalance.`
              : `${r.sessions.length} sessions rebalance on the same day.`;
    out.push({
      key: `${r.kind}-${r.day.getTime()}`,
      day: r.day,
      when: weekdayLabel(r.day),
      at: '',
      title,
      detail,
      risk: frozen.length > 0,
      sessions: r.sessions,
    });
  }
  return out;
}
