import { toDate } from '@llamatrade/core/format';
import type { Notification } from '@llamatrade/core/proto/notification_pb';

import { etParts } from '../../lib/marketClock';

export type EarlierNotice = Pick<Notification, 'id' | 'title' | 'message' | 'isRead' | 'createdAt'>;

export interface EarlierRow<T extends EarlierNotice> {
  /** The newest of the group, which the row shows. */
  notice: T;
  /** How many notices with this title arrived that day. */
  count: number;
  /** Every id in the group, so reading the row reads them all. */
  ids: string[];
  unread: boolean;
}

const dayKey = (d: Date | null) => {
  if (!d) return 'unknown';
  const p = etParts(d);
  return `${p.year}-${p.month}-${p.day}`;
};

/**
 * Repeats of one notice on one New York day fold into a single row with a count, so a
 * connection that drops fifty times reads as one line. Order follows the newest of each group.
 */
export function collapseRepeats<T extends EarlierNotice>(notices: readonly T[]): EarlierRow<T>[] {
  const rows = new Map<string, EarlierRow<T>>();
  for (const n of notices) {
    const key = `${dayKey(toDate(n.createdAt))}|${n.title.trim().toLowerCase()}`;
    const row = rows.get(key);
    if (!row) {
      rows.set(key, { notice: n, count: 1, ids: [n.id], unread: !n.isRead });
      continue;
    }
    row.count += 1;
    row.ids.push(n.id);
    row.unread ||= !n.isRead;
    const at = toDate(n.createdAt)?.getTime() ?? 0;
    if (at > (toDate(row.notice.createdAt)?.getTime() ?? 0)) row.notice = n;
  }
  return [...rows.values()];
}

/** Drops an internal identifier such as ": bar_stream" from the end of a message. */
export function plainMessage(message: string): string {
  return message.replace(/:\s*[a-z0-9]+(?:_[a-z0-9]+)+\.?\s*$/, '.').replace(/\.\.$/, '.');
}
