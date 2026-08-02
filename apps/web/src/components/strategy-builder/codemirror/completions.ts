// Autocomplete support for the strategy DSL editor

import type { CompletionContext, CompletionResult, Completion } from '@codemirror/autocomplete';
import { autocompletion } from '@codemirror/autocomplete';

// Every label below must be vocabulary the backend parser accepts
// (@llamatrade/core/strategy/vocabulary, generated from libs/dsl into
// tests/conformance/vocabulary.json). The dsl-conformance suite enforces that.

const blockTypes: Completion[] = [
  { label: 'strategy', type: 'keyword', info: 'Define a trading strategy', detail: '(strategy "Name" :rebalance ... blocks)' },
  { label: 'weight', type: 'keyword', info: 'Allocate across child blocks', detail: '(weight :method ... blocks)' },
  { label: 'group', type: 'keyword', info: 'Group assets together', detail: '(group "Name" [:weight N] blocks)' },
  { label: 'asset', type: 'keyword', info: 'Add a tradable asset', detail: '(asset SYMBOL [:weight N])' },
  { label: 'if', type: 'keyword', info: 'Conditional block', detail: '(if (condition) block [(else block)])' },
  { label: 'else', type: 'keyword', info: 'Else branch of a conditional', detail: '(else block)' },
  { label: 'filter', type: 'keyword', info: 'Rank and select assets', detail: '(filter :by ... :select (top N) blocks)' },
];

const parameters: Completion[] = [
  { label: ':rebalance', type: 'property', info: 'Rebalance frequency (daily, weekly, monthly, quarterly, annually)' },
  { label: ':benchmark', type: 'property', info: 'Benchmark symbol for comparison' },
  { label: ':description', type: 'property', info: 'Strategy description' },
  { label: ':method', type: 'property', info: 'Weight allocation method' },
  { label: ':lookback', type: 'property', info: 'Lookback period in days' },
  { label: ':top', type: 'property', info: 'Allocate to the top N children (momentum only)' },
  { label: ':weight', type: 'property', info: 'Weight percent, 0–100 (siblings sum to 100)' },
  { label: ':by', type: 'property', info: 'Filter criteria (momentum, volatility, volume)' },
  { label: ':select', type: 'property', info: 'Filter selection, e.g. (top 3)' },
  { label: ':close', type: 'property', info: 'Closing price field' },
  { label: ':open', type: 'property', info: 'Opening price field' },
  { label: ':high', type: 'property', info: 'High price field' },
  { label: ':low', type: 'property', info: 'Low price field' },
  { label: ':volume', type: 'property', info: 'Volume field' },
];

// market-cap parses but the validator rejects it (needs fundamentals), so it is not offered.
const weightMethods: Completion[] = [
  { label: 'equal', type: 'type', info: 'Equal weight all assets' },
  { label: 'specified', type: 'type', info: 'Manually specified weights' },
  { label: 'momentum', type: 'type', info: 'Weight by momentum score' },
  { label: 'inverse-volatility', type: 'type', info: 'Weight inversely to volatility' },
  { label: 'min-variance', type: 'type', info: 'Minimum variance optimization' },
  { label: 'risk-parity', type: 'type', info: 'Risk parity weighting' },
];

const filterMethods: Completion[] = [
  { label: 'top', type: 'type', info: 'Select top N assets' },
  { label: 'bottom', type: 'type', info: 'Select bottom N assets' },
];

const sortCriteria: Completion[] = [
  { label: 'momentum', type: 'type', info: 'Rank by momentum' },
  { label: 'volatility', type: 'type', info: 'Rank by volatility' },
  { label: 'volume', type: 'type', info: 'Rank by volume' },
];

const rebalanceFrequencies: Completion[] = [
  { label: 'daily', type: 'type', info: 'Rebalance every trading day' },
  { label: 'weekly', type: 'type', info: 'Rebalance once per week' },
  { label: 'monthly', type: 'type', info: 'Rebalance once per month' },
  { label: 'quarterly', type: 'type', info: 'Rebalance once per quarter' },
  { label: 'annually', type: 'type', info: 'Rebalance once per year' },
];

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
  { label: 'stoch', type: 'function', info: 'Stochastic Oscillator (outputs: :k :d)', detail: '(stoch SYMBOL k_period d_period smoothing [:output])' },

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

// Price fields are only valid as a keyword inside (price SYMBOL :field); the bare
// names are not values, so they are offered through `parameters` instead.
const metrics: Completion[] = [
  { label: 'price', type: 'function', info: 'Price of a symbol', detail: '(price SYMBOL [:field])' },
  { label: 'drawdown', type: 'function', info: 'Drawdown from peak', detail: '(drawdown SYMBOL)' },
  { label: 'return', type: 'function', info: 'Return over a period', detail: '(return SYMBOL [period])' },
  { label: 'volatility', type: 'function', info: 'Realized volatility', detail: '(volatility SYMBOL [period])' },
];

const operators: Completion[] = [
  { label: '>', type: 'operator', info: 'Greater than' },
  { label: '<', type: 'operator', info: 'Less than' },
  { label: '>=', type: 'operator', info: 'Greater than or equal' },
  { label: '<=', type: 'operator', info: 'Less than or equal' },
  { label: '=', type: 'operator', info: 'Equal to' },
  { label: '!=', type: 'operator', info: 'Not equal to' },
  { label: 'crosses-above', type: 'operator', info: 'Crosses above' },
  { label: 'crosses-below', type: 'operator', info: 'Crosses below' },
];

const logicalOps: Completion[] = [
  { label: 'and', type: 'keyword', info: 'Logical AND' },
  { label: 'or', type: 'keyword', info: 'Logical OR' },
  { label: 'not', type: 'keyword', info: 'Logical NOT' },
];

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
  // Check if we're inside :select (top|bottom N)
  else if (/:\s*select\s+\(\s*\S*$/.test(textBefore)) {
    options = filterMethods;
  }
  // Check if we're after :by
  else if (/:\s*by\s+$/.test(textBefore) || /:\s*by\s+\S*$/.test(textBefore)) {
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
  else if (/\(\s*(>=|<=|!=|>|<|=|crosses-above|crosses-below)\s*$/.test(textBefore)) {
    options = [...indicators, ...metrics];
  }
  // Check if we're after an opening paren
  else if (/\(\s*$/.test(textBefore) || /\(\s*\S*$/.test(textBefore)) {
    options = [...blockTypes, ...indicators, ...metrics, ...operators, ...logicalOps];
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
      ...metrics,
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

/** Exposed so the conformance suite can check every label against the DSL vocabulary. */
export const completionSets = {
  blockTypes,
  parameters,
  weightMethods,
  filterMethods,
  sortCriteria,
  rebalanceFrequencies,
  indicators,
  metrics,
  operators,
  logicalOps,
} as const;

export { getCompletions };
