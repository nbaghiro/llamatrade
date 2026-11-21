import { toDate } from '@llamatrade/core/format';
import { marketDataClient } from '@llamatrade/core/net';
import { MarketStatus, Timeframe } from '@llamatrade/core/proto/market_data_pb';
import { barsToCandles, snapshotToQuote, type Candle } from '@llamatrade/core/stores/markets';
import { create } from 'zustand';

import { RANGE_DAYS, type Move, type Range } from './model';

const DAY_MS = 86_400_000;
const SPARK_DAYS = 45;

function ts(date: Date): { seconds: bigint; nanos: number } {
  return { seconds: BigInt(Math.floor(date.getTime() / 1000)), nanos: 0 };
}

export interface Clock {
  status: MarketStatus;
  nextOpen: Date | null;
  nextClose: Date | null;
}

interface BoardState {
  moves: Record<string, Move>;
  /** Daily closes for the row sparklines, oldest first. */
  sparks: Record<string, number[]>;
  names: Record<string, string>;
  clock: Clock | null;
  loading: boolean;
  error: string | null;
  /** Quotes, sparklines and names for these symbols; symbols already loaded are refreshed. */
  load: (symbols: readonly string[]) => Promise<void>;
  loadClock: () => Promise<void>;
}

/** Prices for the Markets rows: one snapshot call and one daily-bars call for every symbol. */
export const useBoard = create<BoardState>((set, get) => ({
  moves: {},
  sparks: {},
  names: {},
  clock: null,
  loading: false,
  error: null,

  load: async (symbols) => {
    const list = [...new Set(symbols.filter(Boolean))];
    if (list.length === 0) return;
    set({ loading: true, error: null });
    const end = new Date();
    const start = new Date(end.getTime() - SPARK_DAYS * DAY_MS);
    const [snaps, bars, assets] = await Promise.all([
      marketDataClient.getSnapshots({ symbols: list }).then((r) => r.snapshots).catch(() => null),
      marketDataClient
        .getMultiBars({ symbols: list, timeframe: Timeframe.TIMEFRAME_1DAY, start: ts(start), end: ts(end) })
        .then((r) => r.bars)
        .catch(() => null),
      marketDataClient.getAssets({ symbols: list.filter((s) => !get().names[s]) }).then((r) => r.assets).catch(() => null),
    ]);
    const moves: Record<string, Move> = {};
    const sparks: Record<string, number[]> = {};
    for (const sym of list) {
      const q = snapshotToQuote(snaps?.[sym]);
      if (q) moves[sym] = { price: q.price, changePct: q.changePercent };
      const series = bars?.[sym]?.bars ?? [];
      if (series.length > 1) sparks[sym] = barsToCandles(series).map((c) => c.close);
    }
    const names: Record<string, string> = {};
    for (const [sym, asset] of Object.entries(assets ?? {})) if (asset.name) names[sym] = asset.name;
    set((s) => ({
      moves: { ...s.moves, ...moves },
      sparks: { ...s.sparks, ...sparks },
      names: { ...s.names, ...names },
      loading: false,
      error: snaps === null && Object.keys(s.moves).length === 0 ? 'Prices could not be loaded.' : null,
    }));
  },

  loadClock: async () => {
    try {
      const r = await marketDataClient.getMarketStatus({});
      set({ clock: { status: r.status, nextOpen: toDate(r.nextOpen), nextClose: toDate(r.nextClose) } });
    } catch {
      set({ clock: null });
    }
  },
}));

/** "Open until 16:00" / "Opens Mon 09:30" in the device's time, or null without a clock. */
export function clockLine(clock: Clock | null, hhmm: (t: number) => string): string | null {
  if (!clock) return null;
  const weekday = (d: Date) => ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d.getDay()];
  switch (clock.status) {
    case MarketStatus.OPEN:
      return clock.nextClose ? `Open until ${hhmm(clock.nextClose.getTime())}` : 'Open';
    case MarketStatus.PRE_MARKET:
      return clock.nextOpen ? `Opens ${hhmm(clock.nextOpen.getTime())}` : 'Pre-market';
    case MarketStatus.AFTER_HOURS:
      return 'After hours';
    case MarketStatus.CLOSED:
      return clock.nextOpen ? `Opens ${weekday(clock.nextOpen)} ${hhmm(clock.nextOpen.getTime())}` : 'Closed';
    default:
      return null;
  }
}

export interface SymbolSeries {
  candles: Candle[];
  error: string | null;
}

const RANGE_TIMEFRAME: Record<Range, Timeframe> = {
  '1D': Timeframe.TIMEFRAME_5MIN,
  '1M': Timeframe.TIMEFRAME_1DAY,
  '6M': Timeframe.TIMEFRAME_1DAY,
  '1Y': Timeframe.TIMEFRAME_1DAY,
};

/** One symbol's candles for a range. */
export async function loadSeries(symbol: string, range: Range): Promise<SymbolSeries> {
  const end = new Date();
  // A day's five-minute bars: reach back far enough to cover a weekend.
  const days = range === '1D' ? 4 : RANGE_DAYS[range];
  const start = new Date(end.getTime() - days * DAY_MS);
  try {
    const res = await marketDataClient.getHistoricalBars({
      symbol,
      timeframe: RANGE_TIMEFRAME[range],
      start: ts(start),
      end: ts(end),
      adjustForSplits: true,
    });
    let candles = barsToCandles(res.bars);
    if (range === '1D' && candles.length) {
      const lastDay = new Date(candles[candles.length - 1].time * 1000).toDateString();
      candles = candles.filter((c) => new Date(c.time * 1000).toDateString() === lastDay);
    }
    return { candles, error: null };
  } catch (e) {
    return { candles: [], error: e instanceof Error ? e.message : 'Prices could not be loaded.' };
  }
}
