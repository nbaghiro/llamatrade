import { POPULAR_SYMBOLS, type Candle, type SymbolQuote } from '@llamatrade/core/stores/markets';
import { usePortfolioStore, type SleeveSummary } from '@llamatrade/core/stores/portfolio';
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import type { SleeveFill } from '../portfolio/history';
import { shortDate, sleeveRunState } from '../portfolio/sleeveView';
import { useSleeveFills } from '../portfolio/usePortfolioData';
import { etToday } from '../sessions/sessionRows';

import {
  cleanSymbol,
  heldRows,
  rangeBars,
  rangeStart,
  rangeStats,
  readWatchlist,
  saveWatchlist,
  shares,
  type Holder,
  type PriceRange,
  type RangeStats,
  type WatchRow,
} from './marketsView';
import type { FillMark } from './PriceChart';
import { useQuotes, usePriceSeries, type PriceSeries } from './useMarketData';

export type MarketsView = 'map' | 'list';

export const RANGES: readonly { key: PriceRange; label: string }[] = [
  { key: '1D', label: '1D' },
  { key: '1W', label: '1W' },
  { key: '1M', label: '1M' },
  { key: '3M', label: '3M' },
  { key: 'start', label: 'Since start' },
  { key: '1Y', label: '1Y' },
];

export interface MarketsModel {
  view: MarketsView;
  setView: (v: MarketsView) => void;
  sleeves: SleeveSummary[];
  unallocated: number | null;
  loaded: boolean;
  portfolioError: string | null;
  retryPortfolio: () => void;
  held: WatchRow[];
  heldSymbols: string[];
  watching: string[];
  watchOnly: string[];
  watch: (next: string[]) => void;
  symbol: string;
  select: (symbol: string) => void;
  quotes: Record<string, SymbolQuote | null>;
  sparks: Record<string, number[]>;
  daily: Record<string, Candle | null>;
  range: PriceRange;
  setRange: (r: PriceRange) => void;
  rangeLabel: string;
  sinceLabel: string;
  intraday: boolean;
  series: PriceSeries;
  retrySeries: () => void;
  stats: RangeStats | null;
  quote: SymbolQuote | null;
  holders: Holder[];
  heldQty: number;
  heldValue: number;
  equity: number;
  now: Date;
  today: Date;
  symbolFills: SleeveFill[];
  fillMarks: FillMark[];
  sleeveById: Map<string | null, SleeveSummary>;
}

/** Everything both Markets views read: holdings, quotes, the selected symbol and its prices. */
export function useMarketsModel(): MarketsModel {
  const { sleeves, unallocated, loaded, error, fetchPortfolio } = usePortfolioStore();
  const { fills } = useSleeveFills();
  const [params, setParams] = useSearchParams();
  const [range, setRange] = useState<PriceRange>('3M');
  const [watching, setWatching] = useState<string[]>(() => readWatchlist());
  const [attempt, setAttempt] = useState(0);
  const [now] = useState(() => new Date());
  const today = etToday(now);

  useEffect(() => {
    if (!loaded) fetchPortfolio();
  }, [loaded, fetchPortfolio]);

  const held = useMemo(
    () => heldRows(sleeves.map((s) => ({ ...s, running: sleeveRunState(s) === 'running' }))),
    [sleeves]
  );
  const heldSymbols = useMemo(() => held.map((r) => r.symbol), [held]);
  const watchOnly = useMemo(
    () => watching.filter((s) => !heldSymbols.includes(s)),
    [watching, heldSymbols]
  );
  const symbol =
    cleanSymbol(params.get('symbol') ?? '') ?? heldSymbols[0] ?? watchOnly[0] ?? POPULAR_SYMBOLS[0];
  const allSymbols = useMemo(
    () => [...new Set([...heldSymbols, ...watchOnly, symbol])],
    [heldSymbols, watchOnly, symbol]
  );
  const { quotes, sparks, daily } = useQuotes(allSymbols);

  const firstStart =
    sleeves
      .map((s) => s.startedAt)
      .filter((d): d is Date => d !== null)
      .sort((a, b) => a.getTime() - b.getTime())[0] ?? null;
  const start = useMemo(() => rangeStart(range, now, firstStart), [range, now, firstStart]);
  const series = usePriceSeries(symbol, range, start, attempt);

  const holders = held.find((r) => r.symbol === symbol)?.holders ?? [];
  const sleeveById = new Map<string | null, SleeveSummary>(sleeves.map((s) => [s.sleeveId, s]));
  const symbolFills = fills.filter((f) => f.symbol === symbol);
  const fillMarks: FillMark[] = symbolFills
    .filter((f) => sleeveById.has(f.sleeveId))
    .map((f) => {
      const s = sleeveById.get(f.sleeveId);
      return {
        id: f.id,
        at: f.at,
        price: f.price,
        side: f.side,
        live: s?.live ?? false,
        title: `${f.side === 'buy' ? 'Bought' : 'Sold'} ${shares(f.qty)} at ${f.price.toFixed(2)}, ${s?.name ?? 'a sleeve'}`,
      };
    });

  const setParam = (key: string, value: string) => {
    const p = new URLSearchParams(params);
    p.set(key, value);
    setParams(p, { replace: true });
  };
  const rangeLabel = RANGES.find((r) => r.key === range)?.label ?? '';

  return {
    view: params.get('view') === 'list' ? 'list' : 'map',
    setView: (v) => setParam('view', v),
    sleeves,
    unallocated,
    loaded,
    portfolioError: error,
    retryPortfolio: () => {
      fetchPortfolio();
    },
    held,
    heldSymbols,
    watching,
    watchOnly,
    watch: (next) => {
      setWatching(next);
      saveWatchlist(next);
    },
    symbol,
    select: (s) => setParam('symbol', s),
    quotes,
    sparks,
    daily,
    range,
    setRange,
    rangeLabel,
    sinceLabel: range === 'start' && firstStart ? `Since ${shortDate(firstStart)}` : rangeLabel,
    intraday: rangeBars(range) !== 'daily',
    series,
    retrySeries: () => setAttempt((a) => a + 1),
    stats: rangeStats(series.candles, daily[symbol]),
    quote: quotes[symbol] ?? null,
    holders,
    heldQty: holders.reduce((s, h) => s + h.qty, 0),
    heldValue: holders.reduce((s, h) => s + h.marketValue, 0),
    equity: sleeves.reduce((s, x) => s + x.value, 0) + (unallocated ?? 0),
    now,
    today,
    symbolFills,
    fillMarks,
    sleeveById,
  };
}
