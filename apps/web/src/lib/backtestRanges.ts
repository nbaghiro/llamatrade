/**
 * Curated backtest ranges and hard market stretches, shared by the setup cards, the long-range
 * shading and the "Next" suggestion on a result. Dates are UTC days.
 */

/** The first daily bar the data provider has for the symbols the app trades. */
export const DATA_FLOOR = '2016-01-04';

export interface HardStretch {
  id: string;
  label: string;
  /** Peak to trough of SPY, as YYYY-MM-DD. */
  start: string;
  end: string;
}

export const HARD_STRETCHES: readonly HardStretch[] = [
  { id: 'q4-2018', label: 'Q4 2018', start: '2018-10-01', end: '2018-12-24' },
  { id: 'mar-2020', label: 'Mar 2020', start: '2020-02-19', end: '2020-03-23' },
  { id: '2022', label: '2022', start: '2022-01-03', end: '2022-10-12' },
];

export interface CuratedRange {
  id: string;
  label: string;
  start: string;
  end: string;
  /** One line on why this range is worth a run. */
  reason: string;
}

const day = (d: Date) => d.toISOString().slice(0, 10);

const yearsBefore = (d: Date, years: number) => {
  const out = new Date(d);
  out.setUTCFullYear(out.getUTCFullYear() - years);
  return out;
};

/** The four ranges the setup offers, ending at `today` where they run to the present. */
export function curatedRanges(today: Date): CuratedRange[] {
  const end = day(today);
  const fiveBack = day(yearsBefore(today, 5));
  return [
    {
      id: 'five-years',
      label: 'The last five years',
      start: fiveBack < DATA_FLOOR ? DATA_FLOOR : fiveBack,
      end,
      reason: 'Recent markets, long enough to include a full cycle.',
    },
    {
      id: 'fall-2022',
      label: 'Through the 2022 fall',
      start: '2021-11-01',
      end: '2023-06-30',
      reason: "SPY's longest fall in the data, from January to October 2022.",
    },
    {
      id: 'mar-2020',
      label: 'March 2020 and the recovery',
      start: '2020-01-02',
      end: '2021-12-31',
      reason: 'A fast fall and a fast recovery, to see how quickly the rules react.',
    },
    {
      id: 'all-data',
      label: 'All the data there is',
      start: DATA_FLOOR,
      end,
      reason: 'Every daily bar the data provider has, from January 2016.',
    },
  ];
}

const DAY_MS = 86_400_000;
/** Ends this close count as the same range: weekends, holidays and a run started a day later. */
const MATCH_DAYS = 7;

const ms = (iso: string) => Date.parse(`${iso}T00:00:00Z`);

/** Whether a run over `start`..`end` covers the curated `range`, give or take a week. */
export function coversRange(start: Date, end: Date, range: CuratedRange): boolean {
  return (
    Math.abs(start.getTime() - ms(range.start)) <= MATCH_DAYS * DAY_MS &&
    Math.abs(end.getTime() - ms(range.end)) <= MATCH_DAYS * DAY_MS
  );
}

/** Whether a run starts at the data floor, give or take a week. */
export function startsAtFloor(start: Date): boolean {
  return Math.abs(start.getTime() - ms(DATA_FLOOR)) <= MATCH_DAYS * DAY_MS;
}

/** The hard stretches that fall wholly inside a run's dates. */
export function stretchesWithin(start: Date, end: Date): HardStretch[] {
  return HARD_STRETCHES.filter((s) => ms(s.start) >= start.getTime() && ms(s.end) <= end.getTime());
}

export interface StretchFigures {
  stretch: HardStretch;
  /** Deepest fall from the running peak inside the stretch, as a negative fraction. */
  run: number;
  bench: number | null;
}

function deepestFall(values: readonly number[]): number {
  let peak = -Infinity;
  let worst = 0;
  for (const v of values) {
    peak = Math.max(peak, v);
    if (peak > 0) worst = Math.min(worst, v / peak - 1);
  }
  return worst;
}

function inside<T>(dates: readonly Date[], values: readonly T[], from: number, to: number): T[] {
  return values.filter((_, i) => dates[i].getTime() >= from && dates[i].getTime() <= to);
}

/** Each hard stretch's deepest fall for the run and the benchmark, on their own dates. */
export function stretchFigures(
  stretches: readonly HardStretch[],
  dates: readonly Date[],
  values: readonly number[],
  bench: readonly (number | null)[] | null
): StretchFigures[] {
  return stretches.map((stretch) => {
    const from = ms(stretch.start);
    const to = ms(stretch.end);
    const runVals = inside(dates, values, from, to);
    const benchVals = bench
      ? inside(dates, bench, from, to).filter((v): v is number => v !== null)
      : [];
    return {
      stretch,
      run: deepestFall(runVals),
      bench: benchVals.length > 1 ? deepestFall(benchVals) : null,
    };
  });
}

/**
 * Trading days from the end of a stretch until the series is back at its high from before the
 * stretch; null when it never gets back inside the data.
 */
export function daysBackToHigh(
  dates: readonly Date[],
  values: readonly (number | null)[],
  stretch: HardStretch
): number | null {
  const from = ms(stretch.start);
  const to = ms(stretch.end);
  let high = -Infinity;
  let endIdx = -1;
  for (let i = 0; i < dates.length; i++) {
    const v = values[i];
    if (v === null) continue;
    if (dates[i].getTime() <= from) high = Math.max(high, v);
    if (dates[i].getTime() <= to) endIdx = i;
  }
  if (high === -Infinity || endIdx < 0) return null;
  for (let i = endIdx; i < dates.length; i++) {
    const v = values[i];
    if (v !== null && v >= high) return i - endIdx;
  }
  return null;
}
