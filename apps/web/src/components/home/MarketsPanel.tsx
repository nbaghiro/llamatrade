import {
  MARKET_PERIODS,
  useMarketsStore,
  type MarketPeriod,
} from '@llamatrade/core/stores/markets';
import { useEffect, useMemo } from 'react';

import { formatMoney, formatNumber } from '../../lib/format';
import { LineChart } from '../charts';
import SymbolPicker from '../dashboard/SymbolPicker';
import { EmptyState, Money, PanelError, Segmented, SkeletonChart } from '../ui';

const INTRADAY: ReadonlySet<MarketPeriod> = new Set(['5M', '1H']);

function barTime(d: Date, period: MarketPeriod): string {
  const intraday = INTRADAY.has(period);
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: intraday ? 'numeric' : undefined,
    minute: intraday ? '2-digit' : undefined,
  });
}

const PERIOD_LABEL: Record<MarketPeriod, string> = {
  '5M': '5m',
  '1H': '1h',
  '1D': '1D',
  '1W': '1W',
  '1M': '1M',
};

/** Any symbol's recent price from the market data service. Prices are not P&L, so no gain/loss colour. */
export function MarketsPanel({ height = 232 }: { height?: number }) {
  const symbol = useMarketsStore((s) => s.symbol);
  const assetName = useMarketsStore((s) => s.assetName);
  const period = useMarketsStore((s) => s.period);
  const candles = useMarketsStore((s) => s.candles);
  const quote = useMarketsStore((s) => s.quote);
  const watchlist = useMarketsStore((s) => s.watchlist);
  const loading = useMarketsStore((s) => s.loading);
  const error = useMarketsStore((s) => s.error);
  const ensureInit = useMarketsStore((s) => s.ensureInit);
  const setSymbol = useMarketsStore((s) => s.setSymbol);
  const setPeriod = useMarketsStore((s) => s.setPeriod);
  const pick = (next: string) => {
    setSymbol(next).catch(() => undefined);
  };

  useEffect(() => {
    ensureInit().catch(() => undefined);
  }, [ensureInit]);

  const series = useMemo(
    () => ({
      dates: candles.map((c) => new Date(c.time * 1000)),
      closes: candles.map((c) => c.close),
    }),
    [candles]
  );

  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-2">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <SymbolPicker value={symbol} options={watchlist} onSelect={pick} />
          {assetName && (
            <div className="mt-0.5 max-w-[260px] truncate text-[11.5px] text-fg-3">{assetName}</div>
          )}
        </div>
        <div className="text-right">
          {quote ? (
            <>
              <Money value={quote.price} className="text-[20px]" />
              <div className="num text-[12px] text-fg-2">
                {formatMoney(quote.change, { signed: true })} ·{' '}
                {formatNumber(quote.changePercent, { signed: true })}% today
              </div>
            </>
          ) : (
            <span className="num text-[20px] text-fg-3">—</span>
          )}
        </div>
      </div>
      <div className="flex justify-end">
        <Segmented<MarketPeriod>
          label="Bar size"
          value={period}
          onChange={(p) => {
            setPeriod(p).catch(() => undefined);
          }}
          options={MARKET_PERIODS.map((p) => ({ key: p, label: PERIOD_LABEL[p] }))}
        />
      </div>
      {error ? (
        <PanelError
          title={`${symbol} prices couldn't be loaded`}
          cause={error}
          onRetry={() => pick(symbol)}
        />
      ) : series.closes.length > 1 ? (
        <LineChart
          label={`${symbol} closing prices`}
          dates={series.dates}
          series={[{ values: series.closes, kind: 'main' }]}
          height={height}
          yFormat={(v) => formatMoney(v, { dp: v >= 1000 ? 0 : 2 })}
          tooltip={(i) => `${barTime(series.dates[i], period)} · ${formatMoney(series.closes[i])}`}
        />
      ) : loading ? (
        <SkeletonChart height={height} />
      ) : (
        <EmptyState
          title={`No price history for ${symbol}`}
          body="Try another symbol or a different bar size."
        />
      )}
      <p className="m-0 text-[11.5px] text-fg-3">
        IEX data via Alpaca. IEX is one exchange, so prices can differ slightly from other quotes.
      </p>
    </div>
  );
}
