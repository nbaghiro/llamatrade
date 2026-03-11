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
 * Seeded random number generator for consistent chart data
 */
function createSeededRandom(seed: number) {
  let s = seed;
  return () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
}

/**
 * Generate random chart data based on target return with variety
 */
export function generateChartData(targetReturn: number, seed?: number): number[] {
  const points = 20;
  const data: number[] = [100];
  const trend = targetReturn / points;

  // Use seed if provided, otherwise use targetReturn as seed for consistency
  const random = createSeededRandom(seed ?? Math.abs(targetReturn * 1000) + 1);

  // Vary volatility based on the seed
  const baseVolatility = Math.abs(targetReturn) * 0.2 + 1.5;
  const volatilityMultiplier = 0.8 + random() * 0.8; // 0.8 to 1.6x
  const volatility = baseVolatility * volatilityMultiplier;

  // Add some pattern variety: dips, rallies, consolidation
  const patternType = Math.floor(random() * 4);

  for (let i = 1; i < points; i++) {
    let patternModifier = 0;

    switch (patternType) {
      case 0: // Early dip then recovery
        patternModifier = i < 6 ? -0.3 : 0.15;
        break;
      case 1: // Late dip
        patternModifier = i > 14 ? -0.4 : 0.1;
        break;
      case 2: // Mid consolidation
        patternModifier = (i > 7 && i < 13) ? -0.2 : 0.1;
        break;
      case 3: // Steady with volatility spikes
        patternModifier = (i === 5 || i === 12) ? (random() - 0.5) * 2 : 0;
        break;
    }

    const noise = (random() - 0.5) * volatility;
    const trendWithPattern = trend + patternModifier;
    const newValue = data[i - 1] * (1 + (trendWithPattern + noise) / 100);
    data.push(newValue);
  }

  // Normalize to hit approximate target return
  const actualReturn = ((data[data.length - 1] - 100) / 100) * 100;
  const scale = targetReturn !== 0 ? targetReturn / actualReturn : 1;

  return data.map((v, i) => {
    if (i === 0) return 100;
    const normalized = 100 + (v - 100) * Math.abs(scale) * (scale > 0 ? 1 : -1);
    return normalized;
  });
}

/**
 * Generate benchmark (SPY) chart data with variety
 * Uses a seeded random for consistency across renders
 */
export function generateBenchmarkData(seed: number = 42): number[] {
  const points = 20;
  const data: number[] = [100];

  const random = createSeededRandom(seed);

  // Benchmark return varies between 4-12%
  const benchmarkReturn = 4 + random() * 8;
  const trend = benchmarkReturn / points;

  // Vary volatility
  const volatility = 1.2 + random() * 1.5;

  // Different pattern for benchmark
  const patternType = Math.floor(random() * 3);

  for (let i = 1; i < points; i++) {
    let patternModifier = 0;

    switch (patternType) {
      case 0: // Steady climb
        patternModifier = 0;
        break;
      case 1: // Small mid-period pullback
        patternModifier = (i > 8 && i < 12) ? -0.15 : 0.05;
        break;
      case 2: // Early strength, late weakness
        patternModifier = i < 10 ? 0.1 : -0.1;
        break;
    }

    const noise = (random() - 0.5) * volatility;
    const newValue = data[i - 1] * (1 + (trend + patternModifier + noise) / 100);
    data.push(newValue);
  }

  return data;
}

/**
 * Generate demo return/sharpe metrics for strategies without real data
 * First few items are always positive, then ~30% chance of negative for variety
 */
export function generateDemoMetrics(seed: number, index: number = 0): { returnPct: number; sharpeRatio: number } {
  const random = createSeededRandom(seed);
  // First 3 items are always positive, then ~30% chance of negative
  const isNegative = index >= 3 && random() < 0.3;

  const returnPct = isNegative
    ? -(1 + random() * 10) // -1% to -11%
    : 2 + random() * 14; // +2% to +16%

  const sharpeRatio = isNegative
    ? -0.1 + random() * 0.6 // -0.1 to 0.5 for losing strategies
    : 0.6 + random() * 1.5; // 0.6 to 2.1 for winning strategies

  return { returnPct, sharpeRatio };
}

/**
 * Backtest run result for display in the gallery
 */
export interface BacktestRun {
  id: string;
  strategyId: string;
  strategyName: string;
  returnPct: number;
  sharpeRatio: number;
  maxDrawdown: number;
  runDate: Date;
  equityCurve: number[];
  benchmarkCurve: number[];
}

/**
 * Generate mock backtest runs for the gallery
 * Returns a list of recent backtest results across strategies
 */
export function generateBacktestRuns(count: number = 10): BacktestRun[] {
  // Strategy names for mock backtests (mix of real and varied names)
  const strategyNames = [
    { id: 'global-macro', name: 'Global Macro Regime' },
    { id: 'risk-parity', name: 'Risk Parity' },
    { id: 'multi-sleeve', name: 'Multi-Sleeve Institutional' },
    { id: 'momentum-rotation', name: 'Momentum Rotation' },
    { id: 'rsi-mean-reversion', name: 'RSI Mean Reversion' },
    { id: 'golden-cross', name: 'Golden Cross' },
    { id: 'permanent-portfolio', name: 'Permanent Portfolio' },
    { id: 'dual-momentum', name: 'Dual Momentum' },
    { id: 'sector-rotation', name: 'Sector Rotation' },
    { id: 'volatility-targeting', name: 'Volatility Targeting' },
  ];

  const backtests: BacktestRun[] = [];
  const now = new Date();

  for (let i = 0; i < count; i++) {
    const seed = 1000 + i * 137; // Deterministic seed for each backtest
    const random = createSeededRandom(seed);

    // Pick a strategy (cycle through the list)
    const strategyInfo = strategyNames[i % strategyNames.length];

    // Generate varied but realistic metrics
    // ~30% chance of negative return for visual variety
    const isNegative = random() < 0.3;
    const returnPct = isNegative
      ? -(2 + random() * 12) // -2% to -14%
      : 2 + random() * 16; // +2% to +18%
    const sharpeRatio = isNegative
      ? -0.2 + random() * 0.8 // -0.2 to 0.6 for losing strategies
      : 0.5 + random() * 1.6; // 0.5 to 2.1 for winning strategies
    const maxDrawdown = -(5 + random() * 20); // -5% to -25%

    // Generate run date (spread over last 30 days)
    const daysAgo = Math.floor(random() * 30);
    const runDate = new Date(now);
    runDate.setDate(runDate.getDate() - daysAgo);

    backtests.push({
      id: `backtest-${i + 1}`,
      strategyId: strategyInfo.id,
      strategyName: strategyInfo.name,
      returnPct,
      sharpeRatio,
      maxDrawdown,
      runDate,
      equityCurve: generateChartData(returnPct, seed * 31 + 7),
      benchmarkCurve: generateBenchmarkData(seed * 17 + 42),
    });
  }

  // Sort by run date (most recent first)
  backtests.sort((a, b) => b.runDate.getTime() - a.runDate.getTime());

  return backtests;
}
