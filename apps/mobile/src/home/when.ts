/** Short time and day labels for timelines. Pure, local time. */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const DAYS_LONG = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const MONTHS_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

/** "09:45" */
export function hm(t: number): string {
  const d = new Date(t);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/** "Today", "Tomorrow", "Wed" within a week, else "Nov 23". */
export function dayLabel(t: number, now: number): string {
  const a = new Date(t);
  a.setHours(0, 0, 0, 0);
  const b = new Date(now);
  b.setHours(0, 0, 0, 0);
  const diff = Math.round((a.getTime() - b.getTime()) / 86_400_000);
  if (diff === 0) return 'Today';
  if (diff === 1) return 'Tomorrow';
  if (diff === -1) return 'Yesterday';
  if (diff > 1 && diff < 7) return DAYS[a.getDay()];
  return `${MONTHS[a.getMonth()]} ${a.getDate()}`;
}

/** "Nov 23" */
export function shortDate(t: number): string {
  const d = new Date(t);
  return `${MONTHS[d.getMonth()]} ${d.getDate()}`;
}

/** "Tuesday, November 17" */
export function longDate(t: number): string {
  const d = new Date(t);
  return `${DAYS_LONG[d.getDay()]}, ${MONTHS_LONG[d.getMonth()]} ${d.getDate()}`;
}

/** "Wed 09:30" for a next open within a week, "Nov 30, 09:30" beyond. */
export function openLabel(t: number, now: number): string {
  const day = dayLabel(t, now);
  return `${day === 'Today' ? 'Today' : day} ${hm(t)}`;
}
