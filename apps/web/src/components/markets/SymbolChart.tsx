import { EmptyState, PanelError, SkeletonChart } from '../ui';

import { costLines, type Holder } from './marketsView';
import { PriceChart, type FillMark } from './PriceChart';
import type { PriceSeries } from './useMarketData';

interface SymbolChartProps {
  symbol: string;
  label: string;
  series: PriceSeries;
  intraday: boolean;
  holders: readonly Holder[];
  fills: readonly FillMark[];
  height: number;
  onRetry: () => void;
  costLabels?: boolean;
}

/** The selected symbol's prices with each sleeve's average cost and its fills, or why not. */
export function SymbolChart({
  symbol,
  label,
  series,
  intraday,
  holders,
  fills,
  height,
  onRetry,
  costLabels = true,
}: SymbolChartProps) {
  if (series.error) {
    return (
      <PanelError
        title={`${symbol} prices couldn't be loaded`}
        cause={series.error}
        onRetry={onRetry}
      />
    );
  }
  if (series.loading && series.candles.length === 0) return <SkeletonChart height={height} />;
  if (series.candles.length < 2) {
    return (
      <EmptyState title={`No prices for ${symbol} in this range`} body="Try a longer range." />
    );
  }
  return (
    <PriceChart
      label={label}
      candles={series.candles}
      intraday={intraday}
      costLines={costLines(holders)}
      fills={fills}
      height={height}
      costLabels={costLabels}
    />
  );
}
