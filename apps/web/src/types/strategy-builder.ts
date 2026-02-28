// Strategy Builder Type Definitions

export type BlockId = string;
export type BlockType = 'root' | 'asset' | 'group' | 'weight' | 'if' | 'else' | 'filter';
export type WeightMethod =
  | 'specified'
  | 'equal'
  | 'inverse_volatility'
  | 'market_cap'
  | 'momentum'
  | 'min_variance';

// Base block interface
interface BaseBlock {
  id: BlockId;
  parentId: BlockId | null;
}

// Root block - strategy container
export interface RootBlock extends BaseBlock {
  type: 'root';
  parentId: null;
  name: string;
  childIds: BlockId[];
}

// Asset block - individual stock/ETF
export interface AssetBlock extends BaseBlock {
  type: 'asset';
  parentId: BlockId;
  symbol: string;
  exchange: string;
  displayName: string;
}

// Group block - named container for organizing assets
export interface GroupBlock extends BaseBlock {
  type: 'group';
  parentId: BlockId;
  name: string;
  childIds: BlockId[];
}

// Weight block - allocation method
export interface WeightBlock extends BaseBlock {
  type: 'weight';
  parentId: BlockId;
  method: WeightMethod;
  allocations: Record<BlockId, number>; // for 'specified' method
  lookbackDays?: number; // for momentum, inverse_volatility, min_variance
  childIds: BlockId[];
}

// ============================================
// Condition Block Types (IF/ELSE)
// ============================================

// Indicator reference for conditions
export type IndicatorName =
  | 'sma'
  | 'ema'
  | 'rsi'
  | 'macd_line'
  | 'macd_signal'
  | 'bb_upper'
  | 'bb_middle'
  | 'bb_lower'
  | 'atr'
  | 'adx'
  | 'stochastic_k'
  | 'stochastic_d'
  | 'cci'
  | 'williams_r'
  | 'obv'
  | 'mfi'
  | 'vwap';

export type PriceField = 'current' | 'open' | 'high' | 'low' | 'close' | 'volume';
export type IndicatorSource = 'price' | 'close' | 'high' | 'low' | 'open' | 'volume';
export type Comparator = 'gt' | 'lt' | 'gte' | 'lte' | 'cross_above' | 'cross_below';

// Operand types for conditions
export interface IndicatorRef {
  type: 'indicator';
  indicator: IndicatorName;
  period?: number;
  symbol: string;
  source?: IndicatorSource;
  // MACD-specific params
  fastPeriod?: number;
  slowPeriod?: number;
  signalPeriod?: number;
  // Bollinger-specific
  stdDev?: number;
}

export interface PriceRef {
  type: 'price';
  symbol: string;
  field: PriceField;
}

export interface NumberValue {
  type: 'number';
  value: number;
  isPercent?: boolean;
}

export type ConditionOperand = IndicatorRef | PriceRef | NumberValue;

// Structured condition expression
export interface ConditionExpression {
  left: ConditionOperand;
  comparator: Comparator;
  right: ConditionOperand;
}

// If block - conditional allocation
export interface IfBlock extends BaseBlock {
  type: 'if';
  parentId: BlockId;
  condition: ConditionExpression;
  conditionText: string; // Human-readable: "current price of SPY is greater than..."
  childIds: BlockId[];
}

// Else block - alternative allocation (sibling of IfBlock)
export interface ElseBlock extends BaseBlock {
  type: 'else';
  parentId: BlockId;
  ifBlockId: BlockId; // Reference to the associated IfBlock
  childIds: BlockId[];
}

// ============================================
// Filter Block Types
// ============================================

export type FilterSelection = 'top' | 'bottom';
export type FilterUniverse = 'sp500' | 'nasdaq100' | 'russell2000' | 'dow30' | 'custom';
export type FilterSortBy =
  | 'momentum'
  | 'market_cap'
  | 'volume'
  | 'volatility'
  | 'rsi'
  | 'dividend_yield';
export type FilterPeriod = '1m' | '3m' | '6m' | '12m';

export interface FilterConfig {
  selection: FilterSelection;
  count: number;
  universe: FilterUniverse;
  customSymbols?: string[]; // For custom universe
  sortBy: FilterSortBy;
  period: FilterPeriod;
}

// Filter block - dynamic asset selection
export interface FilterBlock extends BaseBlock {
  type: 'filter';
  parentId: BlockId;
  config: FilterConfig;
  displayText: string; // "Top 10 by Momentum (12 months)"
  childIds: BlockId[]; // Populated dynamically based on filter results
}

// Union type for all blocks
export type Block = RootBlock | AssetBlock | GroupBlock | WeightBlock | IfBlock | ElseBlock | FilterBlock;

// Type guards
export function isRootBlock(block: Block): block is RootBlock {
  return block.type === 'root';
}

export function isAssetBlock(block: Block): block is AssetBlock {
  return block.type === 'asset';
}

export function isGroupBlock(block: Block): block is GroupBlock {
  return block.type === 'group';
}

export function isWeightBlock(block: Block): block is WeightBlock {
  return block.type === 'weight';
}

export function isIfBlock(block: Block): block is IfBlock {
  return block.type === 'if';
}

export function isElseBlock(block: Block): block is ElseBlock {
  return block.type === 'else';
}

export function isFilterBlock(block: Block): block is FilterBlock {
  return block.type === 'filter';
}

// Blocks that can have children
export type ParentBlock = RootBlock | GroupBlock | WeightBlock | IfBlock | ElseBlock | FilterBlock;

export function hasChildren(block: Block): block is ParentBlock {
  return (
    block.type === 'root' ||
    block.type === 'group' ||
    block.type === 'weight' ||
    block.type === 'if' ||
    block.type === 'else' ||
    block.type === 'filter'
  );
}

// Strategy tree structure
export interface StrategyTree {
  rootId: BlockId;
  blocks: Record<BlockId, Block>;
}

// UI state
export interface StrategyBuilderUI {
  selectedBlockId: BlockId | null;
  expandedBlocks: Set<BlockId>;
  editingBlockId: BlockId | null;
}

// Weight method metadata for UI
export interface WeightMethodInfo {
  method: WeightMethod;
  label: string;
  description: string;
  hasLookback: boolean;
  color: {
    bg: string;
    text: string;
    border: string;
  };
}

export const WEIGHT_METHODS: WeightMethodInfo[] = [
  {
    method: 'specified',
    label: 'Specified',
    description: 'Fixed percentage allocations',
    hasLookback: false,
    color: { bg: 'bg-green-100 dark:bg-green-900', text: 'text-green-700 dark:text-green-300', border: 'border-green-200 dark:border-green-800' },
  },
  {
    method: 'equal',
    label: 'Equal Weight',
    description: 'Split evenly across children',
    hasLookback: false,
    color: { bg: 'bg-green-100 dark:bg-green-900', text: 'text-green-700 dark:text-green-300', border: 'border-green-200 dark:border-green-800' },
  },
  {
    method: 'inverse_volatility',
    label: 'Inverse Volatility',
    description: 'Risk parity weighting',
    hasLookback: true,
    color: { bg: 'bg-green-100 dark:bg-green-900', text: 'text-green-700 dark:text-green-300', border: 'border-green-200 dark:border-green-800' },
  },
  {
    method: 'market_cap',
    label: 'Market Cap',
    description: 'Cap-weighted allocation',
    hasLookback: false,
    color: { bg: 'bg-green-100 dark:bg-green-900', text: 'text-green-700 dark:text-green-300', border: 'border-green-200 dark:border-green-800' },
  },
  {
    method: 'momentum',
    label: 'Momentum',
    description: 'Momentum-weighted allocation',
    hasLookback: true,
    color: { bg: 'bg-green-100 dark:bg-green-900', text: 'text-green-700 dark:text-green-300', border: 'border-green-200 dark:border-green-800' },
  },
  {
    method: 'min_variance',
    label: 'Min Variance',
    description: 'Minimum variance optimization',
    hasLookback: true,
    color: { bg: 'bg-green-100 dark:bg-green-900', text: 'text-green-700 dark:text-green-300', border: 'border-green-200 dark:border-green-800' },
  },
];

export function getWeightMethodInfo(method: WeightMethod): WeightMethodInfo {
  const info = WEIGHT_METHODS.find((m) => m.method === method);
  if (!info) {
    throw new Error(`Unknown weight method: ${method}`);
  }
  return info;
}

// ============================================
// Indicator Metadata for UI
// ============================================

export interface IndicatorInfo {
  name: IndicatorName;
  label: string;
  shortLabel: string; // For compact display
  hasPeriod: boolean;
  defaultPeriod?: number;
  category: 'trend' | 'momentum' | 'volatility' | 'volume';
}

export const INDICATORS: IndicatorInfo[] = [
  { name: 'sma', label: 'Moving Average (SMA)', shortLabel: 'SMA', hasPeriod: true, defaultPeriod: 20, category: 'trend' },
  { name: 'ema', label: 'Exponential Moving Average', shortLabel: 'EMA', hasPeriod: true, defaultPeriod: 20, category: 'trend' },
  { name: 'rsi', label: 'Relative Strength Index', shortLabel: 'RSI', hasPeriod: true, defaultPeriod: 14, category: 'momentum' },
  { name: 'macd_line', label: 'MACD Line', shortLabel: 'MACD', hasPeriod: false, category: 'momentum' },
  { name: 'macd_signal', label: 'MACD Signal', shortLabel: 'Signal', hasPeriod: false, category: 'momentum' },
  { name: 'bb_upper', label: 'Bollinger Band (Upper)', shortLabel: 'BB Upper', hasPeriod: true, defaultPeriod: 20, category: 'volatility' },
  { name: 'bb_middle', label: 'Bollinger Band (Middle)', shortLabel: 'BB Mid', hasPeriod: true, defaultPeriod: 20, category: 'volatility' },
  { name: 'bb_lower', label: 'Bollinger Band (Lower)', shortLabel: 'BB Lower', hasPeriod: true, defaultPeriod: 20, category: 'volatility' },
  { name: 'atr', label: 'Average True Range', shortLabel: 'ATR', hasPeriod: true, defaultPeriod: 14, category: 'volatility' },
  { name: 'adx', label: 'Average Directional Index', shortLabel: 'ADX', hasPeriod: true, defaultPeriod: 14, category: 'trend' },
  { name: 'stochastic_k', label: 'Stochastic %K', shortLabel: '%K', hasPeriod: true, defaultPeriod: 14, category: 'momentum' },
  { name: 'stochastic_d', label: 'Stochastic %D', shortLabel: '%D', hasPeriod: true, defaultPeriod: 14, category: 'momentum' },
  { name: 'cci', label: 'Commodity Channel Index', shortLabel: 'CCI', hasPeriod: true, defaultPeriod: 20, category: 'momentum' },
  { name: 'williams_r', label: 'Williams %R', shortLabel: '%R', hasPeriod: true, defaultPeriod: 14, category: 'momentum' },
  { name: 'obv', label: 'On-Balance Volume', shortLabel: 'OBV', hasPeriod: false, category: 'volume' },
  { name: 'mfi', label: 'Money Flow Index', shortLabel: 'MFI', hasPeriod: true, defaultPeriod: 14, category: 'volume' },
  { name: 'vwap', label: 'VWAP', shortLabel: 'VWAP', hasPeriod: false, category: 'volume' },
];

export function getIndicatorInfo(name: IndicatorName): IndicatorInfo {
  const info = INDICATORS.find((i) => i.name === name);
  if (!info) {
    throw new Error(`Unknown indicator: ${name}`);
  }
  return info;
}

// ============================================
// Comparator Metadata for UI
// ============================================

export interface ComparatorInfo {
  value: Comparator;
  label: string;
  verboseLabel: string; // "is greater than"
}

export const COMPARATORS: ComparatorInfo[] = [
  { value: 'gt', label: '>', verboseLabel: 'is greater than' },
  { value: 'lt', label: '<', verboseLabel: 'is less than' },
  { value: 'gte', label: '≥', verboseLabel: 'is greater than or equal to' },
  { value: 'lte', label: '≤', verboseLabel: 'is less than or equal to' },
  { value: 'cross_above', label: '↗', verboseLabel: 'crosses above' },
  { value: 'cross_below', label: '↘', verboseLabel: 'crosses below' },
];

export function getComparatorInfo(value: Comparator): ComparatorInfo {
  const info = COMPARATORS.find((c) => c.value === value);
  if (!info) {
    throw new Error(`Unknown comparator: ${value}`);
  }
  return info;
}

// ============================================
// Filter Metadata for UI
// ============================================

export interface FilterUniverseInfo {
  value: FilterUniverse;
  label: string;
  description: string;
}

export const FILTER_UNIVERSES: FilterUniverseInfo[] = [
  { value: 'sp500', label: 'S&P 500', description: 'Large-cap US stocks' },
  { value: 'nasdaq100', label: 'NASDAQ 100', description: 'Tech-heavy large caps' },
  { value: 'russell2000', label: 'Russell 2000', description: 'Small-cap US stocks' },
  { value: 'dow30', label: 'Dow Jones 30', description: 'Blue-chip industrials' },
  { value: 'custom', label: 'Custom', description: 'Your own symbol list' },
];

export interface FilterSortByInfo {
  value: FilterSortBy;
  label: string;
  description: string;
}

export const FILTER_SORT_OPTIONS: FilterSortByInfo[] = [
  { value: 'momentum', label: 'Momentum', description: 'Price change over period' },
  { value: 'market_cap', label: 'Market Cap', description: 'Company size' },
  { value: 'volume', label: 'Volume', description: 'Trading activity' },
  { value: 'volatility', label: 'Volatility', description: 'Price variability' },
  { value: 'rsi', label: 'RSI', description: 'Relative strength' },
  { value: 'dividend_yield', label: 'Dividend Yield', description: 'Income potential' },
];

export interface FilterPeriodInfo {
  value: FilterPeriod;
  label: string;
}

export const FILTER_PERIODS: FilterPeriodInfo[] = [
  { value: '1m', label: '1 month' },
  { value: '3m', label: '3 months' },
  { value: '6m', label: '6 months' },
  { value: '12m', label: '12 months' },
];

// Node position for connector rendering
export interface NodePosition {
  blockId: BlockId;
  x: number;
  y: number;
  width: number;
  height: number;
}

// Connector path data
export interface ConnectorPath {
  parentId: BlockId;
  childId: BlockId;
  path: string;
}
