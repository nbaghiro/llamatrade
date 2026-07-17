// Markets store: drives the dashboard "Markets" view — a single-symbol price
// chart (candles + volume) from the market-data service. Self-contained.


import type { Decimal, Timestamp } from '@llamatrade/core/proto/common_pb';
import type { Bar, Snapshot } from '@llamatrade/core/proto/market_data_pb';
import { Timeframe } from '@llamatrade/core/proto/market_data_pb';
import { create } from 'zustand';

import { marketDataClient, portfolioClient } from '../net';
import { num } from '../format';

import { getTenantContext } from '../net';

export type MarketPeriod = '5M' | '1H' | '1D' | '1W' | '1M';
export const MARKET_PERIODS: MarketPeriod[] = ['5M', '1H', '1D', '1W', '1M'];

export type ChartType = 'candlestick' | 'line';

export interface Candle {
  time: number; // epoch seconds (lightweight-charts UTCTimestamp)
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface SymbolQuote {
  price: number;
  change: number; // absolute price change over the day
  changePercent: number;
  dayHigh: number;
  dayLow: number;
  volume: number;
}

export interface WatchItem {
  symbol: string;
  name: string;
  held: boolean;
  marketValue: number;
}

interface PeriodConfig {
  timeframe: Timeframe;
  lookbackMs: number;
}

// Each preset maps to a bar resolution + trailing window, mirroring how broker
// UIs (e.g. Alpaca) fold resolution and range into one control.
const DAY_MS = 86_400_000;
export const PERIOD_CONFIG: Record<MarketPeriod, PeriodConfig> = {
  '5M': { timeframe: Timeframe.TIMEFRAME_5MIN, lookbackMs: 2 * DAY_MS },
  '1H': { timeframe: Timeframe.TIMEFRAME_1HOUR, lookbackMs: 12 * DAY_MS },
  '1D': { timeframe: Timeframe.TIMEFRAME_1DAY, lookbackMs: 130 * DAY_MS },
  '1W': { timeframe: Timeframe.TIMEFRAME_1WEEK, lookbackMs: 730 * DAY_MS },
  '1M': { timeframe: Timeframe.TIMEFRAME_1MONTH, lookbackMs: 2200 * DAY_MS },
};

export const POPULAR_SYMBOLS = [
  'SPY',
  'QQQ',
  'AAPL',
  'MSFT',
  'NVDA',
  'TSLA',
  'AMZN',
  'GOOGL',
  'META',
  'AMD',
];
const DEFAULT_SYMBOL = 'SPY';

// ---- proto → local conversion ----

function toNum(d: Decimal | undefined): number {
  return num(d);
}

function tsSeconds(ts: Timestamp | undefined): number {
  return ts?.seconds ? Number(ts.seconds) : 0;
}

function toTimestamp(date: Date): { seconds: bigint; nanos: number } {
  const ms = date.getTime();
  return { seconds: BigInt(Math.floor(ms / 1000)), nanos: (ms % 1000) * 1_000_000 };
}

function barToCandle(bar: Bar): Candle | null {
  const time = tsSeconds(bar.timestamp);
  if (!time) return null;
  return {
    time,
    open: toNum(bar.open),
    high: toNum(bar.high),
    low: toNum(bar.low),
    close: toNum(bar.close),
    volume: Number(bar.volume),
  };
}

/** Ascending by time, dropping duplicate timestamps — charts require strictly increasing time. */
export function barsToCandles(bars: Bar[]): Candle[] {
  const sorted = [...bars].sort((a, b) => tsSeconds(a.timestamp) - tsSeconds(b.timestamp));
  const out: Candle[] = [];
  let lastTime = 0;
  for (const bar of sorted) {
    const candle = barToCandle(bar);
    if (candle && candle.time > lastTime) {
      out.push(candle);
      lastTime = candle.time;
    }
  }
  return out;
}

export function snapshotToQuote(snap: Snapshot | undefined): SymbolQuote | null {
  if (!snap) return null;
  const daily = snap.dailyBar;
  const price =
    toNum(snap.latestTrade?.price) || toNum(snap.latestBar?.close) || toNum(daily?.close);
  if (!price) return null;
  return {
    price,
    change: toNum(snap.change),
    changePercent: toNum(snap.changePercent),
    dayHigh: toNum(daily?.high),
    dayLow: toNum(daily?.low),
    volume: daily ? Number(daily.volume) : 0,
  };
}

/** Header stats derived from the loaded series when a live snapshot is unavailable. */
export function quoteFromCandles(candles: Candle[]): SymbolQuote | null {
  if (candles.length === 0) return null;
  const last = candles[candles.length - 1];
  const prev = candles.length > 1 ? candles[candles.length - 2] : last;
  const change = last.close - prev.close;
  return {
    price: last.close,
    change,
    changePercent: prev.close !== 0 ? (change / prev.close) * 100 : 0,
    dayHigh: last.high,
    dayLow: last.low,
    volume: last.volume,
  };
}

async function buildWatchlist(): Promise<{ watchlist: WatchItem[]; defaultSymbol: string }> {
  const context = getTenantContext();
  let held: { symbol: string; marketValue: number }[] = [];

  if (context) {
    try {
      const portfolios = await portfolioClient.listPortfolios({
        context,
        pagination: { page: 1, pageSize: 1 },
      });
      const portfolioId = portfolios.portfolios[0]?.id;
      if (portfolioId) {
        const res = await portfolioClient.getPositions({ context, portfolioId });
        held = res.positions
          .map((p) => ({ symbol: p.symbol, marketValue: toNum(p.marketValue) }))
          .filter((p) => p.symbol)
          .sort((a, b) => b.marketValue - a.marketValue);
      }
    } catch {
      held = [];
    }
  }

  const heldSymbols = held.map((h) => h.symbol);
  const symbols = [...heldSymbols, ...POPULAR_SYMBOLS.filter((s) => !heldSymbols.includes(s))];

  let names: Record<string, string> = {};
  try {
    const res = await marketDataClient.getAssets({ symbols });
    names = Object.fromEntries(
      Object.entries(res.assets).map(([sym, asset]) => [sym, asset.name] as [string, string])
    );
  } catch {
    names = {};
  }

  const heldSet = new Set(heldSymbols);
  const marketValues = new Map(held.map((h) => [h.symbol, h.marketValue]));
  const watchlist: WatchItem[] = symbols.map((symbol) => ({
    symbol,
    name: names[symbol] ?? '',
    held: heldSet.has(symbol),
    marketValue: marketValues.get(symbol) ?? 0,
  }));

  return { watchlist, defaultSymbol: heldSymbols[0] ?? DEFAULT_SYMBOL };
}

interface MarketsState {
  initialized: boolean;
  symbol: string;
  assetName: string;
  period: MarketPeriod;
  chartType: ChartType;
  candles: Candle[];
  quote: SymbolQuote | null;
  watchlist: WatchItem[];
  loading: boolean;
  error: string | null;

  ensureInit: () => Promise<void>;
  setSymbol: (symbol: string) => Promise<void>;
  setPeriod: (period: MarketPeriod) => Promise<void>;
  setChartType: (chartType: ChartType) => void;
  refresh: () => Promise<void>;
}

// Guards against out-of-order responses: only the newest request may commit.
let requestSeq = 0;

export const useMarketsStore = create<MarketsState>((set, get) => {
  async function loadSeries(symbol: string, period: MarketPeriod): Promise<void> {
    const seq = ++requestSeq;
    set({ loading: true, error: null });

    const cfg = PERIOD_CONFIG[period];
    const end = new Date();
    const start = new Date(end.getTime() - cfg.lookbackMs);

    try {
      const [barsRes, snapRes] = await Promise.all([
        marketDataClient.getHistoricalBars({
          symbol,
          timeframe: cfg.timeframe,
          start: toTimestamp(start),
          end: toTimestamp(end),
          adjustForSplits: true,
        }),
        marketDataClient.getSnapshot({ symbol }).catch(() => null),
      ]);
      if (seq !== requestSeq) return;

      const candles = barsToCandles(barsRes.bars);
      const quote = snapshotToQuote(snapRes ?? undefined) ?? quoteFromCandles(candles);
      set({ candles, quote, loading: false });
    } catch (error) {
      if (seq !== requestSeq) return;
      set({
        candles: [],
        quote: null,
        loading: false,
        error: error instanceof Error ? error.message : 'Failed to load market data',
      });
    }
  }

  return {
    initialized: false,
    symbol: '',
    assetName: '',
    period: '1D',
    chartType: 'candlestick',
    candles: [],
    quote: null,
    watchlist: [],
    loading: false,
    error: null,

    ensureInit: async () => {
      if (get().initialized) return;
      set({ initialized: true, loading: true });

      const { watchlist, defaultSymbol } = await buildWatchlist();
      const name = watchlist.find((w) => w.symbol === defaultSymbol)?.name ?? '';
      set({ watchlist, symbol: defaultSymbol, assetName: name });
      await loadSeries(defaultSymbol, get().period);
    },

    setSymbol: async (input) => {
      const symbol = input.trim().toUpperCase();
      if (!symbol || symbol === get().symbol) return;

      const known = get().watchlist.find((w) => w.symbol === symbol)?.name ?? '';
      set({ symbol, assetName: known });
      await loadSeries(symbol, get().period);

      if (!known) {
        try {
          const res = await marketDataClient.getAssets({ symbols: [symbol] });
          const resolved = res.assets[symbol]?.name;
          if (resolved && get().symbol === symbol) set({ assetName: resolved });
        } catch {
          // leave the name blank; the symbol still charts
        }
      }
    },

    setPeriod: async (period) => {
      if (period === get().period) return;
      set({ period });
      await loadSeries(get().symbol, period);
    },

    setChartType: (chartType) => set({ chartType }),

    refresh: async () => {
      const { symbol, period } = get();
      if (symbol) await loadSeries(symbol, period);
    },
  };
});
