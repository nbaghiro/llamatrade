import { MarketStatus } from '@llamatrade/core/proto/market_data_pb';

/** Regular session in minutes after midnight, New York time. Holidays are not modelled. */
const OPEN_MIN = 9 * 60 + 30;
const CLOSE_MIN = 16 * 60;
const TZ = 'America/New_York';

export interface EtParts {
  year: number;
  month: number;
  day: number;
  weekday: number;
  minutes: number;
}

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export function etParts(d: Date): EtParts {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: TZ,
    hour12: false,
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    weekday: 'short',
  }).formatToParts(d);
  const get = (t: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === t)?.value ?? '';
  return {
    year: Number(get('year')),
    month: Number(get('month')) - 1,
    day: Number(get('day')),
    weekday: WEEKDAYS.indexOf(get('weekday')),
    minutes: (Number(get('hour')) % 24) * 60 + Number(get('minute')),
  };
}

function clock(minutes: number): string {
  return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}`;
}

const isWeekday = (weekday: number) => weekday >= 1 && weekday <= 5;

/** True when the regular session is open by the ET wall clock. */
export function isSessionOpen(now: Date): boolean {
  const p = etParts(now);
  return isWeekday(p.weekday) && p.minutes >= OPEN_MIN && p.minutes < CLOSE_MIN;
}

/** Calendar distance in days between two ET dates. */
function dayDistance(a: EtParts, b: EtParts): number {
  return Math.round((Date.UTC(b.year, b.month, b.day) - Date.UTC(a.year, a.month, a.day)) / 864e5);
}

/** "9:30 ET" for later today, "Mon 9:30 ET" for another day. */
export function describeOpen(nextOpen: Date, now: Date): string {
  const o = etParts(nextOpen);
  const n = etParts(now);
  const time = `${clock(o.minutes)} ET`;
  return dayDistance(n, o) === 0 ? time : `${WEEKDAYS[o.weekday]} ${time}`;
}

/** The next regular open by the wall clock, used when the market service gives none. */
export function derivedNextOpen(now: Date): Date {
  const p = etParts(now);
  let addDays = p.minutes < OPEN_MIN && isWeekday(p.weekday) ? 0 : 1;
  while (!isWeekday((p.weekday + addDays) % 7)) addDays += 1;
  return etToDate(p.year, p.month, p.day + addDays, OPEN_MIN);
}

/** The instant of a New York wall-clock time, correct across daylight-saving changes. */
export function etToDate(year: number, month: number, day: number, minutes: number): Date {
  const wanted = Date.UTC(year, month, day, 0, minutes);
  let guess = wanted + 5 * 3_600_000;
  for (let i = 0; i < 2; i++) {
    const g = etParts(new Date(guess));
    const seen = Date.UTC(g.year, g.month, g.day, 0, g.minutes);
    guess += wanted - seen;
  }
  return new Date(guess);
}

export interface MarketChip {
  open: boolean;
  text: string;
}

export interface MarketClockInput {
  status: MarketStatus | null;
  source: 'rpc' | 'derived';
  nextOpen: Date | null;
  now: Date;
}

export function marketChip({ status, source, nextOpen, now }: MarketClockInput): MarketChip {
  const fromService = source === 'rpc' && status !== null && status !== MarketStatus.UNSPECIFIED;
  const open = fromService ? status === MarketStatus.OPEN : isSessionOpen(now);
  if (open) return { open, text: `Market open · ${clock(etParts(now).minutes)} ET` };
  const label =
    fromService && status === MarketStatus.PRE_MARKET
      ? 'Pre-market'
      : fromService && status === MarketStatus.AFTER_HOURS
        ? 'After hours'
        : 'Market closed';
  const opens = fromService && nextOpen ? nextOpen : derivedNextOpen(now);
  return { open, text: `${label} · opens ${describeOpen(opens, now)}` };
}

/** "As of Fri, Nov 13 close": the most recent regular close at or before `now`. */
export function asOfCloseLabel(now: Date): string {
  const p = etParts(now);
  let back = isWeekday(p.weekday) && p.minutes >= CLOSE_MIN ? 0 : 1;
  while (!isWeekday((p.weekday - back + 7 * 7) % 7)) back += 1;
  const d = new Date(Date.UTC(p.year, p.month, p.day - back, 12));
  return `As of ${WEEKDAYS[d.getUTCDay()]}, ${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()} close`;
}

export interface BarClock {
  open: boolean;
  /** "10:42 ET" */
  time: string;
  /** "open", "closed", "pre-market" or "after hours" */
  state: string;
  /** The longer sentence for a tooltip, as the market chip words it. */
  detail: string;
}

/** The bar's clock (frame2 A): the New York time and whether the market is open. */
export function barClock(input: MarketClockInput): BarClock {
  const chip = marketChip(input);
  const time = `${clock(etParts(input.now).minutes)} ET`;
  const state = chip.open
    ? 'open'
    : chip.text.startsWith('Pre-market')
      ? 'pre-market'
      : chip.text.startsWith('After hours')
        ? 'after hours'
        : 'closed';
  return { open: chip.open, time, state, detail: chip.text };
}

/** "10:42" in New York time, for the Now marker and timestamps. */
export function etClock(d: Date): string {
  return clock(etParts(d).minutes);
}
