/* eslint-disable import/order -- vi.mock must be hoisted above the mocked-module imports */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { getHistoricalBars, getSnapshot, getAssets, listPortfolios, getPositions } = vi.hoisted(
  () => ({
    getHistoricalBars: vi.fn(),
    getSnapshot: vi.fn(),
    getAssets: vi.fn(),
    listPortfolios: vi.fn(),
    getPositions: vi.fn(),
  })
);

let tenantContext: { tenantId: string; userId: string } | undefined = { tenantId: 't1', userId: 'u1' };
vi.mock('@llamatrade/core/net', () => ({
  marketDataClient: { getHistoricalBars, getSnapshot, getAssets },
  portfolioClient: { listPortfolios, getPositions },
  getTenantContext: () => tenantContext,
}));

import { Timeframe } from '@llamatrade/core/proto/market_data_pb';
import {
  barsToCandles,
  PERIOD_CONFIG,
  quoteFromCandles,
  snapshotToQuote,
  useMarketsStore,
  type Candle,
} from '@llamatrade/core/stores/markets';

const dec = (value: number) => ({ value: String(value) });
const ts = (seconds: number) => ({ seconds: BigInt(seconds), nanos: 0 });

function bar(seconds: number, o: number, h: number, l: number, c: number, v: number) {
  return {
    symbol: 'X',
    timestamp: ts(seconds),
    open: dec(o),
    high: dec(h),
    low: dec(l),
    close: dec(c),
    volume: BigInt(v),
    tradeCount: 0n,
  } as unknown as Parameters<typeof barsToCandles>[0][number];
}

const INITIAL = useMarketsStore.getState();

beforeEach(() => {
  vi.clearAllMocks();
  tenantContext = { tenantId: 't1', userId: 'u1' };
  useMarketsStore.setState({
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
    ensureInit: INITIAL.ensureInit,
    setSymbol: INITIAL.setSymbol,
    setPeriod: INITIAL.setPeriod,
    setChartType: INITIAL.setChartType,
    refresh: INITIAL.refresh,
  });
});

describe('barsToCandles', () => {
  it('sorts ascending, parses decimals, and drops duplicate timestamps', () => {
    const candles = barsToCandles([
      bar(200, 2, 3, 1, 2.5, 10),
      bar(100, 1, 2, 0.5, 1.5, 20),
      bar(200, 9, 9, 9, 9, 99), // duplicate time — dropped
    ]);
    expect(candles.map((c) => c.time)).toEqual([100, 200]);
    expect(candles[0]).toEqual({ time: 100, open: 1, high: 2, low: 0.5, close: 1.5, volume: 20 });
  });

  it('skips bars without a timestamp', () => {
    const missing = { symbol: 'X', open: dec(1), high: dec(1), low: dec(1), close: dec(1), volume: 0n } as unknown as Parameters<typeof barsToCandles>[0][number];
    expect(barsToCandles([missing])).toEqual([]);
  });
});

describe('snapshotToQuote', () => {
  it('prefers the latest trade price and pulls day stats from the daily bar', () => {
    const quote = snapshotToQuote({
      symbol: 'AAPL',
      latestTrade: { price: dec(144.29) },
      dailyBar: { high: dec(144.34), low: dec(142.28), volume: 77_620_000n, close: dec(144) },
      change: dec(1.29),
      changePercent: dec(0.9),
    } as unknown as Parameters<typeof snapshotToQuote>[0]);
    expect(quote).toEqual({
      price: 144.29,
      change: 1.29,
      changePercent: 0.9,
      dayHigh: 144.34,
      dayLow: 142.28,
      volume: 77_620_000,
    });
  });

  it('returns null when no price can be resolved', () => {
    expect(snapshotToQuote({ symbol: 'X' } as unknown as Parameters<typeof snapshotToQuote>[0])).toBeNull();
    expect(snapshotToQuote(undefined)).toBeNull();
  });
});

describe('quoteFromCandles', () => {
  it('derives change from the last two closes', () => {
    const candles: Candle[] = [
      { time: 1, open: 10, high: 11, low: 9, close: 10, volume: 5 },
      { time: 2, open: 10, high: 13, low: 10, close: 12, volume: 8 },
    ];
    expect(quoteFromCandles(candles)).toEqual({
      price: 12,
      change: 2,
      changePercent: 20,
      dayHigh: 13,
      dayLow: 10,
      volume: 8,
    });
  });

  it('returns null for an empty series', () => {
    expect(quoteFromCandles([])).toBeNull();
  });
});

describe('PERIOD_CONFIG', () => {
  it('maps each preset to the expected resolution', () => {
    expect(PERIOD_CONFIG['5M'].timeframe).toBe(Timeframe.TIMEFRAME_5MIN);
    expect(PERIOD_CONFIG['1D'].timeframe).toBe(Timeframe.TIMEFRAME_1DAY);
    expect(PERIOD_CONFIG['1M'].timeframe).toBe(Timeframe.TIMEFRAME_1MONTH);
  });
});

describe('ensureInit', () => {
  it('defaults to the largest holding and builds a watchlist', async () => {
    listPortfolios.mockResolvedValue({ portfolios: [{ id: 'p1' }] });
    getPositions.mockResolvedValue({
      positions: [
        { symbol: 'TSLA', marketValue: dec(500) },
        { symbol: 'NVDA', marketValue: dec(9000) },
      ],
    });
    getAssets.mockResolvedValue({ assets: { NVDA: { name: 'NVIDIA Corp' } } });
    getHistoricalBars.mockResolvedValue({ bars: [bar(100, 1, 2, 1, 1.5, 3)] });
    getSnapshot.mockResolvedValue({ symbol: 'NVDA', latestTrade: { price: dec(1.5) } });

    await useMarketsStore.getState().ensureInit();

    const s = useMarketsStore.getState();
    expect(s.symbol).toBe('NVDA'); // largest marketValue wins
    expect(s.assetName).toBe('NVIDIA Corp');
    expect(s.watchlist.find((w) => w.symbol === 'NVDA')?.held).toBe(true);
    expect(s.watchlist.some((w) => w.symbol === 'SPY')).toBe(true); // popular appended
    expect(getHistoricalBars).toHaveBeenCalledWith(
      expect.objectContaining({ symbol: 'NVDA', timeframe: Timeframe.TIMEFRAME_1DAY })
    );
    expect(s.candles).toHaveLength(1);
  });

  it('falls back to SPY when there are no positions', async () => {
    listPortfolios.mockResolvedValue({ portfolios: [{ id: 'p1' }] });
    getPositions.mockResolvedValue({ positions: [] });
    getAssets.mockResolvedValue({ assets: {} });
    getHistoricalBars.mockResolvedValue({ bars: [] });
    getSnapshot.mockResolvedValue(null);

    await useMarketsStore.getState().ensureInit();
    expect(useMarketsStore.getState().symbol).toBe('SPY');
  });

  it('falls back to SPY without hitting portfolio APIs when unauthenticated', async () => {
    tenantContext = undefined;
    getAssets.mockResolvedValue({ assets: {} });
    getHistoricalBars.mockResolvedValue({ bars: [] });
    getSnapshot.mockResolvedValue(null);

    await useMarketsStore.getState().ensureInit();
    expect(listPortfolios).not.toHaveBeenCalled();
    expect(useMarketsStore.getState().symbol).toBe('SPY');
  });

  it('is idempotent — a second call does not refetch', async () => {
    listPortfolios.mockResolvedValue({ portfolios: [{ id: 'p1' }] });
    getPositions.mockResolvedValue({ positions: [] });
    getAssets.mockResolvedValue({ assets: {} });
    getHistoricalBars.mockResolvedValue({ bars: [] });
    getSnapshot.mockResolvedValue(null);

    await useMarketsStore.getState().ensureInit();
    await useMarketsStore.getState().ensureInit();
    expect(getHistoricalBars).toHaveBeenCalledTimes(1);
  });
});

describe('setSymbol', () => {
  it('uses the snapshot for the header quote', async () => {
    getHistoricalBars.mockResolvedValue({ bars: [bar(100, 1, 2, 1, 1.5, 3)] });
    getSnapshot.mockResolvedValue({
      symbol: 'AAPL',
      latestTrade: { price: dec(144.29) },
      dailyBar: { high: dec(145), low: dec(142), volume: 1000n },
      change: dec(1.29),
      changePercent: dec(0.9),
    });

    await useMarketsStore.getState().setSymbol('aapl');
    const s = useMarketsStore.getState();
    expect(s.symbol).toBe('AAPL');
    expect(s.quote?.price).toBe(144.29);
    expect(s.quote?.dayHigh).toBe(145);
  });

  it('derives a quote from candles when the snapshot is missing', async () => {
    getHistoricalBars.mockResolvedValue({
      bars: [bar(100, 10, 11, 9, 10, 5), bar(200, 10, 13, 10, 12, 8)],
    });
    getSnapshot.mockResolvedValue(null);

    await useMarketsStore.getState().setSymbol('XYZ');
    expect(useMarketsStore.getState().quote?.price).toBe(12);
    expect(useMarketsStore.getState().quote?.change).toBe(2);
  });
});

describe('race guard', () => {
  it('ignores a stale response when a newer request has commenced', async () => {
    let resolveSlow: (v: unknown) => void = () => {};
    const slow = new Promise((r) => (resolveSlow = r));
    getSnapshot.mockResolvedValue(null);

    // First request hangs on the bars call.
    getHistoricalBars.mockReturnValueOnce(slow);
    const first = useMarketsStore.getState().setSymbol('SLOW');

    // Second request resolves immediately and should win.
    getHistoricalBars.mockResolvedValueOnce({ bars: [bar(300, 5, 5, 5, 5, 1)] });
    await useMarketsStore.getState().setSymbol('FAST');

    // Now let the stale first request finish.
    resolveSlow({ bars: [bar(100, 1, 1, 1, 1, 1)] });
    await first;

    const s = useMarketsStore.getState();
    expect(s.symbol).toBe('FAST');
    expect(s.candles).toHaveLength(1);
    expect(s.candles[0].time).toBe(300); // FAST's data, not the stale SLOW data
  });
});
