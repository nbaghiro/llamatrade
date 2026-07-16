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
  if (typeof d === 'number') return d;
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
