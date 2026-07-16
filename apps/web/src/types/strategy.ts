export interface StrategyConfigJSON {
  name?: string;
  symbols: string[];
  timeframe: string;
  entry?: unknown;
  exit?: unknown;
  position_size_pct?: number;
  stop_loss_pct?: number;
  take_profit_pct?: number;
  trailing_stop_pct?: number;
}
