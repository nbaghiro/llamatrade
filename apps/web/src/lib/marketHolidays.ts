/**
 * NYSE full closures and 13:00 early closes, computed from the exchange's published rules.
 * Dates are calendar days at UTC midnight, as `etToday` and `nextRebalanceDate` use.
 */

export interface MarketDay {
  /** Closed all day. */
  closed: boolean;
  /** Closes at 13:00 ET instead of 16:00. */
  earlyClose: boolean;
  /** "Thanksgiving", "Day after Thanksgiving". */
  name: string | null;
}

const utc = (y: number, m: number, d: number) => new Date(Date.UTC(y, m, d));

/** The nth weekday of a month (n = -1 for the last). */
function nthWeekday(y: number, m: number, weekday: number, n: number): Date {
  if (n > 0) {
    const first = utc(y, m, 1).getUTCDay();
    return utc(y, m, 1 + ((weekday - first + 7) % 7) + (n - 1) * 7);
  }
  const lastDay = utc(y, m + 1, 0);
  return utc(y, m, lastDay.getUTCDate() - ((lastDay.getUTCDay() - weekday + 7) % 7));
}

/** Western Easter Sunday (anonymous Gregorian algorithm). */
function easter(y: number): Date {
  const a = y % 19;
  const b = Math.floor(y / 100);
  const c = y % 100;
  const d = Math.floor(b / 4);
  const e = b % 4;
  const f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4);
  const k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * m + 114) / 31) - 1;
  const day = ((h + l - 7 * m + 114) % 31) + 1;
  return utc(y, month, day);
}

/** A fixed-date holiday moved to Friday when it falls on Saturday and Monday on Sunday. */
function observed(d: Date): Date {
  const wd = d.getUTCDay();
  if (wd === 6) return utc(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() - 1);
  if (wd === 0) return utc(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + 1);
  return d;
}

const key = (d: Date) => d.toISOString().slice(0, 10);

function holidaysOf(y: number): Map<string, string> {
  const out = new Map<string, string>();
  const add = (d: Date, name: string) => out.set(key(d), name);
  // New Year's Day on a Saturday is not observed on the Friday before.
  const ny = utc(y, 0, 1);
  if (ny.getUTCDay() !== 6) add(observed(ny), "New Year's Day");
  add(nthWeekday(y, 0, 1, 3), 'Martin Luther King Jr. Day');
  add(nthWeekday(y, 1, 1, 3), "Presidents' Day");
  const e = easter(y);
  add(utc(y, e.getUTCMonth(), e.getUTCDate() - 2), 'Good Friday');
  add(nthWeekday(y, 4, 1, -1), 'Memorial Day');
  if (y >= 2022) add(observed(utc(y, 5, 19)), 'Juneteenth');
  add(observed(utc(y, 6, 4)), 'Independence Day');
  add(nthWeekday(y, 8, 1, 1), 'Labor Day');
  add(nthWeekday(y, 10, 4, 4), 'Thanksgiving');
  add(observed(utc(y, 11, 25)), 'Christmas');
  return out;
}

function earlyClosesOf(y: number): Map<string, string> {
  const out = new Map<string, string>();
  const weekday = (d: Date) => d.getUTCDay() >= 1 && d.getUTCDay() <= 5;
  const jul3 = utc(y, 6, 3);
  if (weekday(jul3) && utc(y, 6, 4).getUTCDay() !== 6)
    out.set(key(jul3), 'Day before Independence Day');
  const tg = nthWeekday(y, 10, 4, 4);
  out.set(key(utc(y, 10, tg.getUTCDate() + 1)), 'Day after Thanksgiving');
  const dec24 = utc(y, 11, 24);
  if (weekday(dec24)) out.set(key(dec24), 'Christmas Eve');
  return out;
}

const cache = new Map<number, { closed: Map<string, string>; early: Map<string, string> }>();

function yearOf(y: number) {
  let entry = cache.get(y);
  if (!entry) {
    entry = { closed: holidaysOf(y), early: earlyClosesOf(y) };
    cache.set(y, entry);
  }
  return entry;
}

/** What kind of trading day a calendar date is. Weekends are closed with no name. */
export function marketDay(d: Date): MarketDay {
  const wd = d.getUTCDay();
  if (wd === 0 || wd === 6) return { closed: true, earlyClose: false, name: null };
  const y = d.getUTCFullYear();
  // Dec 31 can carry the next year's observed New Year's Day.
  const holiday = yearOf(y).closed.get(key(d)) ?? yearOf(y + 1).closed.get(key(d));
  if (holiday) return { closed: true, earlyClose: false, name: holiday };
  const early = yearOf(y).early.get(key(d));
  if (early) return { closed: false, earlyClose: true, name: early };
  return { closed: false, earlyClose: false, name: null };
}

export const isTradingDay = (d: Date) => !marketDay(d).closed;

/** The same date when it trades, else the next one that does. */
export function tradingDayOnOrAfter(d: Date): Date {
  const out = new Date(d);
  while (!isTradingDay(out)) out.setUTCDate(out.getUTCDate() + 1);
  return out;
}

/** Trading days strictly after `from` and on or before `to`. */
export function tradingDaysBetween(from: Date, to: Date): number {
  let n = 0;
  const d = new Date(from);
  d.setUTCDate(d.getUTCDate() + 1);
  while (d.getTime() <= to.getTime()) {
    if (isTradingDay(d)) n += 1;
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return n;
}
