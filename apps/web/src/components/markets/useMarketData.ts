import { marketDataClient } from '@llamatrade/core/net';
import { Timeframe } from '@llamatrade/core/proto/market_data_pb';
import {
  barsToCandles,
  snapshotToQuote,
  type Candle,
  type SymbolQuote,
} from '@llamatrade/core/stores/markets';
import { useEffect, useState } from 'react';

import { etDayKey } from '../portfolio/history';

import { lastSessionOnly, rangeBars, type PriceRange } from './marketsView';
import { yearRange, type YearRange } from './quoteRows';

const DAY = 86_400_000;
const SPARK_DAYS = 45;

function ts(d: Date) {
  const ms = d.getTime();
  return { seconds: BigInt(Math.floor(ms / 1000)), nanos: 0 };
}

export interface Quotes {
  quotes: Record<string, SymbolQuote | null>;
  /** About a month of daily closes per symbol, for the watchlist lines. */
  sparks: Record<string, number[]>;
  /** Today's daily bar per symbol, for the figures under the chart. */
  daily: Record<string, Candle | null>;
  loading: boolean;
}

/** Latest quotes and short daily histories for a set of symbols; quotes don't wait for the bars. */
export function useQuotes(symbols: readonly string[]): Quotes {
  const key = [...symbols].sort().join(',');
  const [snap, setSnap] = useState<{
    key: string;
    quotes: Record<string, SymbolQuote | null>;
    daily: Record<string, Candle | null>;
  }>({ key: '', quotes: {}, daily: {} });
  const [spark, setSpark] = useState<{ key: string; sparks: Record<string, number[]> }>({
    key: '',
    sparks: {},
  });

  useEffect(() => {
    if (!key) return;
    let live = true;
    const list = key.split(',');
    const end = new Date();
    marketDataClient
      .getSnapshots({ symbols: list })
      .catch(() => null)
      .then((res) => {
        if (!live) return;
        const quotes: Record<string, SymbolQuote | null> = {};
        const daily: Record<string, Candle | null> = {};
        for (const s of list) {
          const one = res?.snapshots[s];
          quotes[s] = snapshotToQuote(one);
          daily[s] = (one?.dailyBar ? barsToCandles([one.dailyBar])[0] : undefined) ?? null;
        }
        setSnap({ key, quotes, daily });
      });
    marketDataClient
      .getMultiBars({
        symbols: list,
        start: ts(new Date(end.getTime() - SPARK_DAYS * DAY)),
        end: ts(end),
        timeframe: Timeframe.TIMEFRAME_1DAY,
        limit: 0,
      })
      .catch(() => null)
      .then((res) => {
        if (!live) return;
        const sparks: Record<string, number[]> = {};
        for (const s of list) {
          sparks[s] = barsToCandles(res?.bars[s]?.bars ?? []).map((c) => c.close);
        }
        setSpark({ key, sparks });
      });
    return () => {
      live = false;
    };
  }, [key]);

  return {
    quotes: snap.quotes,
    daily: snap.daily,
    sparks: spark.sparks,
    loading: snap.key !== key,
  };
}

const TIMEFRAME = {
  intraday5: Timeframe.TIMEFRAME_5MIN,
  hourly: Timeframe.TIMEFRAME_1HOUR,
  daily: Timeframe.TIMEFRAME_1DAY,
} as const;

export interface PriceSeries {
  candles: Candle[];
  name: string;
  exchange: string;
  loading: boolean;
  error: string | null;
}

/** One symbol's bars over a range, with its name and exchange. */
export function usePriceSeries(
  symbol: string,
  range: PriceRange,
  start: Date,
  attempt = 0
): PriceSeries {
  const startMs = start.getTime();
  const key = `${symbol}:${range}:${startMs}:${attempt}`;
  const [state, setState] = useState<PriceSeries & { key: string }>({
    key: '',
    candles: [],
    name: '',
    exchange: '',
    loading: true,
    error: null,
  });

  useEffect(() => {
    if (!symbol) return;
    let live = true;
    const bars = rangeBars(range);
    // A day back is padded so 1D still finds the last session over a weekend.
    const from = new Date(bars === 'intraday5' ? Date.now() - 5 * DAY : startMs);
    Promise.all([
      marketDataClient.getHistoricalBars({
        symbol,
        timeframe: TIMEFRAME[bars],
        start: ts(from),
        end: ts(new Date()),
        adjustForSplits: true,
      }),
      marketDataClient.getAssets({ symbols: [symbol] }).catch(() => null),
    ])
      .then(([res, assets]) => {
        if (!live) return;
        let candles = barsToCandles(res.bars);
        if (bars === 'intraday5')
          candles = lastSessionOnly(candles, (s) => etDayKey(new Date(s * 1000)));
        const asset = assets?.assets[symbol];
        setState({
          key,
          candles,
          name: asset?.name ?? '',
          exchange: asset?.exchange ?? '',
          loading: false,
          error: null,
        });
      })
      .catch((e: unknown) => {
        if (!live) return;
        setState({
          key,
          candles: [],
          name: '',
          exchange: '',
          loading: false,
          error: e instanceof Error ? e.message : 'Prices could not be loaded.',
        });
      });
    return () => {
      live = false;
    };
  }, [key, symbol, range, startMs]);

  return state.key === key ? state : { ...state, loading: true };
}

export interface QuoteExtras {
  names: Record<string, string>;
  intraday: Record<string, number[]>;
  years: Record<string, YearRange | null>;
}

const YEAR_CACHE = 'llamatrade-year-range';

function readYearCache(day: string): Record<string, YearRange | null> {
  try {
    const raw = window.sessionStorage.getItem(YEAR_CACHE);
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    if (
      parsed &&
      typeof parsed === 'object' &&
      'day' in parsed &&
      parsed.day === day &&
      'ranges' in parsed &&
      parsed.ranges &&
      typeof parsed.ranges === 'object'
    ) {
      return parsed.ranges as Record<string, YearRange | null>;
    }
  } catch {
    // Storage can be blocked; the ranges are fetched again.
  }
  return {};
}

function saveYearCache(day: string, ranges: Record<string, YearRange | null>) {
  try {
    window.sessionStorage.setItem(YEAR_CACHE, JSON.stringify({ day, ranges }));
  } catch {
    // Not cached; the next load fetches again.
  }
}

/** Names, the last session's 5-minute closes and the 52-week range for the quote table. */
export function useQuoteExtras(symbols: readonly string[]): QuoteExtras {
  const key = [...symbols].sort().join(',');
  const [state, setState] = useState<QuoteExtras & { key: string }>({
    key: '',
    names: {},
    intraday: {},
    years: {},
  });

  useEffect(() => {
    if (!key) return;
    let live = true;
    const list = key.split(',');
    const end = new Date();
    const day = etDayKey(end);
    const cached = readYearCache(day);
    const missing = list.filter((s) => !(s in cached));
    Promise.all([
      marketDataClient.getAssets({ symbols: list }).catch(() => null),
      marketDataClient
        .getMultiBars({
          symbols: list,
          start: ts(new Date(end.getTime() - 5 * DAY)),
          end: ts(end),
          timeframe: Timeframe.TIMEFRAME_5MIN,
          limit: 0,
        })
        .catch(() => null),
      missing.length
        ? marketDataClient
            .getMultiBars({
              symbols: missing,
              start: ts(new Date(end.getTime() - 366 * DAY)),
              end: ts(end),
              timeframe: Timeframe.TIMEFRAME_1DAY,
              limit: 0,
            })
            .catch(() => null)
        : Promise.resolve(null),
    ]).then(([assets, intraBars, yearBars]) => {
      if (!live) return;
      const names: Record<string, string> = {};
      const intraday: Record<string, number[]> = {};
      const years: Record<string, YearRange | null> = { ...cached };
      for (const s of list) {
        names[s] = assets?.assets[s]?.name ?? '';
        const candles = lastSessionOnly(barsToCandles(intraBars?.bars[s]?.bars ?? []), (sec) =>
          etDayKey(new Date(sec * 1000))
        );
        intraday[s] = candles.map((c) => c.close);
      }
      if (yearBars) {
        for (const s of missing) years[s] = yearRange(barsToCandles(yearBars.bars[s]?.bars ?? []));
        saveYearCache(day, years);
      }
      setState({ key, names, intraday, years });
    });
    return () => {
      live = false;
    };
  }, [key]);

  return state.key === key
    ? state
    : { names: state.names, intraday: state.intraday, years: state.years };
}

/** Whether Alpaca knows a symbol: listed as an asset, or at least quoted. */
export async function findAsset(symbol: string): Promise<{ symbol: string; name: string } | null> {
  const res = await marketDataClient.getAssets({ symbols: [symbol] });
  const asset = res.assets[symbol];
  if (asset) return { symbol, name: asset.name };
  const snaps = await marketDataClient.getSnapshots({ symbols: [symbol] });
  return snapshotToQuote(snaps.snapshots[symbol]) ? { symbol, name: '' } : null;
}
