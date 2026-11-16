import { toDate } from '@llamatrade/core/format';
import type { Notification } from '@llamatrade/core/proto/notification_pb';

export interface DayGroup {
  label: string;
  items: Notification[];
}

function dayKey(d: Date): string {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

/** Splits a newest-first list into Today, Yesterday and dated groups, in the viewer's time zone. */
export function groupByDay(items: readonly Notification[], now: Date): DayGroup[] {
  const today = dayKey(now);
  const yesterday = dayKey(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1));
  const groups: DayGroup[] = [];
  for (const n of items) {
    const created = toDate(n.createdAt);
    const key = created ? dayKey(created) : 'unknown';
    const label = !created
      ? 'Earlier'
      : key === today
        ? 'Today'
        : key === yesterday
          ? 'Yesterday'
          : created.toLocaleDateString('en-US', {
              weekday: 'short',
              month: 'short',
              day: 'numeric',
              ...(created.getFullYear() === now.getFullYear() ? {} : { year: 'numeric' }),
            });
    const last = groups[groups.length - 1];
    if (last?.label === label) last.items.push(n);
    else groups.push({ label, items: [n] });
  }
  return groups;
}
