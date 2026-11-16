/** Series maths shared by the illustrative data and the chart components. */

export interface MonthReturn {
  /** Calendar year. */
  y: number;
  /** Month, 0 = January. */
  m: number;
  /** Return for the month as a fraction. */
  r: number;
}

export interface SeriesStats {
  start: number;
  end: number;
  total: number;
  cagr: number;
  vol: number;
  sharpe: number;
  sortino: number;
  mdd: number;
  mddAt: number;
  ddPeakAt: number;
  recoveredAt: number;
  recoveryDays: number | null;
}

/** Weekdays from `start` to `end` inclusive (YYYY-MM-DD, UTC noon). Holidays are not removed. */
export function tradingDays(start: string, end: string): Date[] {
  const out: Date[] = [];
  const d = new Date(`${start}T12:00:00Z`);
  const e = new Date(`${end}T12:00:00Z`);
  while (d <= e) {
    const w = d.getUTCDay();
    if (w !== 0 && w !== 6) out.push(new Date(d));
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return out;
}

/** Compounds log returns `z` from `start`, drifted so the series ends exactly at `end`. */
export function compound(z: readonly number[], start: number, end: number): number[] {
  const n = z.length;
  if (n === 0) return [];
  if (n === 1) return [start];
  let s = 0;
  for (let i = 1; i < n; i++) s += z[i];
  const adj = (Math.log(end / start) - s) / (n - 1);
  const out = [start];
  let lv = Math.log(start);
  for (let i = 1; i < n; i++) {
    lv += z[i] + adj;
    out.push(Math.exp(lv));
  }
  return out;
}

/** Spreads `amount` of log return evenly over `len` steps from `at`, in place. */
export function shock(z: number[], at: number, len: number, amount: number): void {
  for (let i = Math.max(0, at); i < at + len && i < z.length; i++) z[i] += amount / len;
}

/** Fractional distance below the running peak at each point (0 at a new high). */
export function drawdown(s: readonly number[]): number[] {
  let peak = s.length ? s[0] : 0;
  return s.map((v) => {
    peak = Math.max(peak, v);
    return peak === 0 ? 0 : v / peak - 1;
  });
}

/** One return per calendar month, measured from the previous month's last value. */
export function monthly(s: readonly number[], days: readonly Date[]): MonthReturn[] {
  const out: MonthReturn[] = [];
  let prev = s[0];
  for (let i = 0; i < s.length; i++) {
    const last = i === s.length - 1 || days[i + 1].getUTCMonth() !== days[i].getUTCMonth();
    if (last) {
      out.push({ y: days[i].getUTCFullYear(), m: days[i].getUTCMonth(), r: s[i] / prev - 1 });
      prev = s[i];
    }
  }
  return out;
}

export function stats(s: readonly number[], days: readonly Date[]): SeriesStats {
  const r: number[] = [];
  for (let i = 1; i < s.length; i++) r.push(s[i] / s[i - 1] - 1);
  const mean = r.length ? r.reduce((a, b) => a + b, 0) / r.length : 0;
  const sd =
    r.length > 1 ? Math.sqrt(r.reduce((a, b) => a + (b - mean) ** 2, 0) / (r.length - 1)) : 0;
  const down = r.length ? Math.sqrt(r.reduce((a, b) => a + Math.min(b, 0) ** 2, 0) / r.length) : 0;
  let peak = s[0];
  let mdd = 0;
  let mddAt = 0;
  let peakAt = 0;
  let ddPeakAt = 0;
  for (let i = 0; i < s.length; i++) {
    if (s[i] > peak) {
      peak = s[i];
      peakAt = i;
    }
    const dd = s[i] / peak - 1;
    if (dd < mdd) {
      mdd = dd;
      mddAt = i;
      ddPeakAt = peakAt;
    }
  }
  let recoveredAt = -1;
  for (let i = mddAt; i < s.length && mdd < 0; i++) {
    if (s[i] >= s[ddPeakAt]) {
      recoveredAt = i;
      break;
    }
  }
  const years = (days[days.length - 1].getTime() - days[0].getTime()) / (365.25 * 864e5);
  const end = s[s.length - 1];
  const ratio = (num: number, den: number) => (den === 0 ? 0 : (num / den) * Math.sqrt(252));
  return {
    start: s[0],
    end,
    total: end / s[0] - 1,
    cagr: years > 0 ? Math.pow(end / s[0], 1 / years) - 1 : 0,
    vol: sd * Math.sqrt(252),
    sharpe: ratio(mean, sd),
    sortino: ratio(mean, down),
    mdd,
    mddAt,
    ddPeakAt,
    recoveredAt,
    recoveryDays: recoveredAt > 0 ? recoveredAt - mddAt : null,
  };
}
