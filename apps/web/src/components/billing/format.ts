/**
 * Formatting helpers shared across the billing + settings billing surfaces.
 * Everything here reads proto types (Money, Timestamp) and renders the
 * Monolith-styled figures (short dates, USD, tabular numbers).
 */

import type { Money, Timestamp } from '../../generated/proto/common_pb';

const MS_PER_DAY = 1000 * 60 * 60 * 24;

/** Proto Timestamp -> JS Date (null when unset). */
export function tsToDate(ts: Timestamp | undefined): Date | null {
  if (!ts?.seconds) return null;
  return new Date(Number(ts.seconds) * 1000 + Math.floor(ts.nanos / 1_000_000));
}

/** "Aug 14, 2026" — the invoice/next-bill format used throughout the design. */
export function formatDate(ts: Timestamp | undefined): string {
  const date = tsToDate(ts);
  if (!date) return '—';
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

/** "Aug 14" — compact form for billing-cycle range labels. */
export function formatDayMonth(ts: Timestamp | undefined): string {
  const date = tsToDate(ts);
  if (!date) return '—';
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/** "Feb 2026" — the "member since" format. */
export function formatMonthYear(ts: Timestamp | undefined): string {
  const date = tsToDate(ts);
  if (!date) return '—';
  return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' }).toUpperCase();
}

/** Parse a proto Money amount (decimal string) into a number. */
export function moneyToNumber(money: Money | undefined): number {
  if (!money?.amount) return 0;
  return parseFloat(money.amount) || 0;
}

/** "$49.00" — fixed 2-decimal USD, no thousands beyond the default locale grouping. */
export function formatUsd(value: number): string {
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** "$49" — whole-dollar USD for headline prices. */
export function formatUsdWhole(value: number): string {
  return `$${Math.round(value).toLocaleString('en-US')}`;
}

/** Two-digit year for card expiry ("2028" -> "28"). */
export function shortYear(year: number): string {
  return String(year % 100).padStart(2, '0');
}

export interface BillingCycleProgress {
  totalDays: number;
  elapsedDays: number;
  fraction: number; // 0..1
}

/** Elapsed / total days for the billing-cycle progress bar. */
export function billingCycleProgress(
  start: Timestamp | undefined,
  end: Timestamp | undefined,
): BillingCycleProgress | null {
  const startDate = tsToDate(start);
  const endDate = tsToDate(end);
  if (!startDate || !endDate || endDate <= startDate) return null;

  const totalDays = Math.max(1, Math.round((endDate.getTime() - startDate.getTime()) / MS_PER_DAY));
  const rawElapsed = Math.floor((Date.now() - startDate.getTime()) / MS_PER_DAY);
  const elapsedDays = Math.min(totalDays, Math.max(0, rawElapsed));
  return { totalDays, elapsedDays, fraction: elapsedDays / totalDays };
}
