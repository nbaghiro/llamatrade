// Pure formatting helpers + Monolith signal colors for the dashboard.
// No React here so the store can share these too.

// Monolith up/down signal tokens (exact hex — used for sign-driven inline color).
export const UP = '#0f7a34';
export const DOWN = '#c81e1e';

const MINUS = '−'; // typographic minus, matches the mockup

export function colorForSign(n: number): string {
  return n >= 0 ? UP : DOWN;
}

export function fmtCurrency(value: number, decimals = 0): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/** Signed currency with a leading +/− and no sign duplication ("+$412", "−$50"). */
export function fmtSignedCurrency(value: number, decimals = 0): string {
  const sign = value < 0 ? MINUS : '+';
  return `${sign}${fmtCurrency(Math.abs(value), decimals)}`;
}

/** `value` is already a percentage (e.g. 3.13 → "+3.13%"). */
export function fmtSignedPercent(value: number, decimals = 2): string {
  const sign = value < 0 ? MINUS : '+';
  return `${sign}${Math.abs(value).toFixed(decimals)}%`;
}

/** `fraction` is a decimal return (e.g. 0.124 → "+12.4%"). */
export function fmtSignedFraction(fraction: number, decimals = 1): string {
  return fmtSignedPercent(fraction * 100, decimals);
}

export function fmtQty(value: number): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value);
}

/** Compact relative age: "now", "5m", "2h", "3d", or an absolute date past a week. */
export function timeAgo(date: Date | null): string {
  if (!date) return '';
  const diffMs = Date.now() - date.getTime();
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return 'now';
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

export function fmtDateShort(date: Date | null): string {
  if (!date) return '';
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}
