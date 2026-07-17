import { useEffect } from 'react';

import {
  MARKET_PERIODS,
  useMarketsStore,
  type ChartType,
  type MarketPeriod,
} from '@llamatrade/core/stores/markets';

import { colorForSign, fmtCompact, fmtCurrency, fmtSignedCurrency, fmtSignedPercent } from './format';
import PriceChart from './PriceChart';
import SymbolPicker from './SymbolPicker';

const CHART_TYPES: { key: ChartType; label: string }[] = [
  { key: 'line', label: 'Line' },
  { key: 'candlestick', label: 'Candle' },
];

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex flex-col leading-tight">
      <span className="font-mono text-[9px] font-bold uppercase tracking-[0.12em] text-ink/40">
        {label}
      </span>
      <span className="font-mono text-[12px] font-bold tabular-nums">{value}</span>
    </span>
  );
}

export default function MarketsView() {
  const {
    symbol,
    assetName,
    period,
    chartType,
    candles,
    quote,
    watchlist,
    loading,
    error,
    ensureInit,
    setSymbol,
    setPeriod,
    setChartType,
  } = useMarketsStore();

  useEffect(() => {
    ensureInit();
  }, [ensureInit]);

  const changeColor = quote ? colorForSign(quote.change) : undefined;

  return (
    <div className="flex flex-1 flex-col">
      <div className="px-[18px] pt-1 pb-1.5 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <SymbolPicker value={symbol} options={watchlist} onSelect={setSymbol} />
          {assetName && (
            <div className="font-mono text-[10px] text-ink/45 truncate mt-1 max-w-[220px]">
              {assetName}
            </div>
          )}
        </div>

        <div className="text-right shrink-0">
          <div className="font-mono font-bold text-[26px] leading-none tabular-nums tracking-[-0.01em]">
            {quote ? fmtCurrency(quote.price, 2) : '—'}
          </div>
          {quote && (
            <div
              className="font-mono text-[12px] font-bold tabular-nums mt-1"
              style={{ color: changeColor }}
            >
              {fmtSignedCurrency(quote.change, 2)} ({fmtSignedPercent(quote.changePercent)})
            </div>
          )}
        </div>
      </div>

      {quote && (
        <div className="px-[18px] pb-2 flex gap-5">
          <Stat label="Day Low" value={fmtCurrency(quote.dayLow, 2)} />
          <Stat label="Day High" value={fmtCurrency(quote.dayHigh, 2)} />
          <Stat label="Volume" value={fmtCompact(quote.volume)} />
        </div>
      )}

      <div className="px-[18px] py-1.5 flex items-center justify-between gap-2 border-t border-ink/10">
        <div className="flex gap-1.5">
          {MARKET_PERIODS.map((p: MarketPeriod) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`font-mono text-[10px] font-bold uppercase tracking-[0.04em] border-[1.5px] border-ink px-1.5 py-1 transition-colors ${
                period === p ? 'bg-ink text-bone' : 'bg-paper text-ink hover:bg-ink/5'
              }`}
            >
              {p}
            </button>
          ))}
        </div>
        <div className="flex">
          {CHART_TYPES.map((t) => (
            <button
              key={t.key}
              onClick={() => setChartType(t.key)}
              className={`font-mono text-[10px] font-bold uppercase tracking-[0.04em] border-[1.5px] border-ink px-2 py-1 -ml-[1.5px] first:ml-0 transition-colors ${
                chartType === t.key ? 'bg-ink text-bone' : 'bg-paper text-ink hover:bg-ink/5'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="px-3 pb-3 pt-1 flex flex-1 flex-col min-h-[260px]">
        {error ? (
          <div className="flex-1 flex items-center justify-center font-mono text-[11px] uppercase tracking-[0.08em] text-orange-700">
            {error}
          </div>
        ) : candles.length > 0 ? (
          <PriceChart candles={candles} type={chartType} />
        ) : (
          <div className="flex-1 flex items-center justify-center font-mono text-[11px] uppercase tracking-[0.08em] text-ink/40">
            {loading ? 'Loading price history…' : `No price history for ${symbol}`}
          </div>
        )}
      </div>
    </div>
  );
}
