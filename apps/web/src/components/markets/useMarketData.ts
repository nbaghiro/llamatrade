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

/** Latest quotes and short daily histories for a set of symbols, in two calls. */
export function useQuotes(symbols: readonly string[]): Quotes {
  const key = [...symbols].sort().join(',');
  const [state, setState] = useState<Quotes & { key: string }>({
    key: '',
    quotes: {},
    sparks: {},
    daily: {},
    loading: true,
  });

  useEffect(() => {
    if (!key) return;
    let live = true;
    const list = key.split(',');
    const end = new Date();
    Promise.all([
      marketDataClient.getSnapshots({ symbols: list }).catch(() => null),
      marketDataClient
        .getMultiBars({
          symbols: list,
          start: ts(new Date(end.getTime() - SPARK_DAYS * DAY)),
          end: ts(end),
          timeframe: Timeframe.TIMEFRAME_1DAY,
          limit: 0,
        })
        .catch(() => null),
    ]).then(([snaps, bars]) => {
      if (!live) return;
      const quotes: Record<string, SymbolQuote | null> = {};
      const daily: Record<string, Candle | null> = {};
      const sparks: Record<string, number[]> = {};
      for (const s of list) {
        const snap = snaps?.snapshots[s];
        quotes[s] = snapshotToQuote(snap);
        const d = snap?.dailyBar ? barsToCandles([snap.dailyBar])[0] : undefined;
        daily[s] = d ?? null;
        sparks[s] = barsToCandles(bars?.bars[s]?.bars ?? []).map((c) => c.close);
      }
      setState({ key, quotes, sparks, daily, loading: false });
    });
    return () => {
      live = false;
    };
  }, [key]);

  return state.key === key ? state : { ...state, loading: true };
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
