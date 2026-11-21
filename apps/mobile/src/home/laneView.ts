import type { Lane, LaneMarker } from '../charts/Lanes';
import { laneCode } from '../charts/scale';
import type { LaneIn } from './model';

const DAY = 86_400_000;

/**
 * Session lanes as chart lanes: live in ink, paper dashed in the accent, frozen amber, stopped
 * grey with a square on its last day. `moneyIn` adds a diamond where the session was funded.
 */
export function toChartLanes(lanes: readonly LaneIn[], opts: { moneyIn?: boolean } = {}): Lane[] {
  return lanes.map((l) => ({
    key: l.key,
    label: laneCode(l.name),
    start: l.start,
    end: l.end,
    tone: l.state === 'frozen' || l.state === 'error' ? 'risk' : l.state === 'stopped' ? 'muted' : l.mode === 'live' ? 'ink' : 'accent',
    dashed: l.mode === 'paper',
    markers: [
      ...(opts.moneyIn && l.start ? [{ t: l.start, kind: 'start' as const, id: 'start' }] : []),
      ...l.fillDays.map<LaneMarker>((f) => ({ t: f.day + DAY / 2, kind: 'fill', count: f.count, id: `f${f.day}` })),
      ...l.planned.map<LaneMarker>((p) => ({ t: p + DAY / 2, kind: 'planned', id: `p${p}` })),
      ...(l.state === 'stopped' && l.end ? [{ t: l.end, kind: 'stop' as const, id: 'stop' }] : []),
    ],
  }));
}
