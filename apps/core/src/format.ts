/**
 * Proto value formatting — shared by web and mobile.
 *
 * Backend conventions:
 *  - `Decimal` is a wrapper message `{ value: "102913.23" }` — a STRING, parse it.
 *  - Percent fields arrive ALREADY as percents (3.06 => 3.06%), not fractions.
 *  - `Timestamp` is LlamaTrade's own `{ seconds, nanos }` — int64 as a STRING
 *    over Connect-JSON.
 *
 * Grouping is hand-rolled (not `toLocaleString`) so it renders identically on
 * web, iOS, and Android (Hermes' Intl support varies).
 */

export interface DecimalLike {
  value: string;
}
export interface TimestampLike {
  seconds?: bigint | string | number;
  nanos?: number;
}

/** proto Decimal -> number. */
export function num(d?: DecimalLike | number | null): number {
  if (typeof d === 'number') return Number.isFinite(d) ? d : 0;
  const v = d?.value;
  if (!v) return 0;
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : 0;
}

function group(n: number, digits: number): string {
  const [int, frac] = Math.abs(n).toFixed(digits).split('.');
  const sep = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return frac ? `${sep}.${frac}` : sep;
}

/** $102,913 */
export function money(d?: DecimalLike | number | null, digits = 0): string {
  const n = num(d);
  return `${n < 0 ? '−' : ''}$${group(n, digits)}`;
}

/** +$2,603 / −$207 */
export function signedMoney(d?: DecimalLike | number | null, digits = 0): string {
  const n = num(d);
  return `${n < 0 ? '−' : '+'}$${group(n, digits)}`;
}

/** Compact dollars: $50k, $1.2k, $0. */
export function moneyShort(d?: DecimalLike | number | null): string {
  const n = num(d);
  if (n === 0) return '$0';
  if (Math.abs(n) >= 1000) {
    const k = n / 1000;
    return `${n < 0 ? '−' : ''}$${Math.abs(k) >= 10 ? Math.round(Math.abs(k)) : Math.abs(k).toFixed(1)}k`;
  }
  return `${n < 0 ? '−' : ''}$${Math.round(Math.abs(n))}`;
}

/** +3.06% / −0.24% — input already a percent. */
export function pct(d?: DecimalLike | number | null, digits = 2): string {
  const n = num(d);
  return `${n < 0 ? '−' : '+'}${group(n, digits)}%`;
}

/** Sign helper for tone/coloring. */
export function isUp(d?: DecimalLike | number | null): boolean {
  return num(d) >= 0;
}

/** LlamaTrade Timestamp {seconds,nanos} -> Date (seconds is a STRING over JSON). */
export function toDate(ts?: TimestampLike | null): Date | null {
  if (!ts?.seconds) return null;
  const secs = Number(ts.seconds);
  if (!Number.isFinite(secs)) return null;
  return new Date(secs * 1000 + (ts.nanos ?? 0) / 1e6);
}

/** ms since epoch, or Date.now() when absent. */
export function toMs(ts?: TimestampLike | null): number {
  return toDate(ts)?.getTime() ?? Date.now();
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** 1,234.5 — grouped, up to `maxDigits` decimals with trailing zeros trimmed. */
export function qty(value: number, maxDigits = 2): string {
  const neg = value < 0;
  const [int, frac] = Math.abs(value).toFixed(maxDigits).split('.');
  const sep = int.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const trimmed = frac ? frac.replace(/0+$/, '') : '';
  return `${neg ? '−' : ''}${sep}${trimmed ? `.${trimmed}` : ''}`;
}

/** +12.4% from a fraction (0.124 => "+12.4%"). */
export function signedFraction(fraction: number, digits = 1): string {
  return pct(fraction * 100, digits);
}

/** 77.62M / 1.2K — compact magnitude, hand-rolled (no Intl). */
export function compact(value: number): string {
  const sign = value < 0 ? '−' : '';
  const abs = Math.abs(value);
  const suffixed = (n: number, suffix: string): string =>
    `${sign}${n.toFixed(2).replace(/\.?0+$/, '')}${suffix}`;
  if (abs >= 1e12) return suffixed(abs / 1e12, 'T');
  if (abs >= 1e9) return suffixed(abs / 1e9, 'B');
  if (abs >= 1e6) return suffixed(abs / 1e6, 'M');
  if (abs >= 1e3) return suffixed(abs / 1e3, 'K');
  return `${sign}${abs.toFixed(2).replace(/\.?0+$/, '')}`;
}

/** "Jul 16" — hand-rolled month/day. */
export function dateShort(date: Date | null): string {
  if (!date) return '';
  return `${MONTHS[date.getMonth()]} ${date.getDate()}`;
}

/** "now" / "5m" / "2h" / "3d" / "Jul 16" past a week. */
export function timeAgo(date: Date | null): string {
  if (!date) return '';
  const mins = Math.floor((Date.now() - date.getTime()) / 60_000);
  if (mins < 1) return 'now';
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  return dateShort(date);
}
