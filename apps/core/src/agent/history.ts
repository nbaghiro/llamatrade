/** Groups Copilot conversations by the day of their last activity for the history rail. */

export interface DatedSession {
  id: string;
  title: string;
  lastActivityAt?: { seconds: bigint };
}

export type DayLabel = "Today" | "Yesterday" | "Earlier";

export interface SessionDayGroup<T> {
  label: DayLabel;
  sessions: T[];
}

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/** The local-time day bucket for a timestamp; a missing timestamp counts as earlier. */
export function dayBucket(seconds: bigint | undefined, now: Date): DayLabel {
  if (!seconds) return "Earlier";
  const day = startOfDay(new Date(Number(seconds) * 1000));
  if (day >= startOfDay(now)) return "Today";
  const yesterday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate() - 1,
  ).getTime();
  if (day >= yesterday) return "Yesterday";
  return "Earlier";
}

/**
 * Sorts by last activity, newest first, then splits into Today, Yesterday and Earlier. A query
 * keeps only titles that contain it, ignoring case. Empty groups are left out.
 */
export function groupSessionsByDay<T extends DatedSession>(
  sessions: readonly T[],
  query = "",
  now: Date = new Date(),
): SessionDayGroup<T>[] {
  const q = query.trim().toLowerCase();
  const kept = q
    ? sessions.filter((s) => s.title.toLowerCase().includes(q))
    : [...sessions];
  kept.sort(
    (a, b) =>
      Number(b.lastActivityAt?.seconds ?? 0n) -
      Number(a.lastActivityAt?.seconds ?? 0n),
  );
  const order: DayLabel[] = ["Today", "Yesterday", "Earlier"];
  const groups = order.map((label) => ({ label, sessions: [] as T[] }));
  for (const s of kept) {
    groups[
      order.indexOf(dayBucket(s.lastActivityAt?.seconds, now))
    ].sessions.push(s);
  }
  return groups.filter((g) => g.sessions.length > 0);
}

/** "10:31" for today and yesterday, "Nov 8" for anything older. */
export function sessionWhen(
  seconds: bigint | undefined,
  now: Date = new Date(),
): string {
  if (!seconds) return "";
  const d = new Date(Number(seconds) * 1000);
  if (dayBucket(seconds, now) === "Earlier") {
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }
  return d.toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}
