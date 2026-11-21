/** Whether the app has lost its connection, from failed reads (offline2 B). Pure, for the tests. */

const NETWORK = [
  /network request failed/i,
  /failed to fetch/i,
  /network ?error/i,
  /\[unavailable\]/i,
  /unavailable/i,
  /timed? ?out/i,
  /internet connection appears to be offline/i,
  /could not connect/i,
  /load failed/i,
];

/** A read's error message that means the server couldn't be reached, not that it said no. */
export function isNetworkError(message: string | null | undefined): boolean {
  if (!message) return false;
  return NETWORK.some((re) => re.test(message));
}

/** The time on the strip: "10:38", or "Nov 16, 10:38" when the figures are from another day. */
export function figuresTime(asOf: Date | null, now: Date): string | null {
  if (!asOf || Number.isNaN(asOf.getTime())) return null;
  const hm = `${String(asOf.getHours()).padStart(2, '0')}:${String(asOf.getMinutes()).padStart(2, '0')}`;
  if (asOf.toDateString() === now.toDateString()) return hm;
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${months[asOf.getMonth()]} ${asOf.getDate()}, ${hm}`;
}
