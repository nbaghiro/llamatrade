import type { MonthReturn } from '../illustrative/series';

export interface MonthCell {
  m: number;
  r: number | null;
}

export interface YearRow {
  year: number;
  cells: MonthCell[];
  /** Compounded return of the months present. */
  total: number;
}

/** Rows by year, January to December; months with no data are null. */
export function monthlyRows(months: readonly MonthReturn[]): YearRow[] {
  const years = [...new Set(months.map((m) => m.y))].sort((a, b) => a - b);
  return years.map((year) => {
    let comp = 1;
    const cells = Array.from({ length: 12 }, (_, m) => {
      const f = months.find((x) => x.y === year && x.m === m);
      if (f) comp *= 1 + f.r;
      return { m, r: f ? f.r : null };
    });
    return { year, cells, total: comp - 1 };
  });
}

/** Cells whose return rounds to 0.0% are shown flat. */
export const FLAT_RETURN = 0.0005;

/** Background alpha for a cell: 0.1 for small moves up to 0.48 at `full` (8%) or more. */
export function cellAlpha(r: number, full = 0.08): number {
  const q = Math.min(1, Math.abs(r) / full);
  return 0.1 + q * 0.38;
}

/** The text shown in a cell: one decimal, no sign for gains, true minus for losses. */
export function cellText(r: number): string {
  if (Math.abs(r) < FLAT_RETURN) return '0.0';
  return (r < 0 ? '−' : '') + Math.abs(r * 100).toFixed(1);
}

/** The phone cell text: whole percent, so twelve months fit at 390px. */
export function cellTextShort(r: number): string {
  const whole = Math.round(Math.abs(r * 100));
  return whole === 0 ? '0' : (r < 0 ? '−' : '') + whole;
}
