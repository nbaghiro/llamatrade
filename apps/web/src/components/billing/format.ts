/** Formatting helpers for the plan, payment and invoice surfaces. Reads proto Money and Timestamp. */

import type { Money, Timestamp } from '@llamatrade/core/proto/common_pb';

/** Proto Timestamp -> JS Date (null when unset). */
export function tsToDate(ts: Timestamp | undefined): Date | null {
  if (!ts?.seconds) return null;
  return new Date(Number(ts.seconds) * 1000 + Math.floor(ts.nanos / 1_000_000));
}

/** "Aug 14, 2026", for invoices and the next bill. */
export function formatDate(ts: Timestamp | undefined): string {
  const date = tsToDate(ts);
  if (!date) return '–';
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

/** "Aug 14", for period ranges. */
export function formatDayMonth(ts: Timestamp | undefined): string {
  const date = tsToDate(ts);
  if (!date) return '–';
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/** "Feb 2026". */
export function formatMonthYear(ts: Timestamp | undefined): string {
  const date = tsToDate(ts);
  if (!date) return '–';
  return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
}

/** "Nov 1 to Nov 30". */
export function formatRange(start: Date, end: Date): string {
  const fmt = (d: Date) => d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  return `${fmt(start)} to ${fmt(end)}`;
}

/** "Visa •••• 4242", or "Card •••• 4242" when the brand is unknown. */
export function cardSummary(brand: string | undefined, last4: string | undefined): string {
  const name = brand ? brand.charAt(0).toUpperCase() + brand.slice(1).toLowerCase() : 'Card';
  return last4 ? `${name} •••• ${last4}` : name;
}

/** Parse a proto Money amount (decimal string) into a number. */
export function moneyToNumber(money: Money | undefined): number {
  if (!money?.amount) return 0;
  return parseFloat(money.amount) || 0;
}

/** "$49.00", two decimals with thousands grouping. */
export function formatUsd(value: number): string {
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** "$49", whole dollars for headline prices. */
export function formatUsdWhole(value: number): string {
  return `$${Math.round(value).toLocaleString('en-US')}`;
}

/** Two-digit year for card expiry: 2028 becomes "28". */
export function shortYear(year: number): string {
  return String(year % 100).padStart(2, '0');
}
