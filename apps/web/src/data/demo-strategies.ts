/**
 * Demo strategies with real DSL data for testing the strategy builder.
 * These will be replaced by API calls in production.
 */

export interface DemoStrategy {
  id: string;
  name: string;
  description: string;
  type: 'mean_reversion' | 'trend_following' | 'momentum' | 'breakout' | 'custom';
  status: 'active' | 'draft' | 'paused';
  symbols: string[];
  timeframe: string;
  created_at: string;
  updated_at: string;
  performance: {
    return: number;
    sharpe: number;
    maxDrawdown: number;
  };
  config_sexpr: string;
}

export const DEMO_STRATEGIES: DemoStrategy[] = [
  {
    id: '1',
    name: 'RSI Mean Reversion',
    description: 'Buy oversold, sell overbought using RSI indicator',
    type: 'mean_reversion',
    status: 'active',
    symbols: ['SPY', 'QQQ'],
    timeframe: '1D',
    created_at: '2024-02-20T10:00:00Z',
    updated_at: '2024-02-25T14:30:00Z',
    performance: { return: 12.4, sharpe: 1.82, maxDrawdown: -8.2 },
    config_sexpr: `(strategy
  :name "RSI Mean Reversion"
  :type mean_reversion
  :symbols ["SPY" "QQQ"]
  :timeframe "1D"
  :entry (< (rsi close 14) 30)
  :exit (> (rsi close 14) 70)
  :position-size-pct 10.0
  :stop-loss-pct 3.0
  :take-profit-pct 10.0)`,
  },
  {
    id: '2',
    name: 'MACD Crossover',
    description: 'Trend following using MACD signal crossovers',
    type: 'trend_following',
    status: 'active',
    symbols: ['AAPL', 'MSFT', 'GOOGL'],
    timeframe: '4H',
    created_at: '2024-02-18T08:00:00Z',
    updated_at: '2024-02-24T09:15:00Z',
    performance: { return: 8.7, sharpe: 1.45, maxDrawdown: -12.1 },
    config_sexpr: `(strategy
  :name "MACD Crossover"
  :type trend_following
  :symbols ["AAPL" "MSFT" "GOOGL"]
  :timeframe "4H"
  :entry (cross-above (macd-line close 12 26 9) (macd-signal close 12 26 9))
  :exit (cross-below (macd-line close 12 26 9) (macd-signal close 12 26 9))
  :position-size-pct 10.0
  :stop-loss-pct 4.0
  :take-profit-pct 12.0)`,
  },
  {
    id: '3',
    name: 'Momentum Top 10',
    description: 'Rotate into top momentum stocks monthly',
    type: 'momentum',
    status: 'draft',
    symbols: ['SPY'],
    timeframe: '1D',
    created_at: '2024-02-22T16:00:00Z',
    updated_at: '2024-02-22T16:00:00Z',
    performance: { return: -2.1, sharpe: 0.65, maxDrawdown: -15.3 },
    config_sexpr: `(strategy
  :name "Momentum Top 10"
  :type momentum
  :symbols ["SPY"]
  :timeframe "1D"
  :entry (and
    (> close (sma close 200))
    (> (roc close 252) 0))
  :exit (< close (sma close 200))
  :position-size-pct 50.0)`,
  },
  {
    id: '4',
    name: 'Golden Cross Strategy',
    description: '50/200 SMA crossover for long-term trend',
    type: 'trend_following',
    status: 'active',
    symbols: ['SPY'],
    timeframe: '1D',
    created_at: '2024-02-10T12:00:00Z',
    updated_at: '2024-02-25T08:00:00Z',
    performance: { return: 15.8, sharpe: 2.1, maxDrawdown: -6.5 },
    config_sexpr: `(strategy
  :name "Golden Cross Strategy"
  :type trend_following
  :symbols ["SPY"]
  :timeframe "1D"
  :entry (cross-above (sma close 50) (sma close 200))
  :exit (cross-below (sma close 50) (sma close 200))
  :position-size-pct 100.0
  :stop-loss-pct 10.0)`,
  },
  {
    id: '5',
    name: 'Bollinger Breakout',
    description: 'Trade breakouts from Bollinger Band squeezes',
    type: 'breakout',
    status: 'paused',
    symbols: ['NVDA', 'AMD', 'TSM'],
    timeframe: '1H',
    created_at: '2024-02-15T14:00:00Z',
    updated_at: '2024-02-23T11:30:00Z',
    performance: { return: 5.2, sharpe: 1.15, maxDrawdown: -9.8 },
    config_sexpr: `(strategy
  :name "Bollinger Breakout"
  :type breakout
  :symbols ["NVDA" "AMD" "TSM"]
  :timeframe "1H"
  :entry (and
    (> close (bb-upper close 20 2.0))
    (> (adx high low close 14) 25))
  :exit (< close (bb-middle close 20 2.0))
  :position-size-pct 5.0
  :stop-loss-pct 2.0
  :take-profit-pct 6.0)`,
  },
  {
    id: 'core-satellite',
    name: 'Core Satellite Strategy',
    description: 'Portfolio allocation with core holdings, growth, and bonds',
    type: 'custom',
    status: 'active',
    symbols: ['SPY', 'VTI', 'QQQ', 'ARKK', 'BND', 'TLT'],
    timeframe: '1D',
    created_at: '2024-01-10T10:00:00Z',
    updated_at: '2024-02-20T14:30:00Z',
    performance: { return: 9.2, sharpe: 1.65, maxDrawdown: -7.4 },
    // Special marker - this strategy uses portfolio builder format, not DSL
    config_sexpr: '__PORTFOLIO_CORE_SATELLITE__',
  },
];

/**
 * Get a demo strategy by ID
 */
export function getDemoStrategy(id: string): DemoStrategy | undefined {
  return DEMO_STRATEGIES.find((s) => s.id === id);
}

/**
 * Generate random chart data based on target return
 */
export function generateChartData(targetReturn: number): number[] {
  const points = 20;
  const data: number[] = [100];
  const trend = targetReturn / points;
  const volatility = Math.abs(targetReturn) * 0.15 + 1;

  for (let i = 1; i < points; i++) {
    const noise = (Math.random() - 0.5) * volatility;
    const newValue = data[i - 1] * (1 + (trend + noise) / 100);
    data.push(newValue);
  }
  return data;
}
