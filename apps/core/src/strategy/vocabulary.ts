// The DSL vocabulary the Python parser accepts (libs/dsl/llamatrade_dsl/ast.py is the
// authority). tests/conformance/vocabulary.json is generated from those constants and pins the
// tables below; the keyword tables mirror libs/dsl/llamatrade_dsl/parser.py, which does not
// export them. Every table is sorted so it can be compared to the generated JSON directly.

export const DSL_REBALANCE_FREQUENCIES = [
  'annually',
  'daily',
  'monthly',
  'quarterly',
  'weekly',
] as const;

// market-cap parses but the validator rejects it (needs fundamentals the engine lacks).
export const DSL_WEIGHT_METHODS = [
  'equal',
  'inverse-volatility',
  'market-cap',
  'min-variance',
  'momentum',
  'risk-parity',
  'specified',
] as const;

export const DSL_FILTER_CRITERIA = ['momentum', 'volatility', 'volume'] as const;

export const DSL_SELECT_DIRECTIONS = ['bottom', 'top'] as const;

export const DSL_COMPARISON_OPS = ['!=', '<', '<=', '=', '>', '>='] as const;

export const DSL_CROSSOVER_OPS = ['crosses-above', 'crosses-below'] as const;

export const DSL_LOGICAL_OPS = ['and', 'not', 'or'] as const;

export const DSL_INDICATORS = [
  'adx',
  'atr',
  'bbands',
  'cci',
  'donchian',
  'ema',
  'keltner',
  'macd',
  'mfi',
  'momentum',
  'obv',
  'rsi',
  'sma',
  'stddev',
  'stoch',
  'vwap',
  'williams-r',
] as const;

export const DSL_METRICS = ['drawdown', 'return', 'volatility'] as const;

export const DSL_PRICE_FIELDS = ['close', 'high', 'low', 'open', 'volume'] as const;

// Block heads accepted by Parser._parse_block, plus `else`, which only appears
// inside an if.
export const DSL_BLOCK_TYPES = [
  'asset',
  'else',
  'filter',
  'group',
  'if',
  'strategy',
  'weight',
] as const;

/** Keyword arguments each form accepts, without the leading colon. */
export const DSL_KEYWORDS_BY_FORM = {
  strategy: ['benchmark', 'description', 'rebalance'],
  weight: ['lookback', 'method', 'top'],
  filter: ['by', 'lookback', 'select'],
  asset: ['weight'],
  group: ['weight'],
  price: DSL_PRICE_FIELDS,
} as const satisfies Record<string, readonly string[]>;

/** Every keyword argument the parser accepts anywhere, with the leading colon. */
export const DSL_KEYWORDS: readonly string[] = Array.from(
  new Set(Object.values(DSL_KEYWORDS_BY_FORM).flatMap((names) => names.map((n) => `:${n}`)))
).sort();

export type DslIndicator = (typeof DSL_INDICATORS)[number];
export type DslMetric = (typeof DSL_METRICS)[number];
export type DslWeightMethod = (typeof DSL_WEIGHT_METHODS)[number];

export const DSL_INDICATOR_SET: ReadonlySet<string> = new Set(DSL_INDICATORS);
export const DSL_METRIC_SET: ReadonlySet<string> = new Set(DSL_METRICS);
export const DSL_BLOCK_TYPE_SET: ReadonlySet<string> = new Set(DSL_BLOCK_TYPES);
export const DSL_WEIGHT_METHOD_SET: ReadonlySet<string> = new Set(DSL_WEIGHT_METHODS);
export const DSL_OPERATOR_SET: ReadonlySet<string> = new Set([
  ...DSL_COMPARISON_OPS,
  ...DSL_CROSSOVER_OPS,
]);
export const DSL_LOGICAL_SET: ReadonlySet<string> = new Set(DSL_LOGICAL_OPS);
export const DSL_KEYWORD_SET: ReadonlySet<string> = new Set(DSL_KEYWORDS);
