// Monolith up/down signal colors + dashboard-name aliases over @llamatrade/core/format.
// The formatters are hand-rolled in core (Hermes-parity); this file just maps the
// dashboard's `fmt*` names onto them and keeps the sign colors that are web-only.
import { compact, dateShort, money, pct, qty, signedFraction, signedMoney } from '@llamatrade/core/format';

export { timeAgo } from '@llamatrade/core/format';

// Monolith up/down signal tokens (exact hex — used for sign-driven inline color).
export const UP = '#0f7a34';
export const DOWN = '#c81e1e';

export function colorForSign(n: number): string {
  return n >= 0 ? UP : DOWN;
}

export const fmtCurrency = money;
export const fmtSignedCurrency = signedMoney;
export const fmtSignedPercent = (value: number, decimals = 2): string => pct(value, decimals);
export const fmtSignedFraction = signedFraction;
export const fmtQty = (value: number): string => qty(value);
export const fmtCompact = compact;
export const fmtDateShort = dateShort;
