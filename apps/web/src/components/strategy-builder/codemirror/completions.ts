// Autocomplete support for the strategy DSL editor

import type { CompletionContext, CompletionResult, Completion } from '@codemirror/autocomplete';
import { autocompletion } from '@codemirror/autocomplete';

// Block type completions
const blockTypes: Completion[] = [
  { label: 'strategy', type: 'keyword', info: 'Define a trading strategy' },
  { label: 'weight', type: 'keyword', info: 'Set weight allocation method', detail: '(allocation ...)' },
  { label: 'allocation', type: 'keyword', info: 'Define portfolio allocation', detail: ':method :children' },
  { label: 'group', type: 'keyword', info: 'Group assets together', detail: ':name :children' },
  { label: 'asset', type: 'keyword', info: 'Add a tradable asset' },
  { label: 'if', type: 'keyword', info: 'Conditional block', detail: '(condition) (then ...) (else ...)' },
  { label: 'then', type: 'keyword', info: 'Then branch of conditional' },
  { label: 'else', type: 'keyword', info: 'Else branch of conditional' },
  { label: 'filter', type: 'keyword', info: 'Filter assets by criteria', detail: ':selection :count :sort-by' },
];

// Parameter completions
const parameters: Completion[] = [
  { label: ':name', type: 'property', info: 'Name of the strategy or group' },
  { label: ':method', type: 'property', info: 'Weight allocation method' },
  { label: ':symbol', type: 'property', info: 'Ticker symbol' },
  { label: ':weight', type: 'property', info: 'Weight percentage (0-1)' },
  { label: ':symbols', type: 'property', info: 'List of ticker symbols' },
  { label: ':timeframe', type: 'property', info: 'Trading timeframe (1D, 1H, etc.)' },
  { label: ':entry', type: 'property', info: 'Entry condition' },
  { label: ':exit', type: 'property', info: 'Exit condition' },
  { label: ':lookback-days', type: 'property', info: 'Lookback period in days' },
  { label: ':children', type: 'property', info: 'Child elements' },
  { label: ':selection', type: 'property', info: 'Filter selection (top/bottom)' },
  { label: ':count', type: 'property', info: 'Number of assets to select' },
  { label: ':sort-by', type: 'property', info: 'Sort criteria for filtering' },
  { label: ':universe', type: 'property', info: 'Asset universe for filtering' },
  { label: ':period', type: 'property', info: 'Time period for calculations' },
  { label: ':description', type: 'property', info: 'Strategy description' },
  { label: ':type', type: 'property', info: 'Strategy type' },
  { label: ':position-size', type: 'property', info: 'Position sizing percentage' },
  { label: ':stop-loss-pct', type: 'property', info: 'Stop loss percentage' },
  { label: ':take-profit-pct', type: 'property', info: 'Take profit percentage' },
  { label: ':rebalance', type: 'property', info: 'Rebalance frequency (daily, weekly, monthly, quarterly, annually)' },
  { label: ':benchmark', type: 'property', info: 'Benchmark symbol for comparison' },
];

// Weight method completions
const weightMethods: Completion[] = [
  { label: 'equal', type: 'type', info: 'Equal weight all assets' },
  { label: 'specified', type: 'type', info: 'Manually specified weights' },
  { label: 'momentum', type: 'type', info: 'Weight by momentum score' },
  { label: 'inverse-volatility', type: 'type', info: 'Weight inversely to volatility' },
  { label: 'min-variance', type: 'type', info: 'Minimum variance optimization' },
  { label: 'risk-parity', type: 'type', info: 'Risk parity weighting' },
];

// Filter methods
const filterMethods: Completion[] = [
  { label: 'top', type: 'type', info: 'Select top N assets' },
  { label: 'bottom', type: 'type', info: 'Select bottom N assets' },
];

// Sort criteria
const sortCriteria: Completion[] = [
  { label: 'momentum', type: 'type', info: 'Sort by momentum' },
  { label: 'market_cap', type: 'type', info: 'Sort by market cap' },
  { label: 'volume', type: 'type', info: 'Sort by volume' },
  { label: 'volatility', type: 'type', info: 'Sort by volatility' },
  { label: 'rsi', type: 'type', info: 'Sort by RSI' },
  { label: 'dividend_yield', type: 'type', info: 'Sort by dividend yield' },
];

// Rebalance frequency options
const rebalanceFrequencies: Completion[] = [
  { label: 'daily', type: 'type', info: 'Rebalance every trading day' },
  { label: 'weekly', type: 'type', info: 'Rebalance once per week' },
  { label: 'monthly', type: 'type', info: 'Rebalance once per month' },
  { label: 'quarterly', type: 'type', info: 'Rebalance once per quarter' },
  { label: 'annually', type: 'type', info: 'Rebalance once per year' },
];

// Indicator completions
// Syntax: (indicator SYMBOL params... [:output])
// Multi-output indicators support :output specifier for specific outputs
const indicators: Completion[] = [
  // Simple moving averages
  { label: 'sma', type: 'function', info: 'Simple Moving Average', detail: '(sma SYMBOL period)' },
  { label: 'ema', type: 'function', info: 'Exponential Moving Average', detail: '(ema SYMBOL period)' },

  // Momentum indicators
  { label: 'rsi', type: 'function', info: 'Relative Strength Index (0-100)', detail: '(rsi SYMBOL period)' },
  { label: 'cci', type: 'function', info: 'Commodity Channel Index', detail: '(cci SYMBOL period)' },
  { label: 'williams-r', type: 'function', info: 'Williams %R (-100 to 0)', detail: '(williams-r SYMBOL period)' },
  { label: 'momentum', type: 'function', info: 'Price Momentum', detail: '(momentum SYMBOL period)' },

  // Multi-output: MACD - outputs: :line (default), :signal, :histogram
  { label: 'macd', type: 'function', info: 'MACD (outputs: :line :signal :histogram)', detail: '(macd SYMBOL fast slow signal [:output])' },

  // Multi-output: Bollinger Bands - outputs: :upper, :middle (default), :lower
  { label: 'bbands', type: 'function', info: 'Bollinger Bands (outputs: :upper :middle :lower)', detail: '(bbands SYMBOL period stddev [:output])' },

  // Multi-output: Stochastic - outputs: :k (default), :d
  { label: 'stoch', type: 'function', info: 'Stochastic Oscillator (outputs: :k :d)', detail: '(stoch SYMBOL k_period d_period [:output])' },

  // Multi-output: ADX - outputs: :value (default), :plus_di, :minus_di
  { label: 'adx', type: 'function', info: 'Average Directional Index (outputs: :value :plus_di :minus_di)', detail: '(adx SYMBOL period [:output])' },

  // Volatility indicators
  { label: 'atr', type: 'function', info: 'Average True Range', detail: '(atr SYMBOL period)' },
  { label: 'stddev', type: 'function', info: 'Standard Deviation', detail: '(stddev SYMBOL period)' },

  // Channel indicators - outputs: :upper, :middle, :lower
  { label: 'keltner', type: 'function', info: 'Keltner Channel (outputs: :upper :middle :lower)', detail: '(keltner SYMBOL period multiplier [:output])' },
  { label: 'donchian', type: 'function', info: 'Donchian Channel (outputs: :upper :middle :lower)', detail: '(donchian SYMBOL period [:output])' },

  // Volume indicators
  { label: 'obv', type: 'function', info: 'On-Balance Volume', detail: '(obv SYMBOL)' },
  { label: 'mfi', type: 'function', info: 'Money Flow Index (0-100)', detail: '(mfi SYMBOL period)' },
  { label: 'vwap', type: 'function', info: 'Volume Weighted Average Price', detail: '(vwap SYMBOL)' },
];

// Price fields
const priceFields: Completion[] = [
  { label: 'close', type: 'variable', info: 'Closing price' },
  { label: 'open', type: 'variable', info: 'Opening price' },
  { label: 'high', type: 'variable', info: 'High price' },
  { label: 'low', type: 'variable', info: 'Low price' },
  { label: 'volume', type: 'variable', info: 'Trading volume' },
];

// Comparison operators
const operators: Completion[] = [
  { label: '>', type: 'operator', info: 'Greater than' },
  { label: '<', type: 'operator', info: 'Less than' },
  { label: '>=', type: 'operator', info: 'Greater than or equal' },
  { label: '<=', type: 'operator', info: 'Less than or equal' },
  { label: 'cross-above', type: 'operator', info: 'Crosses above' },
  { label: 'cross-below', type: 'operator', info: 'Crosses below' },
];

// Logical operators
const logicalOps: Completion[] = [
  { label: 'and', type: 'keyword', info: 'Logical AND' },
  { label: 'or', type: 'keyword', info: 'Logical OR' },
  { label: 'not', type: 'keyword', info: 'Logical NOT' },
];

// Common ticker symbols
const commonSymbols: Completion[] = [
  // Major ETFs
  { label: 'SPY', type: 'constant', info: 'SPDR S&P 500 ETF' },
  { label: 'QQQ', type: 'constant', info: 'Invesco QQQ Trust' },
  { label: 'IWM', type: 'constant', info: 'iShares Russell 2000' },
  { label: 'VTI', type: 'constant', info: 'Vanguard Total Stock Market' },
  { label: 'VOO', type: 'constant', info: 'Vanguard S&P 500' },
  { label: 'VEA', type: 'constant', info: 'Vanguard FTSE Developed' },
  { label: 'VWO', type: 'constant', info: 'Vanguard FTSE Emerging' },
  // Bonds
  { label: 'BND', type: 'constant', info: 'Vanguard Total Bond' },
  { label: 'TLT', type: 'constant', info: 'iShares 20+ Year Treasury' },
  { label: 'AGG', type: 'constant', info: 'iShares Core US Aggregate Bond' },
  { label: 'LQD', type: 'constant', info: 'iShares iBoxx Investment Grade' },
  // Sector ETFs
  { label: 'XLF', type: 'constant', info: 'Financial Select Sector' },
  { label: 'XLK', type: 'constant', info: 'Technology Select Sector' },
  { label: 'XLE', type: 'constant', info: 'Energy Select Sector' },
  { label: 'XLV', type: 'constant', info: 'Health Care Select Sector' },
  { label: 'XLI', type: 'constant', info: 'Industrial Select Sector' },
  // Commodities
  { label: 'GLD', type: 'constant', info: 'SPDR Gold Shares' },
  { label: 'SLV', type: 'constant', info: 'iShares Silver Trust' },
  { label: 'USO', type: 'constant', info: 'United States Oil Fund' },
  // Thematic
  { label: 'ARKK', type: 'constant', info: 'ARK Innovation' },
  { label: 'XBI', type: 'constant', info: 'SPDR S&P Biotech' },
];

/**
 * Get context-aware completions
 */
function getCompletions(context: CompletionContext): CompletionResult | null {
  // Get the text before the cursor
  const line = context.state.doc.lineAt(context.pos);
  const textBefore = line.text.slice(0, context.pos - line.from);

  // Check for explicit completion trigger
  const explicit = context.explicit;

  // Find the word being typed
  const wordMatch = textBefore.match(/[a-zA-Z0-9_:-]*$/);
  const word = wordMatch ? wordMatch[0] : '';
  const from = context.pos - word.length;

  // Don't complete if there's no word and it's not explicit
  if (!word && !explicit) {
    return null;
  }

  // Context-based completion
  let options: Completion[] = [];

  // Check if we're after :method
  if (/:\s*method\s+$/.test(textBefore) || /:\s*method\s+\S*$/.test(textBefore)) {
    options = weightMethods;
  }
  // Check if we're after :selection
  else if (/:\s*selection\s+$/.test(textBefore) || /:\s*selection\s+\S*$/.test(textBefore)) {
    options = filterMethods;
  }
  // Check if we're after :sort-by
  else if (/:\s*sort-by\s+$/.test(textBefore) || /:\s*sort-by\s+\S*$/.test(textBefore)) {
    options = sortCriteria;
  }
  // Check if we're after :rebalance
  else if (/:\s*rebalance\s+$/.test(textBefore) || /:\s*rebalance\s+\S*$/.test(textBefore)) {
    options = rebalanceFrequencies;
  }
  // Check if we're typing a parameter (starts with :)
  else if (word.startsWith(':')) {
    options = parameters;
  }
  // Check if we're in a condition context (after operators)
  else if (/\(\s*(>|<|>=|<=|cross-above|cross-below)\s*$/.test(textBefore)) {
    options = [...indicators, ...priceFields];
  }
  // Check if we're after an opening paren
  else if (/\(\s*$/.test(textBefore) || /\(\s*\S*$/.test(textBefore)) {
    options = [...blockTypes, ...indicators, ...operators, ...logicalOps];
  }
  // Check if we're after :symbol or :symbols
  else if (/:\s*symbols?\s+\[?["\s]*$/.test(textBefore) || /:\s*symbols?\s+\[?["\s]*\S*$/.test(textBefore)) {
    options = commonSymbols;
  }
  // Check if we're typing an uppercase word (likely a symbol)
  else if (/^[A-Z][A-Z0-9]*$/.test(word)) {
    options = commonSymbols;
  }
  // General completions
  else {
    options = [
      ...blockTypes,
      ...indicators,
      ...priceFields,
      ...operators,
      ...logicalOps,
      ...weightMethods,
    ];
  }

  // Filter options by the word being typed
  if (word && !word.startsWith(':')) {
    const lower = word.toLowerCase();
    options = options.filter(opt =>
      opt.label.toLowerCase().startsWith(lower)
    );
  }

  if (options.length === 0) {
    return null;
  }

  return {
    from,
    options,
    validFor: /^[a-zA-Z0-9_:-]*$/,
  };
}

/**
 * CodeMirror autocomplete extension for the strategy DSL
 */
export const dslAutocomplete = autocompletion({
  override: [getCompletions],
  icons: true,
  closeOnBlur: true,
  maxRenderedOptions: 20,
});

export { getCompletions };
