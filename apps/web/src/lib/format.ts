/** Display formatting for figures. Negative values use the true minus sign (U+2212). */

const MINUS = '−';
const DASH = '—';

export type Tone = 'gain' | 'loss' | 'flat';

export interface FormatOptions {
  /** Decimal places. */
  dp?: number;
  /** Prefix positive values with "+". */
  signed?: boolean;
}

function digits(abs: number, dp: number): string {
  return abs.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp });
}

function sign(v: number, signed: boolean): string {
  if (v < 0) return MINUS;
  return signed && v > 0 ? '+' : '';
}

/** Rounds first, so a value that displays as zero carries no sign. */
function rounded(v: number, dp: number): number {
  const f = 10 ** dp;
  const r = Math.round(v * f) / f;
  return Object.is(r, -0) ? 0 : r;
}

export function formatNumber(v: number, { dp = 2, signed = false }: FormatOptions = {}): string {
  if (!Number.isFinite(v)) return DASH;
  const r = rounded(v, dp);
  return sign(r, signed) + digits(Math.abs(r), dp);
}

export function formatMoney(v: number, { dp = 2, signed = false }: FormatOptions = {}): string {
  if (!Number.isFinite(v)) return DASH;
  const r = rounded(v, dp);
  return `${sign(r, signed)}$${digits(Math.abs(r), dp)}`;
}

/** Formats a fraction (0.0123) as a percentage (1.23%). */
export function formatPct(
  fraction: number,
  { dp = 2, signed = false }: FormatOptions = {}
): string {
  if (!Number.isFinite(fraction)) return DASH;
  const r = rounded(fraction * 100, dp);
  return `${sign(r, signed)}${digits(Math.abs(r), dp)}%`;
}

/** Profit-and-loss tone of a value, judged at the precision it is shown with. */
export function pnlTone(v: number, dp = 2): Tone {
  if (!Number.isFinite(v)) return 'flat';
  const r = rounded(v, dp);
  if (r > 0) return 'gain';
  if (r < 0) return 'loss';
  return 'flat';
}

/** Day moves smaller than this many percent read as flat. */
export const QUIET_MOVE_PCT = 0.25;

/** Tone of a day move given in percent: under QUIET_MOVE_PCT either way it stays flat. */
export function moveTone(pct: number): Tone {
  if (!Number.isFinite(pct) || Math.abs(pct) < QUIET_MOVE_PCT) return 'flat';
  return pct > 0 ? 'gain' : 'loss';
}

/** Text colour for a tone; flat is ink. */
export const TONE_TEXT: Record<Tone, string> = { gain: 'text-gain', loss: 'text-loss', flat: '' };

/** A service message as a sentence: trimmed, with a closing full stop when it has none. */
export function asSentence(message: string | null | undefined): string {
  const t = message?.trim() ?? '';
  return !t || /[.!?]$/.test(t) ? t : `${t}.`;
}
