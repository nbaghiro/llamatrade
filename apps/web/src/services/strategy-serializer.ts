// Strategy Serializer
// Converts between visual block tree and S-expression DSL format

import type { StrategyConfigJSON, StrategyType } from '../types/strategy';
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
  strategyType: StrategyType;
  timeframe: string;
  stopLossPct?: number;
  takeProfitPct?: number;
  trailingStopPct?: number;
  positionSizePct?: number;
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
    return operand.field === 'current' ? 'close' : operand.field;
  }

  if (operand.type === 'number') {
    return String(operand.value);
  }

  // Indicator
  const ind = operand;
  const source = ind.source || 'close';

  switch (ind.indicator) {
    case 'sma':
      return `(sma ${source} ${ind.period || 20})`;
    case 'ema':
      return `(ema ${source} ${ind.period || 20})`;
    case 'rsi':
      return `(rsi ${source} ${ind.period || 14})`;
    case 'macd_line':
      return `(macd-line ${source} ${ind.fastPeriod || 12} ${ind.slowPeriod || 26} ${ind.signalPeriod || 9})`;
    case 'macd_signal':
      return `(macd-signal ${source} ${ind.fastPeriod || 12} ${ind.slowPeriod || 26} ${ind.signalPeriod || 9})`;
    case 'bb_upper':
      return `(bb-upper ${source} ${ind.period || 20} ${ind.stdDev || 2.0})`;
    case 'bb_middle':
      return `(bb-middle ${source} ${ind.period || 20} ${ind.stdDev || 2.0})`;
    case 'bb_lower':
      return `(bb-lower ${source} ${ind.period || 20} ${ind.stdDev || 2.0})`;
    case 'atr':
      return `(atr high low close ${ind.period || 14})`;
    case 'adx':
      return `(adx high low close ${ind.period || 14})`;
    case 'stochastic_k':
    case 'stochastic_d':
      return `(stochastic high low close ${ind.period || 14} 3 3)`;
    case 'cci':
      return `(cci ${source} ${ind.period || 20})`;
    case 'williams_r':
      return `(williams-r high low close ${ind.period || 14})`;
    case 'obv':
      return `(obv close volume)`;
    case 'mfi':
      return `(mfi high low close volume ${ind.period || 14})`;
    case 'vwap':
      return `(vwap close volume)`;
    default:
      return `(${ind.indicator} ${source})`;
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
 */
function serializeWeightBlock(
  block: WeightBlock,
  tree: StrategyTree,
  indent: string
): string {
  const children = block.childIds.map((id) => tree.blocks[id]);
  const lines: string[] = [];

  lines.push(`${indent}(allocation :method ${block.method}`);

  if (block.lookbackDays) {
    lines.push(`${indent}  :lookback-days ${block.lookbackDays}`);
  }

  lines.push(`${indent}  :children [`);

  for (const child of children) {
    if (isAssetBlock(child)) {
      const allocation = block.allocations[child.id] ?? 0;
      if (block.method === 'specified') {
        lines.push(`${indent}    {:symbol "${child.symbol}" :weight ${allocation / 100}}`);
      } else {
        lines.push(`${indent}    {:symbol "${child.symbol}"}`);
      }
    } else if (isGroupBlock(child)) {
      lines.push(`${indent}    {:group "${child.name}"`);
      lines.push(serializeChildren(child.childIds, tree, indent + '      '));
      lines.push(`${indent}    }`);
    } else if (isIfBlock(child)) {
      lines.push(serializeIfBlock(child, tree, indent + '    '));
    }
  }

  lines.push(`${indent}  ])`);
  return lines.join('\n');
}

/**
 * Serialize IF/ELSE block to DSL
 */
function serializeIfBlock(block: IfBlock, tree: StrategyTree, indent: string): string {
  const lines: string[] = [];

  lines.push(`${indent}(if ${conditionToDSL(block.condition)}`);
  lines.push(`${indent}  (then`);
  lines.push(serializeChildren(block.childIds, tree, indent + '    '));
  lines.push(`${indent}  )`);

  // Find associated else block
  const parent = tree.blocks[block.parentId];
  if (parent && hasChildren(parent)) {
    const parentBlock = parent as { childIds: BlockId[] };
    const blockIndex = parentBlock.childIds.indexOf(block.id);
    if (blockIndex >= 0 && blockIndex < parentBlock.childIds.length - 1) {
      const nextId = parentBlock.childIds[blockIndex + 1];
      const nextBlock = tree.blocks[nextId];
      if (isElseBlock(nextBlock) && nextBlock.ifBlockId === block.id) {
        lines.push(`${indent}  (else`);
        lines.push(serializeChildren(nextBlock.childIds, tree, indent + '    '));
        lines.push(`${indent}  )`);
      }
    }
  }

  lines.push(`${indent})`);
  return lines.join('\n');
}

/**
 * Serialize filter block to DSL
 */
function serializeFilterBlock(block: FilterBlock, indent: string): string {
  const config = block.config;
  const lines: string[] = [];

  lines.push(`${indent}(filter`);
  lines.push(`${indent}  :selection ${config.selection}`);
  lines.push(`${indent}  :count ${config.count}`);
  lines.push(`${indent}  :universe ${config.universe}`);
  lines.push(`${indent}  :sort-by ${config.sortBy}`);
  lines.push(`${indent}  :period "${config.period}"`);

  if (config.customSymbols && config.customSymbols.length > 0) {
    lines.push(`${indent}  :custom-symbols [${config.customSymbols.map((s) => `"${s}"`).join(' ')}]`);
  }

  lines.push(`${indent})`);
  return lines.join('\n');
}

/**
 * Serialize children of a container block
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
      lines.push(`${indent}{:symbol "${child.symbol}"}`);
    } else if (isGroupBlock(child)) {
      lines.push(`${indent}(group :name "${child.name}"`);
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
 * Convert block tree to S-expression DSL string
 */
export function toDSL(tree: StrategyTree, metadata: StrategyMetadata): string {
  const root = tree.blocks[tree.rootId] as RootBlock;
  const symbols = extractSymbols(tree);

  const lines: string[] = [];

  lines.push('(strategy');
  lines.push(`  :name "${metadata.name}"`);
  lines.push(`  :type ${metadata.strategyType}`);
  lines.push(`  :symbols [${symbols.map((s) => `"${s}"`).join(' ')}]`);
  lines.push(`  :timeframe "${metadata.timeframe}"`);

  if (metadata.description) {
    lines.push(`  :description "${metadata.description}"`);
  }

  if (metadata.positionSizePct !== undefined) {
    lines.push(`  :position-size-pct ${metadata.positionSizePct}`);
  }

  if (metadata.stopLossPct !== undefined) {
    lines.push(`  :stop-loss-pct ${metadata.stopLossPct}`);
  }

  if (metadata.takeProfitPct !== undefined) {
    lines.push(`  :take-profit-pct ${metadata.takeProfitPct}`);
  }

  if (metadata.trailingStopPct !== undefined) {
    lines.push(`  :trailing-stop-pct ${metadata.trailingStopPct}`);
  }

  // Serialize portfolio allocation
  lines.push('  :portfolio (');
  lines.push(serializeChildren(root.childIds, tree, '    '));
  lines.push('  )');

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

/**
 * Validate a strategy tree before saving
 */
export function validateTree(tree: StrategyTree): ValidationResult {
  const errors: ValidationError[] = [];
  const warnings: ValidationError[] = [];

  const root = tree.blocks[tree.rootId];
  if (!root || root.type !== 'root') {
    errors.push({
      message: 'Strategy must have a root block',
      severity: 'error',
    });
    return { valid: false, errors, warnings };
  }

  // Check for at least one asset
  const hasAssets = Object.values(tree.blocks).some((b) => isAssetBlock(b));
  if (!hasAssets) {
    errors.push({
      message: 'Strategy must contain at least one asset',
      severity: 'error',
    });
  }

  // Validate each block
  for (const block of Object.values(tree.blocks)) {
    // Check parent exists
    if (block.parentId !== null && !tree.blocks[block.parentId]) {
      errors.push({
        blockId: block.id,
        message: `Block "${block.id}" has invalid parent reference`,
        severity: 'error',
      });
    }

    // Validate weight blocks
    if (isWeightBlock(block)) {
      if (block.method === 'specified') {
        // Check allocations sum to 100
        const total = Object.values(block.allocations).reduce((sum, v) => sum + v, 0);
        if (Math.abs(total - 100) > 0.01 && block.childIds.length > 0) {
          warnings.push({
            blockId: block.id,
            message: `Weight allocations sum to ${total}%, not 100%`,
            severity: 'warning',
          });
        }
      }
    }

    // Validate IF blocks
    if (isIfBlock(block)) {
      if (!block.condition) {
        errors.push({
          blockId: block.id,
          message: 'IF block must have a condition',
          severity: 'error',
        });
      }
    }

    // Validate filter blocks
    if (isFilterBlock(block)) {
      if (block.config.count < 1) {
        errors.push({
          blockId: block.id,
          message: 'Filter must select at least 1 asset',
          severity: 'error',
        });
      }
    }
  }

  // Check for orphan blocks
  const reachable = new Set<BlockId>();
  function markReachable(id: BlockId): void {
    if (reachable.has(id)) return;
    reachable.add(id);
    const block = tree.blocks[id];
    if (block && hasChildren(block)) {
      const parentBlock = block as { childIds: BlockId[] };
      for (const childId of parentBlock.childIds) {
        markReachable(childId);
      }
    }
  }
  markReachable(tree.rootId);

  for (const id of Object.keys(tree.blocks)) {
    if (!reachable.has(id)) {
      warnings.push({
        blockId: id,
        message: `Block "${id}" is not reachable from root`,
        severity: 'warning',
      });
    }
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings,
  };
}

// ============================================
// S-Expression DSL Parsing (config_sexpr → Block Tree)
// ============================================

interface ParsedCondition {
  comparator: Comparator;
  left: ConditionOperand;
  right: ConditionOperand;
}

/**
 * Simple tokenizer for S-expressions
 */
function tokenize(input: string): string[] {
  const tokens: string[] = [];
  let current = 0;

  while (current < input.length) {
    const char = input[current];

    // Skip whitespace
    if (/\s/.test(char)) {
      current++;
      continue;
    }

    // Parentheses and brackets
    if (char === '(' || char === ')' || char === '[' || char === ']' || char === '{' || char === '}') {
      tokens.push(char);
      current++;
      continue;
    }

    // String literal
    if (char === '"') {
      let value = '';
      current++; // Skip opening quote
      while (current < input.length && input[current] !== '"') {
        value += input[current];
        current++;
      }
      current++; // Skip closing quote
      tokens.push(`"${value}"`);
      continue;
    }

    // Keyword (starts with :)
    if (char === ':') {
      let value = ':';
      current++;
      while (current < input.length && /[a-zA-Z0-9_-]/.test(input[current])) {
        value += input[current];
        current++;
      }
      tokens.push(value);
      continue;
    }

    // Number or symbol
    if (/[a-zA-Z0-9.<>=_-]/.test(char)) {
      let value = '';
      while (current < input.length && /[a-zA-Z0-9.<>=_-]/.test(input[current])) {
        value += input[current];
        current++;
      }
      tokens.push(value);
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

  // Indicator call like (rsi close 14)
  if (Array.isArray(expr) && expr.length >= 2) {
    const [indicator, ...args] = expr;

    switch (indicator) {
      case 'rsi': {
        // (rsi close 14)
        const period = typeof args[1] === 'number' ? args[1] : 14;
        return {
          type: 'indicator',
          indicator: 'rsi',
          period,
          symbol: defaultSymbol,
          source: 'close',
        };
      }
      case 'sma': {
        // (sma close 200)
        const period = typeof args[1] === 'number' ? args[1] : 20;
        return {
          type: 'indicator',
          indicator: 'sma',
          period,
          symbol: defaultSymbol,
          source: 'close',
        };
      }
      case 'ema': {
        // (ema close 20)
        const period = typeof args[1] === 'number' ? args[1] : 20;
        return {
          type: 'indicator',
          indicator: 'ema',
          period,
          symbol: defaultSymbol,
          source: 'close',
        };
      }
      case 'macd-line': {
        // (macd-line close 12 26 9)
        return {
          type: 'indicator',
          indicator: 'macd_line',
          symbol: defaultSymbol,
          fastPeriod: typeof args[1] === 'number' ? args[1] : 12,
          slowPeriod: typeof args[2] === 'number' ? args[2] : 26,
          signalPeriod: typeof args[3] === 'number' ? args[3] : 9,
        };
      }
      case 'macd-signal': {
        return {
          type: 'indicator',
          indicator: 'macd_signal',
          symbol: defaultSymbol,
          fastPeriod: typeof args[1] === 'number' ? args[1] : 12,
          slowPeriod: typeof args[2] === 'number' ? args[2] : 26,
          signalPeriod: typeof args[3] === 'number' ? args[3] : 9,
        };
      }
      case 'bb-upper':
      case 'bb-middle':
      case 'bb-lower': {
        const period = typeof args[1] === 'number' ? args[1] : 20;
        const stdDev = typeof args[2] === 'number' ? args[2] : 2.0;
        const indicatorName = indicator === 'bb-upper' ? 'bb_upper'
          : indicator === 'bb-middle' ? 'bb_middle'
          : 'bb_lower';
        return {
          type: 'indicator',
          indicator: indicatorName,
          period,
          stdDev,
          symbol: defaultSymbol,
          source: 'close',
        };
      }
      case 'adx': {
        // (adx high low close 14)
        const period = typeof args[3] === 'number' ? args[3] : 14;
        return {
          type: 'indicator',
          indicator: 'adx',
          period,
          symbol: defaultSymbol,
        };
      }
      case 'atr': {
        const period = typeof args[3] === 'number' ? args[3] : 14;
        return {
          type: 'indicator',
          indicator: 'atr',
          period,
          symbol: defaultSymbol,
        };
      }
      case 'roc': {
        // (roc close 252)
        const period = typeof args[1] === 'number' ? args[1] : 252;
        return {
          type: 'indicator',
          indicator: 'sma', // Use SMA as placeholder for ROC
          period,
          symbol: defaultSymbol,
          source: 'close',
        };
      }
    }
  }

  return null;
}

interface ParsedStrategy {
  name: string;
  type: string;
  symbols: string[];
  timeframe: string;
  entry?: ConditionExpression;
  exit?: ConditionExpression;
  positionSizePct?: number;
  stopLossPct?: number;
  takeProfitPct?: number;
}

/**
 * Parse a full strategy S-expression string
 */
export function parseDSLString(dslString: string): ParsedStrategy | null {
  try {
    const tokens = tokenize(dslString);
    const pos = { index: 0 };
    const parsed = parseExpr(tokens, pos);

    if (!Array.isArray(parsed) || parsed[0] !== 'strategy') {
      return null;
    }

    const result: ParsedStrategy = {
      name: '',
      type: 'custom',
      symbols: [],
      timeframe: '1D',
    };

    // Parse key-value pairs
    for (let i = 1; i < parsed.length; i += 2) {
      const key = parsed[i];
      const value = parsed[i + 1];

      switch (key) {
        case ':name':
          result.name = String(value);
          break;
        case ':type':
          result.type = String(value);
          break;
        case ':symbols':
          if (Array.isArray(value)) {
            result.symbols = value.map(String);
          }
          break;
        case ':timeframe':
          result.timeframe = String(value);
          break;
        case ':entry':
          if (Array.isArray(value)) {
            const cond = parseConditionExpr(value, result.symbols[0] || 'SPY');
            if (cond) {
              result.entry = {
                left: cond.left,
                comparator: cond.comparator,
                right: cond.right,
              };
            }
          }
          break;
        case ':exit':
          if (Array.isArray(value)) {
            const cond = parseConditionExpr(value, result.symbols[0] || 'SPY');
            if (cond) {
              result.exit = {
                left: cond.left,
                comparator: cond.comparator,
                right: cond.right,
              };
            }
          }
          break;
        case ':position-size-pct':
          result.positionSizePct = Number(value);
          break;
        case ':stop-loss-pct':
          result.stopLossPct = Number(value);
          break;
        case ':take-profit-pct':
          result.takeProfitPct = Number(value);
          break;
      }
    }

    return result;
  } catch {
    return null;
  }
}

/**
 * Create a block tree from a parsed DSL strategy
 */
export function fromDSLString(dslString: string): StrategyTree | null {
  const parsed = parseDSLString(dslString);
  if (!parsed) return null;

  blockIdCounter = 0;
  const rootId = generateBlockId();
  const blocks: Record<BlockId, Block> = {};

  const root: RootBlock = {
    id: rootId,
    type: 'root',
    parentId: null,
    name: parsed.name,
    childIds: [],
  };
  blocks[rootId] = root;

  // Create asset blocks for each symbol
  for (const symbol of parsed.symbols) {
    const assetId = generateBlockId();
    const asset: AssetBlock = {
      id: assetId,
      type: 'asset',
      parentId: rootId,
      symbol,
      exchange: 'NASDAQ',
      displayName: symbol,
    };
    blocks[assetId] = asset;
    root.childIds.push(assetId);
  }

  // Create entry condition block
  if (parsed.entry) {
    const ifId = generateBlockId();
    const elseId = generateBlockId();

    const ifBlock: IfBlock = {
      id: ifId,
      type: 'if',
      parentId: rootId,
      condition: parsed.entry,
      conditionText: `Entry: ${conditionToText(parsed.entry)}`,
      childIds: [],
    };
    blocks[ifId] = ifBlock;
    root.childIds.push(ifId);

    const elseBlock: ElseBlock = {
      id: elseId,
      type: 'else',
      parentId: rootId,
      ifBlockId: ifId,
      childIds: [],
    };
    blocks[elseId] = elseBlock;
    root.childIds.push(elseId);
  }

  // Create exit condition block
  if (parsed.exit) {
    const ifId = generateBlockId();
    const elseId = generateBlockId();

    const ifBlock: IfBlock = {
      id: ifId,
      type: 'if',
      parentId: rootId,
      condition: parsed.exit,
      conditionText: `Exit: ${conditionToText(parsed.exit)}`,
      childIds: [],
    };
    blocks[ifId] = ifBlock;
    root.childIds.push(ifId);

    const elseBlock: ElseBlock = {
      id: elseId,
      type: 'else',
      parentId: rootId,
      ifBlockId: ifId,
      childIds: [],
    };
    blocks[elseId] = elseBlock;
    root.childIds.push(elseId);
  }

  return { rootId, blocks };
}

// ============================================
// Utility Exports
// ============================================

export const strategySerializer = {
  toDSL,
  fromDSL,
  fromDSLString,
  parseDSLString,
  validateTree,
  conditionToText,
};

export default strategySerializer;
