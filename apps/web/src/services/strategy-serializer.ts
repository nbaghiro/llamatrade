// Strategy Serializer
// Converts between visual block tree and S-expression DSL format
// Also provides tokenization with position tracking for editor integration

import type { StrategyConfigJSON } from '../types/strategy';
import type {
  Block,
  BlockId,
  StrategyTree,
  RootBlock,
  AssetBlock,
  WeightBlock,
  IfBlock,
  ElseBlock,
  FilterBlock,
  FilterConfig,
  ConditionExpression,
  ConditionOperand,
  Comparator,
} from '../types/strategy-builder';
import {
  hasChildren,
  isIfBlock,
  isElseBlock,
  isAssetBlock,
  isWeightBlock,
  isGroupBlock,
  isFilterBlock,
} from '../types/strategy-builder';

// ============================================
// Strategy Metadata for Serialization
// ============================================

export interface StrategyMetadata {
  name: string;
  description?: string;
  timeframe: string;
  stopLossPct?: number;
  takeProfitPct?: number;
  trailingStopPct?: number;
  positionSizePct?: number;
}

/**
 * Result of parsing a DSL string, includes both tree and metadata
 */
export interface ParsedDSL {
  tree: StrategyTree;
  metadata: Partial<StrategyMetadata>;
}

// ============================================
// Validation Types
// ============================================

export interface ValidationError {
  blockId?: BlockId;
  field?: string;
  message: string;
  severity: 'error' | 'warning';
}

export interface ValidationResult {
  valid: boolean;
  errors: ValidationError[];
  warnings: ValidationError[];
}

// ============================================
// Token Types for Editor Integration
// ============================================

export type TokenType =
  | 'keyword'      // strategy, weight, asset, group, if, else, filter
  | 'parameter'    // :method, :weight, :rebalance, :benchmark, :lookback
  | 'method'       // specified, equal, momentum, inverse-volatility
  | 'indicator'    // sma, ema, rsi, macd, bbands
  | 'operator'     // >, <, >=, <=, cross-above, cross-below
  | 'logical'      // and, or, not
  | 'string'       // "Strategy Name"
  | 'number'       // 50, 0.05, 100
  | 'comment'      // ; comment
  | 'symbol'       // SPY, VTI, BND (uppercase identifiers)
  | 'bracket'      // ( ) [ ] { }
  | 'unknown';     // Unrecognized tokens

export interface TokenWithPosition {
  type: TokenType;
  value: string;
  start: number;    // Character offset from start of input
  end: number;      // Character offset (exclusive)
  line: number;     // 1-indexed line number
  column: number;   // 1-indexed column number
}

export interface ParseError {
  message: string;
  line: number;
  column: number;
  start: number;
  end: number;
}

// ============================================
// Case Conversion Helpers
// ============================================

// DSL keywords that should use kebab-case
const KEBAB_CASE_KEYWORDS = new Set([
  'inverse-volatility',
  'min-variance',
  'risk-parity',
  'cross-above',
  'cross-below',
  'lookback-days',
  'sort-by',
  'custom-symbols',
  'stop-loss-pct',
  'take-profit-pct',
  'trailing-stop-pct',
  'position-size-pct',
  'position-size',
  'macd-line',
  'macd-signal',
  'bb-upper',
  'bb-middle',
  'bb-lower',
  'williams-r',
]);

/**
 * Convert snake_case to kebab-case for DSL serialization
 */
export function toKebabCase(str: string): string {
  return str.replace(/_/g, '-');
}

/**
 * Convert kebab-case to snake_case for internal representation
 */
export function fromKebabCase(str: string): string {
  return str.replace(/-/g, '_');
}

/**
 * Check if a string is a DSL keyword that uses kebab-case
 */
export function isKebabCaseKeyword(str: string): boolean {
  return KEBAB_CASE_KEYWORDS.has(str);
}

// ============================================
// Verbose Text Generation
// ============================================

/**
 * Format an operand (left or right side of condition) to verbose text
 */
function operandToText(operand: ConditionOperand): string {
  if (operand.type === 'price') {
    const field = operand.field === 'current' ? 'current price' : operand.field;
    return `${field} of ${operand.symbol}`;
  }

  if (operand.type === 'number') {
    if (operand.isPercent) {
      return `${operand.value}%`;
    }
    return String(operand.value);
  }

  // Indicator
  const ind = operand;
  const period = ind.period ? `${ind.period}d ` : '';

  switch (ind.indicator) {
    case 'sma':
      return `the ${period}moving average of ${ind.source || 'price'} of ${ind.symbol}`;
    case 'ema':
      return `the ${period}exponential moving average of ${ind.source || 'price'} of ${ind.symbol}`;
    case 'rsi':
      return `${period}relative strength index of ${ind.symbol}`;
    case 'macd_line':
      return `MACD line of ${ind.symbol}`;
    case 'macd_signal':
      return `MACD signal line of ${ind.symbol}`;
    case 'bb_upper':
      return `the upper Bollinger Band of ${ind.symbol}`;
    case 'bb_middle':
      return `the middle Bollinger Band of ${ind.symbol}`;
    case 'bb_lower':
      return `the lower Bollinger Band of ${ind.symbol}`;
    case 'atr':
      return `${period}ATR of ${ind.symbol}`;
    case 'adx':
      return `${period}ADX of ${ind.symbol}`;
    case 'stochastic_k':
      return `stochastic %K of ${ind.symbol}`;
    case 'stochastic_d':
      return `stochastic %D of ${ind.symbol}`;
    case 'cci':
      return `${period}CCI of ${ind.symbol}`;
    case 'williams_r':
      return `${period}Williams %R of ${ind.symbol}`;
    case 'obv':
      return `OBV of ${ind.symbol}`;
    case 'mfi':
      return `${period}MFI of ${ind.symbol}`;
    case 'vwap':
      return `VWAP of ${ind.symbol}`;
    default:
      return `${ind.indicator} of ${ind.symbol}`;
  }
}

/**
 * Format comparator to verbose text
 */
function comparatorToText(comp: Comparator): string {
  switch (comp) {
    case 'gt':
      return 'is greater than';
    case 'lt':
      return 'is less than';
    case 'gte':
      return 'is greater than or equal to';
    case 'lte':
      return 'is less than or equal to';
    case 'cross_above':
      return 'crosses above';
    case 'cross_below':
      return 'crosses below';
  }
}

/**
 * Convert a condition expression to verbose human-readable text
 */
export function conditionToText(condition: ConditionExpression): string {
  const left = operandToText(condition.left);
  const comp = comparatorToText(condition.comparator);
  const right = operandToText(condition.right);
  return `${left} ${comp} ${right}`;
}

// ============================================
// DSL Serialization (Block Tree → S-expression)
// ============================================

/**
 * Serialize an operand to S-expression
 */
function operandToDSL(operand: ConditionOperand): string {
  if (operand.type === 'price') {
    // Backend DSL expects (price SYMBOL [:field]) format
    // Field is optional keyword - only include non-default fields
    const field = operand.field === 'current' ? 'close' : operand.field;
    if (field === 'close') {
      // close is default, omit it
      return `(price ${operand.symbol})`;
    }
    // Other fields need :keyword syntax
    return `(price ${operand.symbol} :${field})`;
  }

  if (operand.type === 'number') {
    return String(operand.value);
  }

  // Indicator
  const ind = operand;
  const symbol = ind.symbol;

  // Multi-output indicators use :output syntax, e.g., (macd SPY 12 26 9 :signal)
  switch (ind.indicator) {
    case 'sma':
      return `(sma ${symbol} ${ind.period || 20})`;
    case 'ema':
      return `(ema ${symbol} ${ind.period || 20})`;
    case 'rsi':
      return `(rsi ${symbol} ${ind.period || 14})`;
    case 'macd_line':
      return `(macd ${symbol} ${ind.fastPeriod || 12} ${ind.slowPeriod || 26} ${ind.signalPeriod || 9} :line)`;
    case 'macd_signal':
      return `(macd ${symbol} ${ind.fastPeriod || 12} ${ind.slowPeriod || 26} ${ind.signalPeriod || 9} :signal)`;
    case 'bb_upper':
      return `(bbands ${symbol} ${ind.period || 20} ${ind.stdDev || 2.0} :upper)`;
    case 'bb_middle':
      return `(bbands ${symbol} ${ind.period || 20} ${ind.stdDev || 2.0} :middle)`;
    case 'bb_lower':
      return `(bbands ${symbol} ${ind.period || 20} ${ind.stdDev || 2.0} :lower)`;
    case 'atr':
      return `(atr ${symbol} ${ind.period || 14})`;
    case 'adx':
      return `(adx ${symbol} ${ind.period || 14})`;
    case 'stochastic_k':
      return `(stoch ${symbol} ${ind.period || 14} 3 3 :k)`;
    case 'stochastic_d':
      return `(stoch ${symbol} ${ind.period || 14} 3 3 :d)`;
    case 'cci':
      return `(cci ${symbol} ${ind.period || 20})`;
    case 'williams_r':
      return `(williams-r ${symbol} ${ind.period || 14})`;
    case 'obv':
      return `(obv ${symbol})`;
    case 'mfi':
      return `(mfi ${symbol} ${ind.period || 14})`;
    case 'vwap':
      return `(vwap ${symbol})`;
    default:
      return `(${ind.indicator} ${symbol})`;
  }
}

/**
 * Serialize comparator to DSL operator
 */
function comparatorToDSL(comp: Comparator): string {
  switch (comp) {
    case 'gt':
      return '>';
    case 'lt':
      return '<';
    case 'gte':
      return '>=';
    case 'lte':
      return '<=';
    case 'cross_above':
      return 'cross-above';
    case 'cross_below':
      return 'cross-below';
  }
}

/**
 * Serialize a condition expression to S-expression
 */
function conditionToDSL(condition: ConditionExpression): string {
  const op = comparatorToDSL(condition.comparator);
  const left = operandToDSL(condition.left);
  const right = operandToDSL(condition.right);

  if (op === 'cross-above' || op === 'cross-below') {
    return `(${op} ${left} ${right})`;
  }

  return `(${op} ${left} ${right})`;
}

/**
 * Extract all symbols from the tree
 */
function extractSymbols(tree: StrategyTree): string[] {
  const symbols = new Set<string>();

  for (const block of Object.values(tree.blocks)) {
    if (isAssetBlock(block)) {
      symbols.add(block.symbol);
    }
    // Also extract from conditions
    if (isIfBlock(block)) {
      extractSymbolsFromCondition(block.condition, symbols);
    }
  }

  return Array.from(symbols);
}

function extractSymbolsFromCondition(
  condition: ConditionExpression,
  symbols: Set<string>
): void {
  if (condition.left.type === 'price') {
    symbols.add(condition.left.symbol);
  } else if (condition.left.type === 'indicator') {
    symbols.add(condition.left.symbol);
  }

  if (condition.right.type === 'price') {
    symbols.add(condition.right.symbol);
  } else if (condition.right.type === 'indicator') {
    symbols.add(condition.right.symbol);
  }
}

/**
 * Serialize weight allocation to DSL
 * Generates: (weight :method <method> [:lookback N] (asset ...) ...)
 *
 * IMPORTANT: Backend DSL requires that when method is "specified", all direct
 * children must be Assets with :weight. Groups cannot be direct children of
 * a specified weight block. If we have groups, we must use a different method.
 */
function serializeWeightBlock(
  block: WeightBlock,
  tree: StrategyTree,
  indent: string
): string {
  const children = block.childIds.map((id) => tree.blocks[id]);
  const lines: string[] = [];

  // Determine method - backend DSL doesn't support groups under "specified"
  // If we have non-asset children (groups, nested weights), use "equal" instead
  let method = block.method;
  if (method === 'specified') {
    const hasNonAssetChildren = children.some((child) => !isAssetBlock(child));
    if (hasNonAssetChildren) {
      // Can't use specified with groups - fallback to equal
      method = 'equal';
    }
  }

  // Convert method to DSL format (snake_case to kebab-case for multi-word methods)
  const methodStr = method.replace(/_/g, '-');
  lines.push(`${indent}(weight :method ${methodStr}`);

  if (block.lookbackDays) {
    lines.push(`${indent}  :lookback ${block.lookbackDays}`);
  }

  for (const child of children) {
    if (isAssetBlock(child)) {
      const allocation = block.allocations[child.id] ?? 0;
      // Only output :weight when using specified method AND we have a valid allocation
      if (method === 'specified' && allocation > 0) {
        lines.push(`${indent}  (asset ${child.symbol} :weight ${allocation})`);
      } else {
        lines.push(`${indent}  (asset ${child.symbol})`);
      }
    } else if (isGroupBlock(child)) {
      lines.push(`${indent}  (group "${child.name}"`);
      lines.push(serializeChildren(child.childIds, tree, indent + '    '));
      lines.push(`${indent}  )`);
    } else if (isWeightBlock(child)) {
      lines.push(serializeWeightBlock(child, tree, indent + '  '));
    } else if (isIfBlock(child)) {
      lines.push(serializeIfBlock(child, tree, indent + '  '));
    } else if (isFilterBlock(child)) {
      lines.push(serializeFilterBlock(child, indent + '  '));
    }
  }

  lines.push(`${indent})`);
  return lines.join('\n');
}

/**
 * Serialize IF/ELSE block to DSL
 * Backend expects: (if CONDITION THEN_BLOCK [(else ELSE_BLOCK)])
 * No (then ...) wrapper - just the block directly after condition
 */
function serializeIfBlock(block: IfBlock, tree: StrategyTree, indent: string): string {
  const lines: string[] = [];

  lines.push(`${indent}(if ${conditionToDSL(block.condition)}`);

  // Serialize then block - backend expects a single block, not wrapped in (then ...)
  // If there are multiple children, wrap them in a weight block
  if (block.childIds.length === 0) {
    // No children - add a placeholder weight block
    lines.push(`${indent}  (weight :method equal)`);
  } else if (block.childIds.length === 1) {
    // Single child - serialize directly
    const child = tree.blocks[block.childIds[0]];
    if (child) {
      lines.push(serializeSingleBlock(child, tree, indent + '  '));
    }
  } else {
    // Multiple children - wrap in a weight block
    lines.push(`${indent}  (weight :method equal`);
    lines.push(serializeChildren(block.childIds, tree, indent + '    '));
    lines.push(`${indent}  )`);
  }

  // Find associated else block by ifBlockId (not by position, as order may vary)
  const parent = tree.blocks[block.parentId];
  if (parent && hasChildren(parent)) {
    const parentBlock = parent as { childIds: BlockId[] };
    // Search all siblings for an else block that references this if block
    for (const siblingId of parentBlock.childIds) {
      const siblingBlock = tree.blocks[siblingId];
      if (isElseBlock(siblingBlock) && siblingBlock.ifBlockId === block.id) {
        // Serialize else block - also expects a single block
        if (siblingBlock.childIds.length === 0) {
          lines.push(`${indent}  (else (weight :method equal))`);
        } else if (siblingBlock.childIds.length === 1) {
          const elseChild = tree.blocks[siblingBlock.childIds[0]];
          if (elseChild) {
            lines.push(`${indent}  (else`);
            lines.push(serializeSingleBlock(elseChild, tree, indent + '    '));
            lines.push(`${indent}  )`);
          }
        } else {
          lines.push(`${indent}  (else`);
          lines.push(`${indent}    (weight :method equal`);
          lines.push(serializeChildren(siblingBlock.childIds, tree, indent + '      '));
          lines.push(`${indent}    )`);
          lines.push(`${indent}  )`);
        }
        break; // Found the else block, stop searching
      }
    }
  }

  lines.push(`${indent})`);
  return lines.join('\n');
}

/**
 * Serialize a single block (helper for if/else which expects single blocks)
 */
function serializeSingleBlock(block: Block, tree: StrategyTree, indent: string): string {
  if (isAssetBlock(block)) {
    return `${indent}(asset ${block.symbol})`;
  } else if (isGroupBlock(block)) {
    const lines: string[] = [];
    lines.push(`${indent}(group "${block.name}"`);
    lines.push(serializeChildren(block.childIds, tree, indent + '  '));
    lines.push(`${indent})`);
    return lines.join('\n');
  } else if (isWeightBlock(block)) {
    return serializeWeightBlock(block, tree, indent);
  } else if (isIfBlock(block)) {
    return serializeIfBlock(block, tree, indent);
  } else if (isFilterBlock(block)) {
    return serializeFilterBlock(block, indent);
  }
  return '';
}

/**
 * Serialize filter block to DSL
 * Generates: (filter :by <criteria> :select (top/bottom N) [:lookback N] children...)
 */
function serializeFilterBlock(block: FilterBlock, indent: string): string {
  const config = block.config;
  const lines: string[] = [];

  // Map sortBy to filter criteria (e.g., momentum -> returns)
  const criteriaMap: Record<string, string> = {
    momentum: 'returns',
    volatility: 'volatility',
    volume: 'volume',
    market_cap: 'market_cap',
    rsi: 'rsi',
    dividend_yield: 'dividend_yield',
  };
  const criteria = criteriaMap[config.sortBy] || 'returns';

  // Map period to lookback days
  const periodMap: Record<string, number> = {
    '1m': 21,
    '3m': 63,
    '6m': 126,
    '12m': 252,
  };
  const lookback = periodMap[config.period] || 63;

  lines.push(`${indent}(filter :by ${criteria} :select (${config.selection} ${config.count}) :lookback ${lookback}`);

  // Add children if custom symbols provided
  if (config.customSymbols && config.customSymbols.length > 0) {
    for (const symbol of config.customSymbols) {
      lines.push(`${indent}  (asset ${symbol})`);
    }
  }

  lines.push(`${indent})`);
  return lines.join('\n');
}

/**
 * Serialize children of a container block
 * Generates allocation-based DSL format
 */
function serializeChildren(
  childIds: BlockId[],
  tree: StrategyTree,
  indent: string
): string {
  const lines: string[] = [];

  for (const childId of childIds) {
    const child = tree.blocks[childId];
    if (!child) continue;

    // Skip else blocks (handled with their if block)
    if (isElseBlock(child)) continue;

    if (isAssetBlock(child)) {
      lines.push(`${indent}(asset ${child.symbol})`);
    } else if (isGroupBlock(child)) {
      lines.push(`${indent}(group "${child.name}"`);
      lines.push(serializeChildren(child.childIds, tree, indent + '  '));
      lines.push(`${indent})`);
    } else if (isWeightBlock(child)) {
      lines.push(serializeWeightBlock(child, tree, indent));
    } else if (isIfBlock(child)) {
      lines.push(serializeIfBlock(child, tree, indent));
    } else if (isFilterBlock(child)) {
      lines.push(serializeFilterBlock(child, indent));
    }
  }

  return lines.join('\n');
}

/**
 * Map UI timeframe to DSL rebalance frequency
 */
function timeframeToRebalance(timeframe: string): string {
  const mapping: Record<string, string> = {
    '1D': 'daily',
    '1W': 'weekly',
    '1M': 'monthly',
    '3M': 'quarterly',
    '1Y': 'annually',
  };
  return mapping[timeframe] || 'daily';
}

/**
 * Map DSL rebalance frequency to UI timeframe
 */
function rebalanceToTimeframe(rebalance: string): string {
  const mapping: Record<string, string> = {
    'daily': '1D',
    'weekly': '1W',
    'monthly': '1M',
    'quarterly': '3M',
    'annually': '1Y',
  };
  return mapping[rebalance] || '1D';
}

/**
 * Convert block tree to S-expression DSL string
 * Generates allocation-based format compatible with backend parser
 */
export function toDSL(tree: StrategyTree, metadata: StrategyMetadata): string {
  const lines: string[] = [];
  const root = tree.blocks[tree.rootId];

  // Strategy header with name as first argument (required by backend parser)
  lines.push(`(strategy "${metadata.name}"`);

  // Optional rebalance frequency
  const rebalance = timeframeToRebalance(metadata.timeframe);
  lines.push(`  :rebalance ${rebalance}`);

  // Optional description
  if (metadata.description) {
    lines.push(`  :description "${metadata.description}"`);
  }

  // Serialize children of root block
  if (root && hasChildren(root)) {
    const rootBlock = root as { childIds: BlockId[] };
    const childContent = serializeChildren(rootBlock.childIds, tree, '  ');
    if (childContent.trim()) {
      lines.push(childContent);
    } else {
      // If no child blocks, create a minimal weight block with extracted symbols
      const symbols = extractSymbols(tree);
      if (symbols.length > 0) {
        lines.push('  (weight :method equal');
        for (const symbol of symbols) {
          lines.push(`    (asset ${symbol})`);
        }
        lines.push('  )');
      } else {
        // Default to SPY if no symbols found
        lines.push('  (weight :method equal');
        lines.push('    (asset SPY))');
      }
    }
  } else {
    // No root children - create minimal strategy
    lines.push('  (weight :method equal');
    lines.push('    (asset SPY))');
  }

  lines.push(')');

  return lines.join('\n');
}

// ============================================
// DSL Deserialization (config_json → Block Tree)
// ============================================

let blockIdCounter = 0;

function generateBlockId(): BlockId {
  return `block_${Date.now()}_${++blockIdCounter}`;
}

/**
 * Convert backend config_json to block tree
 */
export function fromDSL(
  configJson: StrategyConfigJSON,
  uiState?: Record<string, unknown>
): StrategyTree {
  // If UI state exists, use it directly (it's the saved block tree)
  if (uiState && uiState.rootId && uiState.blocks) {
    return uiState as unknown as StrategyTree;
  }

  // Otherwise, create a minimal tree from config
  blockIdCounter = 0;

  const rootId = generateBlockId();
  const blocks: Record<BlockId, Block> = {};

  const root: RootBlock = {
    id: rootId,
    type: 'root',
    parentId: null,
    name: configJson.name || 'Imported Strategy',
    childIds: [],
  };
  blocks[rootId] = root;

  // Create asset blocks from symbols
  for (const symbol of configJson.symbols || []) {
    const assetId = generateBlockId();
    const asset: AssetBlock = {
      id: assetId,
      type: 'asset',
      parentId: rootId,
      symbol,
      exchange: 'NASDAQ', // Default
      displayName: symbol,
    };
    blocks[assetId] = asset;
    root.childIds.push(assetId);
  }

  return { rootId, blocks };
}

// ============================================
// Validation
// ============================================

// Import comprehensive validation module
import {
  validateStrategy,
  type ValidationIssue as ComprehensiveIssue,
  type ValidationResult as ComprehensiveResult,
} from './validation';

/**
 * Validate a strategy tree before saving.
 *
 * Combines structural validation (root block, parent references) with
 * content validation from the validation module.
 */
export function validateTree(tree: StrategyTree): ValidationResult {
  const errors: ValidationError[] = [];
  const warnings: ValidationError[] = [];

  // Structural: verify root block exists
  const root = tree.blocks[tree.rootId];
  if (!root || root.type !== 'root') {
    errors.push({
      message: 'Strategy must have a root block',
      severity: 'error',
    });
    return { valid: false, errors, warnings };
  }

  // Structural: verify parent references are valid
  for (const block of Object.values(tree.blocks)) {
    if (block.parentId !== null && !tree.blocks[block.parentId]) {
      errors.push({
        blockId: block.id,
        message: `Block "${block.id}" has invalid parent reference`,
        severity: 'error',
      });
    }
  }

  // Content validation (block rules, required fields)
  const result = validateStrategy(tree);

  // Map comprehensive issues to ValidationError format
  const mapIssue = (issue: ComprehensiveIssue): ValidationError => ({
    blockId: issue.blockId,
    field: issue.field,
    message: issue.message,
    severity: issue.severity,
  });

  errors.push(...result.errors.map(mapIssue));
  warnings.push(...result.warnings.map(mapIssue));

  return {
    valid: errors.length === 0,
    errors,
    warnings,
  };
}

/**
 * Get comprehensive validation result with all issue details
 * Use this for UI components that need suggestions and rule IDs
 */
export function validateTreeComprehensive(tree: StrategyTree): ComprehensiveResult {
  return validateStrategy(tree);
}


// ============================================
// S-Expression DSL Parsing (config_sexpr → Block Tree)
// ============================================

interface ParsedCondition {
  comparator: Comparator;
  left: ConditionOperand;
  right: ConditionOperand;
}

// Token classification sets
const DSL_KEYWORDS = new Set([
  'strategy', 'weight', 'asset', 'group', 'if', 'else', 'filter',
  'then', 'allocation', 'universe',
]);

const DSL_METHODS = new Set([
  'specified', 'equal', 'momentum', 'inverse-volatility', 'min-variance',
  'risk-parity', 'inverse_volatility', 'min_variance', 'risk_parity',
  'top', 'bottom',
]);

const DSL_INDICATORS = new Set([
  'sma', 'ema', 'rsi', 'macd', 'macd-line', 'macd-signal',
  'bbands', 'bb-upper', 'bb-middle', 'bb-lower',
  'atr', 'adx', 'stochastic', 'cci', 'williams-r', 'obv', 'mfi', 'vwap', 'roc',
]);

const DSL_OPERATORS = new Set([
  '>', '<', '>=', '<=', '=', '!=',
  'cross-above', 'cross-below', 'crosses-above', 'crosses-below',
]);

const DSL_LOGICAL = new Set(['and', 'or', 'not']);

/**
 * Classify a token value into its semantic type
 */
function classifyToken(value: string): TokenType {
  // Brackets
  if ('()[]{}' .includes(value)) {
    return 'bracket';
  }

  // Comments
  if (value.startsWith(';')) {
    return 'comment';
  }

  // String literals
  if (value.startsWith('"') && value.endsWith('"')) {
    return 'string';
  }

  // Parameters (keywords starting with :)
  if (value.startsWith(':')) {
    return 'parameter';
  }

  // Numbers
  if (/^-?\d+(\.\d+)?$/.test(value)) {
    return 'number';
  }

  // Check against known token types
  const lower = value.toLowerCase();

  if (DSL_KEYWORDS.has(lower)) {
    return 'keyword';
  }

  if (DSL_METHODS.has(lower)) {
    return 'method';
  }

  if (DSL_INDICATORS.has(lower)) {
    return 'indicator';
  }

  if (DSL_OPERATORS.has(value)) {
    return 'operator';
  }

  if (DSL_LOGICAL.has(lower)) {
    return 'logical';
  }

  // Uppercase identifiers are likely symbols (tickers)
  if (/^[A-Z][A-Z0-9]*$/.test(value)) {
    return 'symbol';
  }

  // Price fields
  if (['close', 'open', 'high', 'low', 'volume', 'price'].includes(lower)) {
    return 'keyword';
  }

  return 'unknown';
}

/**
 * Simple tokenizer for S-expressions (returns values only, no positions)
 */
function tokenize(input: string): string[] {
  return tokenizeWithPositions(input).map((t) => t.value);
}

/**
 * Tokenizer with position tracking for editor integration
 * Returns tokens with line, column, and character offset information
 */
export function tokenizeWithPositions(input: string): TokenWithPosition[] {
  const tokens: TokenWithPosition[] = [];
  let current = 0;
  let line = 1;
  let lineStart = 0; // Character offset where current line starts

  function getColumn(): number {
    return current - lineStart + 1;
  }

  function createToken(type: TokenType, value: string, start: number, startLine: number, startColumn: number): TokenWithPosition {
    return {
      type,
      value,
      start,
      end: current,
      line: startLine,
      column: startColumn,
    };
  }

  while (current < input.length) {
    const char = input[current];

    // Track newlines for line/column info
    if (char === '\n') {
      current++;
      line++;
      lineStart = current;
      continue;
    }

    // Skip other whitespace
    if (/\s/.test(char)) {
      current++;
      continue;
    }

    // Comments (semicolon to end of line)
    if (char === ';') {
      const start = current;
      const startLine = line;
      const startColumn = getColumn();
      let value = '';
      while (current < input.length && input[current] !== '\n') {
        value += input[current];
        current++;
      }
      tokens.push(createToken('comment', value, start, startLine, startColumn));
      continue;
    }

    // Parentheses and brackets
    if ('()[]{}' .includes(char)) {
      const start = current;
      const startLine = line;
      const startColumn = getColumn();
      current++;
      tokens.push(createToken('bracket', char, start, startLine, startColumn));
      continue;
    }

    // String literal
    if (char === '"') {
      const start = current;
      const startLine = line;
      const startColumn = getColumn();
      let value = '"';
      current++; // Skip opening quote
      while (current < input.length && input[current] !== '"') {
        if (input[current] === '\n') {
          line++;
          lineStart = current + 1;
        }
        value += input[current];
        current++;
      }
      if (current < input.length) {
        value += '"';
        current++; // Skip closing quote
      }
      tokens.push(createToken('string', value, start, startLine, startColumn));
      continue;
    }

    // Keyword (starts with :)
    if (char === ':') {
      const start = current;
      const startLine = line;
      const startColumn = getColumn();
      let value = ':';
      current++;
      while (current < input.length && /[a-zA-Z0-9_-]/.test(input[current])) {
        value += input[current];
        current++;
      }
      tokens.push(createToken('parameter', value, start, startLine, startColumn));
      continue;
    }

    // Number, symbol, or identifier
    if (/[a-zA-Z0-9.<>=_-]/.test(char)) {
      const start = current;
      const startLine = line;
      const startColumn = getColumn();
      let value = '';
      while (current < input.length && /[a-zA-Z0-9.<>=_-]/.test(input[current])) {
        value += input[current];
        current++;
      }
      const type = classifyToken(value);
      tokens.push(createToken(type, value, start, startLine, startColumn));
      continue;
    }

    // Skip unknown characters
    current++;
  }

  return tokens;
}

/**
 * Parse a single S-expression and return the result
 */
function parseExpr(tokens: string[], pos: { index: number }): unknown {
  const token = tokens[pos.index];

  if (token === '(') {
    pos.index++; // Skip '('
    const list: unknown[] = [];
    while (tokens[pos.index] !== ')' && pos.index < tokens.length) {
      list.push(parseExpr(tokens, pos));
    }
    pos.index++; // Skip ')'
    return list;
  }

  if (token === '[') {
    pos.index++; // Skip '['
    const arr: unknown[] = [];
    while (tokens[pos.index] !== ']' && pos.index < tokens.length) {
      arr.push(parseExpr(tokens, pos));
    }
    pos.index++; // Skip ']'
    return arr;
  }

  // String literal
  if (token.startsWith('"') && token.endsWith('"')) {
    pos.index++;
    return token.slice(1, -1);
  }

  // Number
  if (/^-?\d+(\.\d+)?$/.test(token)) {
    pos.index++;
    return parseFloat(token);
  }

  // Symbol or keyword
  pos.index++;
  return token;
}

/**
 * Parse DSL condition expression like (< (rsi close 14) 30)
 */
function parseConditionExpr(expr: unknown[], defaultSymbol: string): ParsedCondition | null {
  if (!Array.isArray(expr) || expr.length < 3) return null;

  const [op, left, right] = expr;

  let comparator: Comparator;
  switch (op) {
    case '<': comparator = 'lt'; break;
    case '>': comparator = 'gt'; break;
    case '<=': comparator = 'lte'; break;
    case '>=': comparator = 'gte'; break;
    case 'cross-above': comparator = 'cross_above'; break;
    case 'cross-below': comparator = 'cross_below'; break;
    default: return null;
  }

  const leftOperand = parseOperand(left, defaultSymbol);
  const rightOperand = parseOperand(right, defaultSymbol);

  if (!leftOperand || !rightOperand) return null;

  return { comparator, left: leftOperand, right: rightOperand };
}

/**
 * Helper to check if a string is an uppercase ticker symbol (like BTC, SPY, ETH)
 */
function isTickerSymbol(str: string): boolean {
  return /^[A-Z][A-Z0-9]*$/.test(str);
}

/**
 * Helper to check if a string is a price source (close, open, high, low, volume)
 */
function isPriceSource(str: string): boolean {
  return ['close', 'open', 'high', 'low', 'volume'].includes(str.toLowerCase());
}

/**
 * Extract symbol from indicator arguments.
 * Templates use: (sma BTC 50) or (sma close 200)
 * - If first arg is uppercase ticker (BTC), use it as symbol
 * - If first arg is lowercase source (close), use defaultSymbol
 * Returns: { symbol, periodArgIndex } where periodArgIndex points to the period argument
 */
function extractSymbolFromIndicatorArgs(
  args: unknown[],
  defaultSymbol: string
): { symbol: string; periodArgIndex: number } {
  const firstArg = args[0];
  if (typeof firstArg === 'string') {
    // Check if it's an uppercase ticker (e.g., BTC, SPY, ETH)
    if (isTickerSymbol(firstArg)) {
      return { symbol: firstArg, periodArgIndex: 1 };
    }
    // It's a source (close, open, etc.) - use default symbol
    return { symbol: defaultSymbol, periodArgIndex: 1 };
  }
  return { symbol: defaultSymbol, periodArgIndex: 0 };
}

/**
 * Parse an operand (indicator call, price, or number)
 */
function parseOperand(expr: unknown, defaultSymbol: string): ConditionOperand | null {
  // Number
  if (typeof expr === 'number') {
    return { type: 'number', value: expr };
  }

  // Simple symbol like 'close', 'price'
  if (typeof expr === 'string') {
    if (expr === 'close' || expr === 'price') {
      return { type: 'price', symbol: defaultSymbol, field: 'close' };
    }
    if (expr === 'open') {
      return { type: 'price', symbol: defaultSymbol, field: 'open' };
    }
    if (expr === 'high') {
      return { type: 'price', symbol: defaultSymbol, field: 'high' };
    }
    if (expr === 'low') {
      return { type: 'price', symbol: defaultSymbol, field: 'low' };
    }
    // Try parsing as number
    const num = parseFloat(expr);
    if (!isNaN(num)) {
      return { type: 'number', value: num };
    }
    return null;
  }

  // Indicator call or price expression like (rsi SPY 14) or (price BTC)
  if (Array.isArray(expr) && expr.length >= 2) {
    const [indicator, ...args] = expr;

    // Handle (price SYMBOL) syntax - e.g., (price BTC) or (price SPY)
    if (indicator === 'price') {
      const firstArg = args[0];
      let symbol = defaultSymbol;
      let field: 'close' | 'open' | 'high' | 'low' = 'close';

      if (typeof firstArg === 'string') {
        if (isTickerSymbol(firstArg)) {
          symbol = firstArg;
        } else if (isPriceSource(firstArg)) {
          field = firstArg.toLowerCase() as 'close' | 'open' | 'high' | 'low';
        }
      }
      return { type: 'price', symbol, field };
    }

    switch (indicator) {
      case 'rsi': {
        // (rsi SPY 14) or (rsi close 14) - first arg can be symbol or source
        const { symbol, periodArgIndex } = extractSymbolFromIndicatorArgs(args, defaultSymbol);
        const period = typeof args[periodArgIndex] === 'number' ? args[periodArgIndex] : 14;
        return {
          type: 'indicator',
          indicator: 'rsi',
          period,
          symbol,
          source: 'close',
        };
      }
      case 'sma': {
        // (sma BTC 50) or (sma close 200)
        const { symbol, periodArgIndex } = extractSymbolFromIndicatorArgs(args, defaultSymbol);
        const period = typeof args[periodArgIndex] === 'number' ? args[periodArgIndex] : 20;
        return {
          type: 'indicator',
          indicator: 'sma',
          period,
          symbol,
          source: 'close',
        };
      }
      case 'ema': {
        // (ema ETH 20) or (ema close 20)
        const { symbol, periodArgIndex } = extractSymbolFromIndicatorArgs(args, defaultSymbol);
        const period = typeof args[periodArgIndex] === 'number' ? args[periodArgIndex] : 20;
        return {
          type: 'indicator',
          indicator: 'ema',
          period,
          symbol,
          source: 'close',
        };
      }
      case 'macd':
      case 'macd-line': {
        // (macd SPY 12 26 9 :line) or (macd-line close 12 26 9)
        const { symbol, periodArgIndex } = extractSymbolFromIndicatorArgs(args, defaultSymbol);
        return {
          type: 'indicator',
          indicator: 'macd_line',
          symbol,
          fastPeriod: typeof args[periodArgIndex] === 'number' ? args[periodArgIndex] : 12,
          slowPeriod: typeof args[periodArgIndex + 1] === 'number' ? args[periodArgIndex + 1] : 26,
          signalPeriod: typeof args[periodArgIndex + 2] === 'number' ? args[periodArgIndex + 2] : 9,
        };
      }
      case 'macd-signal': {
        const { symbol, periodArgIndex } = extractSymbolFromIndicatorArgs(args, defaultSymbol);
        return {
          type: 'indicator',
          indicator: 'macd_signal',
          symbol,
          fastPeriod: typeof args[periodArgIndex] === 'number' ? args[periodArgIndex] : 12,
          slowPeriod: typeof args[periodArgIndex + 1] === 'number' ? args[periodArgIndex + 1] : 26,
          signalPeriod: typeof args[periodArgIndex + 2] === 'number' ? args[periodArgIndex + 2] : 9,
        };
      }
      case 'bbands':
      case 'bb-upper':
      case 'bb-middle':
      case 'bb-lower': {
        // (bbands SPY 20 2 :upper) or (bb-upper close 20 2)
        const { symbol, periodArgIndex } = extractSymbolFromIndicatorArgs(args, defaultSymbol);
        const period = typeof args[periodArgIndex] === 'number' ? args[periodArgIndex] : 20;
        const stdDev = typeof args[periodArgIndex + 1] === 'number' ? args[periodArgIndex + 1] : 2.0;
        let indicatorName: 'bb_upper' | 'bb_middle' | 'bb_lower' = 'bb_middle';
        if (indicator === 'bb-upper') indicatorName = 'bb_upper';
        else if (indicator === 'bb-lower') indicatorName = 'bb_lower';
        else if (indicator === 'bbands') {
          // Check for :output parameter
          const outputIdx = args.findIndex(a => a === ':output' || a === ':upper' || a === ':middle' || a === ':lower');
          if (outputIdx !== -1) {
            const output = args[outputIdx] === ':output' ? args[outputIdx + 1] : String(args[outputIdx]).slice(1);
            if (output === 'upper') indicatorName = 'bb_upper';
            else if (output === 'lower') indicatorName = 'bb_lower';
          }
        }
        return {
          type: 'indicator',
          indicator: indicatorName,
          period,
          stdDev,
          symbol,
          source: 'close',
        };
      }
      case 'adx': {
        // (adx SPY 14) or (adx high low close 14)
        const { symbol, periodArgIndex } = extractSymbolFromIndicatorArgs(args, defaultSymbol);
        // If first arg is symbol, period is at index 1; otherwise it's at index 3 (after high, low, close)
        const period = typeof args[periodArgIndex] === 'number'
          ? args[periodArgIndex]
          : typeof args[3] === 'number' ? args[3] : 14;
        return {
          type: 'indicator',
          indicator: 'adx',
          period,
          symbol,
        };
      }
      case 'atr': {
        // (atr SPY 14) or (atr high low close 14)
        const { symbol, periodArgIndex } = extractSymbolFromIndicatorArgs(args, defaultSymbol);
        const period = typeof args[periodArgIndex] === 'number'
          ? args[periodArgIndex]
          : typeof args[3] === 'number' ? args[3] : 14;
        return {
          type: 'indicator',
          indicator: 'atr',
          period,
          symbol,
        };
      }
      case 'momentum':
      case 'roc': {
        // (momentum SPY 90) or (roc close 252)
        const { symbol, periodArgIndex } = extractSymbolFromIndicatorArgs(args, defaultSymbol);
        const period = typeof args[periodArgIndex] === 'number' ? args[periodArgIndex] : 252;
        return {
          type: 'indicator',
          indicator: 'sma', // Use SMA as placeholder for momentum/ROC
          period,
          symbol,
          source: 'close',
        };
      }
      case 'donchian': {
        // (donchian SPY 20 :output upper)
        const { symbol, periodArgIndex } = extractSymbolFromIndicatorArgs(args, defaultSymbol);
        const period = typeof args[periodArgIndex] === 'number' ? args[periodArgIndex] : 20;
        return {
          type: 'indicator',
          indicator: 'sma', // Use SMA as placeholder for Donchian
          period,
          symbol,
          source: 'close',
        };
      }
    }
  }

  return null;
}

/**
 * Parse a full strategy S-expression string into a block tree and metadata
 * Handles the allocation-based DSL format:
 *   (strategy "Name" :rebalance daily :description "..." (weight ...) (group ...) ...)
 */
export function fromDSLString(dslString: string): ParsedDSL | null {
  try {
    const tokens = tokenize(dslString);
    const pos = { index: 0 };
    const parsed = parseExpr(tokens, pos);

    if (!Array.isArray(parsed) || parsed[0] !== 'strategy') {
      return null;
    }

    blockIdCounter = 0;
    const rootId = generateBlockId();
    const blocks: Record<BlockId, Block> = {};

    // Get strategy name (first argument after 'strategy')
    let strategyName = 'Imported Strategy';
    let startIdx = 1;

    if (typeof parsed[1] === 'string' && !String(parsed[1]).startsWith(':')) {
      strategyName = parsed[1];
      startIdx = 2;
    }

    const root: RootBlock = {
      id: rootId,
      type: 'root',
      parentId: null,
      name: strategyName,
      childIds: [],
    };
    blocks[rootId] = root;

    // Initialize metadata with parsed name
    const metadata: Partial<StrategyMetadata> = {
      name: strategyName,
    };

    // Parse remaining elements (key-value pairs and nested blocks)
    let i = startIdx;
    while (i < parsed.length) {
      const item = parsed[i];

      // Key-value pairs - parse metadata
      if (typeof item === 'string' && item.startsWith(':')) {
        const key = item.slice(1); // Remove leading ':'
        const value = parsed[i + 1];

        switch (key) {
          case 'rebalance':
            if (typeof value === 'string') {
              metadata.timeframe = rebalanceToTimeframe(value);
            }
            break;
          case 'description':
            if (typeof value === 'string') {
              metadata.description = value;
            }
            break;
          case 'stop-loss-pct':
            if (typeof value === 'number') {
              metadata.stopLossPct = value;
            }
            break;
          case 'take-profit-pct':
            if (typeof value === 'number') {
              metadata.takeProfitPct = value;
            }
            break;
          case 'position-size':
            if (typeof value === 'number') {
              metadata.positionSizePct = value;
            }
            break;
        }

        i += 2; // Skip key and value
        continue;
      }

      // Nested blocks
      if (Array.isArray(item)) {
        const childIds = parseBlockFromExpr(item, rootId, blocks);
        for (const childId of childIds) {
          root.childIds.push(childId);
        }
      }

      i++;
    }

    return { tree: { rootId, blocks }, metadata };
  } catch {
    return null;
  }
}

/**
 * Parse a block expression and add it to the blocks map
 * Returns an array of block IDs (usually one, but IF blocks may return [ifId, elseId])
 */
function parseBlockFromExpr(
  expr: unknown[],
  parentId: BlockId,
  blocks: Record<BlockId, Block>
): BlockId[] {
  if (!Array.isArray(expr) || expr.length === 0) return [];

  const blockType = expr[0];

  switch (blockType) {
    case 'asset':
      return [parseAssetExpr(expr, parentId, blocks)];
    case 'weight':
      return [parseWeightExpr(expr, parentId, blocks)];
    case 'group':
      return [parseGroupExpr(expr, parentId, blocks)];
    case 'if':
      return parseIfExpr(expr, parentId, blocks); // Returns [ifId] or [ifId, elseId]
    case 'filter':
      return [parseFilterExpr(expr, parentId, blocks)];
    default:
      return [];
  }
}

/**
 * Parse (asset SYMBOL [:weight N])
 */
function parseAssetExpr(
  expr: unknown[],
  parentId: BlockId,
  blocks: Record<BlockId, Block>
): BlockId {
  const id = generateBlockId();
  const symbol = typeof expr[1] === 'string' ? expr[1] : 'UNKNOWN';

  const asset: AssetBlock = {
    id,
    type: 'asset',
    parentId,
    symbol,
    exchange: 'NASDAQ',
    displayName: symbol,
  };
  blocks[id] = asset;
  return id;
}

/**
 * Parse (weight :method METHOD [:lookback N] children...)
 */
function parseWeightExpr(
  expr: unknown[],
  parentId: BlockId,
  blocks: Record<BlockId, Block>
): BlockId {
  const id = generateBlockId();

  // Create weight block FIRST with empty childIds, so that parseIfExpr
  // can find the parent and add else blocks to it
  const weightBlock: WeightBlock = {
    id,
    type: 'weight',
    parentId,
    method: 'equal',
    allocations: {},
    lookbackDays: undefined,
    childIds: [],
  };
  blocks[id] = weightBlock;

  let i = 1;
  while (i < expr.length) {
    const item = expr[i];

    if (item === ':method') {
      const methodVal = String(expr[i + 1] || 'equal');
      // Convert kebab-case to snake_case for internal representation
      weightBlock.method = methodVal.replace(/-/g, '_') as WeightBlock['method'];
      i += 2;
      continue;
    }

    if (item === ':lookback') {
      const lookbackVal = expr[i + 1];
      weightBlock.lookbackDays = typeof lookbackVal === 'number' ? lookbackVal : undefined;
      i += 2;
      continue;
    }

    // Skip other parameters
    if (typeof item === 'string' && item.startsWith(':')) {
      i += 2;
      continue;
    }

    // Parse child blocks
    if (Array.isArray(item)) {
      // Check if it's an asset with weight
      if (item[0] === 'asset') {
        const childId = parseAssetExpr(item, id, blocks);
        weightBlock.childIds.push(childId);

        // Extract weight if specified
        for (let j = 2; j < item.length; j++) {
          if (item[j] === ':weight' && typeof item[j + 1] === 'number') {
            weightBlock.allocations[childId] = item[j + 1];
          }
        }
      } else {
        const childIds = parseBlockFromExpr(item, id, blocks);
        // Add all returned IDs (IF blocks may return [ifId, elseId])
        for (const childId of childIds) {
          weightBlock.childIds.push(childId);
        }

        // Extract :weight from any child block type (groups, filters, etc.)
        // Handles syntax like: (group "Name" :weight 50 children...)
        for (let j = 1; j < item.length; j++) {
          if (item[j] === ':weight' && typeof item[j + 1] === 'number') {
            // Apply weight to the first child ID (the primary block, not else block)
            if (childIds.length > 0) {
              weightBlock.allocations[childIds[0]] = item[j + 1];
            }
            break;
          }
        }
      }
    }

    i++;
  }

  return id;
}

/**
 * Parse (group "Name" children...)
 */
function parseGroupExpr(
  expr: unknown[],
  parentId: BlockId,
  blocks: Record<BlockId, Block>
): BlockId {
  const id = generateBlockId();
  const name = typeof expr[1] === 'string' ? expr[1] : 'Group';

  // Create group block FIRST with empty childIds, so that parseIfExpr
  // can find the parent and add else blocks to it
  const groupBlock = {
    id,
    type: 'group' as const,
    parentId,
    name,
    childIds: [] as BlockId[],
  };
  blocks[id] = groupBlock;

  // Parse children - IF blocks may return [ifId, elseId]
  for (let i = 2; i < expr.length; i++) {
    const item = expr[i];
    if (Array.isArray(item)) {
      const childIds = parseBlockFromExpr(item, id, blocks);
      for (const childId of childIds) {
        groupBlock.childIds.push(childId);
      }
    }
  }

  return id;
}

/**
 * Parse (if CONDITION THEN_BLOCK [(else ELSE_BLOCK)])
 * Handles two formats:
 * 1. (if CONDITION (then ...) (else ...)) - explicit then wrapper
 * 2. (if CONDITION BLOCK (else ...)) - direct then block without wrapper
 *
 * Returns [ifId] or [ifId, elseId] to ensure correct ordering in parent
 */
function parseIfExpr(
  expr: unknown[],
  parentId: BlockId,
  blocks: Record<BlockId, Block>
): BlockId[] {
  const ifId = generateBlockId();
  const ifChildIds: BlockId[] = [];
  const elseChildIds: BlockId[] = [];
  let conditionExpr: unknown[] | null = null;

  // Find condition, then block, and else block
  for (let i = 1; i < expr.length; i++) {
    const item = expr[i];
    if (!Array.isArray(item)) continue;

    if (item[0] === 'then') {
      // Explicit (then ...) wrapper - parse children
      for (let j = 1; j < item.length; j++) {
        if (Array.isArray(item[j])) {
          const childIds = parseBlockFromExpr(item[j], ifId, blocks);
          for (const childId of childIds) {
            ifChildIds.push(childId);
          }
        }
      }
    } else if (item[0] === 'else') {
      // Parse else children (we'll create the else block later)
      // Use a placeholder parent ID that we'll fix after creating the else block
      for (let j = 1; j < item.length; j++) {
        if (Array.isArray(item[j])) {
          const childIds = parseBlockFromExpr(item[j], ifId, blocks);
          for (const childId of childIds) {
            elseChildIds.push(childId);
          }
        }
      }
    } else if (!conditionExpr) {
      // First array that's not then/else is the condition
      conditionExpr = item;
    } else {
      // Any other block after condition is the then-block content (no wrapper)
      // This handles: (if CONDITION (weight ...) (else ...))
      const childIds = parseBlockFromExpr(item, ifId, blocks);
      for (const childId of childIds) {
        ifChildIds.push(childId);
      }
    }
  }

  // Parse condition
  let condition: ConditionExpression | undefined;
  if (conditionExpr) {
    const parsed = parseConditionExpr(conditionExpr, 'SPY');
    if (parsed) {
      condition = {
        left: parsed.left,
        comparator: parsed.comparator,
        right: parsed.right,
      };
    }
  }

  // Default condition if none provided
  if (!condition) {
    condition = {
      left: { type: 'price', symbol: 'SPY', field: 'close' },
      comparator: 'gt',
      right: { type: 'number', value: 0 },
    };
  }

  const ifBlock: IfBlock = {
    id: ifId,
    type: 'if',
    parentId,
    condition,
    conditionText: conditionToText(condition),
    childIds: ifChildIds,
  };
  blocks[ifId] = ifBlock;

  // Create else block if there are else children
  if (elseChildIds.length > 0) {
    const elseId = generateBlockId();

    // Update else children to have correct parent (the else block)
    for (const childId of elseChildIds) {
      const child = blocks[childId];
      if (child) {
        child.parentId = elseId;
      }
    }

    const elseBlock: ElseBlock = {
      id: elseId,
      type: 'else',
      parentId,
      ifBlockId: ifId,
      childIds: elseChildIds,
    };
    blocks[elseId] = elseBlock;

    // Return both IF and ELSE IDs in correct order
    // The caller will add them to parent.childIds in this order
    return [ifId, elseId];
  }

  return [ifId];
}

/**
 * Parse (filter :by CRITERIA :select (top/bottom N) [:lookback N] children...)
 */
function parseFilterExpr(
  expr: unknown[],
  parentId: BlockId,
  blocks: Record<BlockId, Block>
): BlockId {
  const id = generateBlockId();
  let sortBy = 'momentum';
  let selection: 'top' | 'bottom' = 'top';
  let count = 3;
  let period = '3m';
  const customSymbols: string[] = [];

  let i = 1;
  while (i < expr.length) {
    const item = expr[i];

    if (item === ':by') {
      const byVal = String(expr[i + 1] || 'returns');
      // Map 'returns' back to 'momentum'
      sortBy = byVal === 'returns' ? 'momentum' : byVal;
      i += 2;
      continue;
    }

    if (item === ':select') {
      const selectExpr = expr[i + 1];
      if (Array.isArray(selectExpr) && selectExpr.length >= 2) {
        selection = selectExpr[0] === 'bottom' ? 'bottom' : 'top';
        count = typeof selectExpr[1] === 'number' ? selectExpr[1] : 3;
      }
      i += 2;
      continue;
    }

    if (item === ':lookback') {
      const lookbackVal = expr[i + 1];
      const lookback = typeof lookbackVal === 'number' ? lookbackVal : 63;
      // Map lookback days to period
      if (lookback <= 21) period = '1m';
      else if (lookback <= 63) period = '3m';
      else if (lookback <= 126) period = '6m';
      else period = '12m';
      i += 2;
      continue;
    }

    // Skip other parameters
    if (typeof item === 'string' && item.startsWith(':')) {
      i += 2;
      continue;
    }

    // Parse child assets for custom symbols
    if (Array.isArray(item) && item[0] === 'asset') {
      const symbol = typeof item[1] === 'string' ? item[1] : '';
      if (symbol) customSymbols.push(symbol);
    }

    i++;
  }

  const filter: FilterBlock = {
    id,
    type: 'filter',
    parentId,
    config: {
      sortBy: sortBy as FilterConfig['sortBy'],
      selection,
      count,
      period: period as FilterConfig['period'],
      universe: customSymbols.length > 0 ? 'custom' : 'sp500',
      customSymbols: customSymbols.length > 0 ? customSymbols : undefined,
    },
    displayText: `${selection === 'top' ? 'Top' : 'Bottom'} ${count} by ${sortBy}`,
    childIds: [],
  };
  blocks[id] = filter;
  return id;
}

// ============================================
// Utility Exports
// ============================================

export const strategySerializer = {
  toDSL,
  fromDSL,
  fromDSLString,
  validateTree,
  conditionToText,
  tokenizeWithPositions,
  toKebabCase,
  fromKebabCase,
  isKebabCaseKeyword,
};

export default strategySerializer;
