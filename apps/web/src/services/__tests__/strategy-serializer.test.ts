/* eslint-disable @typescript-eslint/no-non-null-assertion */
import {
  tokenizeWithPositions,
  toKebabCase,
  fromKebabCase,
  isKebabCaseKeyword,
  fromDSL,
  fromDSLString,
  toDSL,
  validateTree,
  type StrategyMetadata,
} from '@llamatrade/core/strategy/serializer';
import type { Block } from '@llamatrade/core/strategy/types';
import { describe, it, expect } from 'vitest';


describe('tokenizeWithPositions', () => {
  it('should tokenize simple S-expression', () => {
    const input = '(strategy :name "Test")';
    const tokens = tokenizeWithPositions(input);

    expect(tokens.length).toBe(5);
    expect(tokens[0]).toMatchObject({ type: 'bracket', value: '(' });
    expect(tokens[1]).toMatchObject({ type: 'keyword', value: 'strategy' });
    expect(tokens[2]).toMatchObject({ type: 'parameter', value: ':name' });
    expect(tokens[3]).toMatchObject({ type: 'string', value: '"Test"' });
    expect(tokens[4]).toMatchObject({ type: 'bracket', value: ')' });
  });

  it('should track line and column positions', () => {
    const input = '(strategy\n  :name "Test")';
    const tokens = tokenizeWithPositions(input);

    // First line
    expect(tokens[0]).toMatchObject({ line: 1, column: 1 });
    expect(tokens[1]).toMatchObject({ line: 1, column: 2 });

    // Second line
    expect(tokens[2]).toMatchObject({ line: 2, column: 3 });
    expect(tokens[3]).toMatchObject({ line: 2, column: 9 });
  });

  it('should track character offsets', () => {
    const input = '(strategy :name)';
    const tokens = tokenizeWithPositions(input);

    expect(tokens[0]).toMatchObject({ start: 0, end: 1 }); // (
    expect(tokens[1]).toMatchObject({ start: 1, end: 9 }); // strategy
    expect(tokens[2]).toMatchObject({ start: 10, end: 15 }); // :name
    expect(tokens[3]).toMatchObject({ start: 15, end: 16 }); // )
  });

  it('should classify keywords correctly', () => {
    const input = '(strategy weight group if else filter)';
    const tokens = tokenizeWithPositions(input);

    const keywords = tokens.filter((t) => t.type === 'keyword');
    expect(keywords.map((t) => t.value)).toEqual([
      'strategy', 'weight', 'group', 'if', 'else', 'filter',
    ]);
  });

  it('should classify methods correctly', () => {
    const input = '(equal momentum inverse-volatility)';
    const tokens = tokenizeWithPositions(input);

    const methods = tokens.filter((t) => t.type === 'method');
    expect(methods.map((t) => t.value)).toEqual([
      'equal', 'momentum', 'inverse-volatility',
    ]);
  });

  it('should classify indicators correctly', () => {
    const input = '(sma ema rsi macd-line bb-upper)';
    const tokens = tokenizeWithPositions(input);

    const indicators = tokens.filter((t) => t.type === 'indicator');
    expect(indicators.map((t) => t.value)).toEqual([
      'sma', 'ema', 'rsi', 'macd-line', 'bb-upper',
    ]);
  });

  it('should classify operators correctly', () => {
    const input = '(> < >= <= cross-above cross-below)';
    const tokens = tokenizeWithPositions(input);

    const operators = tokens.filter((t) => t.type === 'operator');
    expect(operators.map((t) => t.value)).toEqual([
      '>', '<', '>=', '<=', 'cross-above', 'cross-below',
    ]);
  });

  it('should classify numbers correctly', () => {
    const input = '(50 -10 0.05 100.5)';
    const tokens = tokenizeWithPositions(input);

    const numbers = tokens.filter((t) => t.type === 'number');
    expect(numbers.map((t) => t.value)).toEqual(['50', '-10', '0.05', '100.5']);
  });

  it('should classify symbols (tickers) correctly', () => {
    const input = '("SPY" VTI BND QQQ)';
    const tokens = tokenizeWithPositions(input);

    const symbols = tokens.filter((t) => t.type === 'symbol');
    expect(symbols.map((t) => t.value)).toEqual(['VTI', 'BND', 'QQQ']);
  });

  it('should handle comments', () => {
    const input = '; This is a comment\n(strategy)';
    const tokens = tokenizeWithPositions(input);

    const comments = tokens.filter((t) => t.type === 'comment');
    expect(comments.length).toBe(1);
    expect(comments[0].value).toBe('; This is a comment');
  });

  it('should handle strings with spaces', () => {
    const input = '(:name "My Strategy Name")';
    const tokens = tokenizeWithPositions(input);

    const strings = tokens.filter((t) => t.type === 'string');
    expect(strings.length).toBe(1);
    expect(strings[0].value).toBe('"My Strategy Name"');
  });

  it('should handle nested brackets', () => {
    const input = '((sma close 20) (ema close 50))';
    const tokens = tokenizeWithPositions(input);

    const brackets = tokens.filter((t) => t.type === 'bracket');
    expect(brackets.length).toBe(6); // 3 opening, 3 closing
  });

  it('should handle array syntax', () => {
    const input = '[:symbols ["SPY" "QQQ"]]';
    const tokens = tokenizeWithPositions(input);

    const brackets = tokens.filter((t) => t.type === 'bracket');
    expect(brackets.map((t) => t.value)).toContain('[');
    expect(brackets.map((t) => t.value)).toContain(']');
  });
});

describe('case conversion helpers', () => {
  describe('toKebabCase', () => {
    it('should convert snake_case to kebab-case', () => {
      expect(toKebabCase('inverse_volatility')).toBe('inverse-volatility');
      expect(toKebabCase('min_variance')).toBe('min-variance');
      expect(toKebabCase('risk_parity')).toBe('risk-parity');
    });

    it('should leave already kebab-case unchanged', () => {
      expect(toKebabCase('inverse-volatility')).toBe('inverse-volatility');
    });

    it('should leave single words unchanged', () => {
      expect(toKebabCase('equal')).toBe('equal');
      expect(toKebabCase('momentum')).toBe('momentum');
    });
  });

  describe('fromKebabCase', () => {
    it('should convert kebab-case to snake_case', () => {
      expect(fromKebabCase('inverse-volatility')).toBe('inverse_volatility');
      expect(fromKebabCase('min-variance')).toBe('min_variance');
      expect(fromKebabCase('risk-parity')).toBe('risk_parity');
    });

    it('should leave already snake_case unchanged', () => {
      expect(fromKebabCase('inverse_volatility')).toBe('inverse_volatility');
    });
  });

  describe('isKebabCaseKeyword', () => {
    it('should return true for DSL kebab-case keywords', () => {
      expect(isKebabCaseKeyword('inverse-volatility')).toBe(true);
      expect(isKebabCaseKeyword('min-variance')).toBe(true);
      expect(isKebabCaseKeyword('cross-above')).toBe(true);
      expect(isKebabCaseKeyword('macd-line')).toBe(true);
    });

    it('should return false for non-kebab keywords', () => {
      expect(isKebabCaseKeyword('equal')).toBe(false);
      expect(isKebabCaseKeyword('momentum')).toBe(false);
      expect(isKebabCaseKeyword('sma')).toBe(false);
    });
  });
});

describe('round-trip case conversion', () => {
  it('should round-trip weight methods', () => {
    const methods = ['inverse_volatility', 'min_variance', 'risk_parity'];

    for (const method of methods) {
      const kebab = toKebabCase(method);
      const snake = fromKebabCase(kebab);
      expect(snake).toBe(method);
    }
  });
});

describe('fromDSLString', () => {
  it('should parse simple strategy with assets', () => {
    const dsl = `(strategy "Simple Portfolio"
  :rebalance daily
  (weight :method equal
    (asset SPY)
    (asset BND)))`;

    const result = fromDSLString(dsl);
    expect(result).not.toBeNull();
    expect(result!.metadata.name).toBe('Simple Portfolio');
    expect(result!.metadata.timeframe).toBe('1D');

    // Verify tree structure
    const tree = result!.tree;
    expect(tree.rootId).toBeDefined();
    const root = tree.blocks[tree.rootId];
    expect(root.type).toBe('root');
    expect('childIds' in root && root.childIds.length).toBeGreaterThan(0);
  });

  it('should parse strategy with specified weights', () => {
    const dsl = `(strategy "60/40 Portfolio"
  :rebalance monthly
  (weight :method specified
    (asset VTI :weight 60)
    (asset BND :weight 40)))`;

    const result = fromDSLString(dsl);
    expect(result).not.toBeNull();
    expect(result!.metadata.name).toBe('60/40 Portfolio');
    expect(result!.metadata.timeframe).toBe('1M');

    // Find weight block
    const tree = result!.tree;
    const weightBlocks = Object.values(tree.blocks).filter(b => b.type === 'weight');
    expect(weightBlocks.length).toBe(1);

    const weightBlock = weightBlocks[0] as { allocations: Record<string, number> };
    const allocationValues = Object.values(weightBlock.allocations);
    expect(allocationValues).toContain(60);
    expect(allocationValues).toContain(40);
  });

  it('should parse strategy with nested groups', () => {
    const dsl = `(strategy "Grouped Portfolio"
  :rebalance weekly
  (weight :method equal
    (group "US Stocks"
      (asset SPY)
      (asset QQQ))
    (group "Bonds"
      (asset BND)
      (asset TLT))))`;

    const result = fromDSLString(dsl);
    expect(result).not.toBeNull();

    const tree = result!.tree;
    const groupBlocks = Object.values(tree.blocks).filter(b => b.type === 'group');
    expect(groupBlocks.length).toBe(2);

    const groupNames = groupBlocks.map(g => (g as { name: string }).name);
    expect(groupNames).toContain('US Stocks');
    expect(groupNames).toContain('Bonds');
  });

  it('should parse strategy with if/else condition', () => {
    const dsl = `(strategy "Conditional"
  :rebalance daily
  (if (< (rsi close 14) 30)
    (weight :method equal
      (asset SPY))
    (else
      (weight :method equal
        (asset BND)))))`;

    const result = fromDSLString(dsl);
    expect(result).not.toBeNull();

    const tree = result!.tree;
    const ifBlocks = Object.values(tree.blocks).filter(b => b.type === 'if');
    const elseBlocks = Object.values(tree.blocks).filter(b => b.type === 'else');

    expect(ifBlocks.length).toBe(1);
    expect(elseBlocks.length).toBe(1);

    const ifBlock = ifBlocks[0] as { condition: { comparator: string } };
    expect(ifBlock.condition.comparator).toBe('lt');
  });

  it('should order IF block before ELSE block in parent childIds', () => {
    const dsl = `(strategy "Ordering Test"
  :rebalance daily
  (weight :method equal
    (if (> close 100)
      (asset SPY)
      (else
        (asset BND)))))`;

    const result = fromDSLString(dsl);
    expect(result).not.toBeNull();

    const tree = result!.tree;
    const ifBlocks = Object.values(tree.blocks).filter(b => b.type === 'if');
    const elseBlocks = Object.values(tree.blocks).filter(b => b.type === 'else');

    expect(ifBlocks.length).toBe(1);
    expect(elseBlocks.length).toBe(1);

    // Find the weight block that contains the if/else
    const weightBlock = Object.values(tree.blocks).find(
      b => b.type === 'weight' && 'childIds' in b
    ) as { childIds: string[] } | undefined;
    expect(weightBlock).toBeDefined();

    // Verify IF comes before ELSE in childIds
    const ifIndex = weightBlock!.childIds.indexOf(ifBlocks[0]!.id);
    const elseIndex = weightBlock!.childIds.indexOf(elseBlocks[0]!.id);

    expect(ifIndex).toBeGreaterThanOrEqual(0);
    expect(elseIndex).toBeGreaterThanOrEqual(0);
    expect(ifIndex).toBeLessThan(elseIndex);
  });

  it('should parse strategy with filter block', () => {
    const dsl = `(strategy "Momentum Filter"
  :rebalance monthly
  (filter :by returns :select (top 5) :lookback 63
    (asset AAPL)
    (asset MSFT)
    (asset GOOGL)
    (asset AMZN)
    (asset META)))`;

    const result = fromDSLString(dsl);
    expect(result).not.toBeNull();

    const tree = result!.tree;
    const filterBlocks = Object.values(tree.blocks).filter(b => b.type === 'filter');
    expect(filterBlocks.length).toBe(1);

    const filter = filterBlocks[0] as { config: { selection: string; count: number } };
    expect(filter.config.selection).toBe('top');
    expect(filter.config.count).toBe(5);
  });

  it('preserves a filter universe nested in a weight (multi-asset-trend shape)', () => {
    // Regression: the DSL-text parser used to scrape only DIRECT (asset ...)
    // children, so a filter wrapping its assets in a (weight ...) parsed to an
    // EMPTY filter — which the backend rejected ("Select count (2) exceeds
    // available assets (0)"). The universe must survive as real children.
    const dsl = `(strategy "Nested Filter"
  :rebalance weekly
  (filter :by momentum :select (top 2) :lookback 60
    (weight :method equal
      (asset DBC)
      (asset PDBC)
      (asset DBA)
      (asset DBE)
      (asset DBB))))`;

    const result = fromDSLString(dsl);
    expect(result).not.toBeNull();
    const tree = result!.tree;

    const filterBlocks = Object.values(tree.blocks).filter((b) => b.type === 'filter');
    expect(filterBlocks.length).toBe(1);
    const filter = filterBlocks[0] as { childIds: string[] };
    expect(filter.childIds.length).toBeGreaterThan(0); // the nested weight is a real child
    expect(Object.values(tree.blocks).filter((b) => b.type === 'asset').length).toBe(5);

    // Round-trips to a NON-empty filter (previously it emitted a childless filter).
    const metadata: StrategyMetadata = {
      name: result!.metadata.name || 'Nested Filter',
      timeframe: result!.metadata.timeframe || '1W',
    };
    const dsl2 = toDSL(result!.tree, metadata);
    expect(dsl2).toContain('(asset DBC)');
    expect(dsl2).toContain('(asset DBB)');
  });

  it('should parse description from DSL', () => {
    const dsl = `(strategy "Documented Strategy"
  :rebalance daily
  :description "A well-documented strategy"
  (weight :method equal
    (asset SPY)))`;

    const result = fromDSLString(dsl);
    expect(result).not.toBeNull();
    expect(result!.metadata.description).toBe('A well-documented strategy');
  });

  it('should parse momentum weighting method', () => {
    const dsl = `(strategy "Momentum Strategy"
  :rebalance monthly
  (weight :method momentum :lookback 63
    (asset SPY)
    (asset QQQ)
    (asset IWM)))`;

    const result = fromDSLString(dsl);
    expect(result).not.toBeNull();

    const tree = result!.tree;
    const weightBlocks = Object.values(tree.blocks).filter(b => b.type === 'weight');
    expect(weightBlocks.length).toBe(1);

    const weight = weightBlocks[0] as { method: string; lookbackDays: number };
    expect(weight.method).toBe('momentum');
    expect(weight.lookbackDays).toBe(63);
  });

  it('should return null for invalid DSL', () => {
    expect(fromDSLString('not valid dsl')).toBeNull();
    expect(fromDSLString('(notastrategy)')).toBeNull();
    expect(fromDSLString('')).toBeNull();
  });
});

describe('toDSL', () => {
  it('should serialize a simple tree to DSL', () => {
    // Create a minimal tree
    const tree = {
      rootId: 'root',
      blocks: {
        root: {
          id: 'root',
          type: 'root' as const,
          parentId: null,
          name: 'Test Strategy',
          childIds: ['asset1'],
        },
        asset1: {
          id: 'asset1',
          type: 'asset' as const,
          parentId: 'root',
          symbol: 'SPY',
          exchange: 'NASDAQ',
          displayName: 'SPY',
        },
      },
    };

    const metadata: StrategyMetadata = {
      name: 'Test Strategy',
      timeframe: '1D',
    };

    const dsl = toDSL(tree, metadata);

    expect(dsl).toContain('(strategy "Test Strategy"');
    expect(dsl).toContain(':rebalance daily');
    expect(dsl).toContain('(asset SPY)');
  });
});

describe('round-trip DSL serialization', () => {
  it('should round-trip simple strategy', () => {
    const originalDsl = `(strategy "Simple Portfolio"
  :rebalance daily
  (weight :method equal
    (asset SPY)
    (asset BND)))`;

    const parsed = fromDSLString(originalDsl);
    expect(parsed).not.toBeNull();

    const metadata: StrategyMetadata = {
      name: parsed!.metadata.name || 'Simple Portfolio',
      timeframe: parsed!.metadata.timeframe || '1D',
    };

    const reserialized = toDSL(parsed!.tree, metadata);

    // Re-parse to verify structure is preserved
    const reparsed = fromDSLString(reserialized);
    expect(reparsed).not.toBeNull();
    expect(reparsed!.metadata.name).toBe(parsed!.metadata.name);

    // Check asset count is preserved
    const originalAssets = Object.values(parsed!.tree.blocks).filter(b => b.type === 'asset');
    const reparsedAssets = Object.values(reparsed!.tree.blocks).filter(b => b.type === 'asset');
    expect(reparsedAssets.length).toBe(originalAssets.length);
  });

  it('should round-trip strategy with groups', () => {
    const originalDsl = `(strategy "Grouped Strategy"
  :rebalance weekly
  (weight :method equal
    (group "Tech"
      (asset AAPL)
      (asset MSFT))
    (group "Finance"
      (asset JPM)
      (asset GS))))`;

    const parsed = fromDSLString(originalDsl);
    expect(parsed).not.toBeNull();

    const metadata: StrategyMetadata = {
      name: parsed!.metadata.name || 'Grouped Strategy',
      timeframe: parsed!.metadata.timeframe || '1W',
    };

    const reserialized = toDSL(parsed!.tree, metadata);
    const reparsed = fromDSLString(reserialized);
    expect(reparsed).not.toBeNull();

    // Verify groups are preserved
    const originalGroups = Object.values(parsed!.tree.blocks).filter(b => b.type === 'group');
    const reparsedGroups = Object.values(reparsed!.tree.blocks).filter(b => b.type === 'group');
    expect(reparsedGroups.length).toBe(originalGroups.length);
  });

  it('should round-trip strategy with conditions', () => {
    const originalDsl = `(strategy "Conditional"
  :rebalance daily
  (if (< (rsi close 14) 30)
    (weight :method equal
      (asset SPY))))`;

    const parsed = fromDSLString(originalDsl);
    expect(parsed).not.toBeNull();

    const metadata: StrategyMetadata = {
      name: parsed!.metadata.name || 'Conditional',
      timeframe: parsed!.metadata.timeframe || '1D',
    };

    const reserialized = toDSL(parsed!.tree, metadata);
    const reparsed = fromDSLString(reserialized);
    expect(reparsed).not.toBeNull();

    // Verify if block is preserved
    const originalIfBlocks = Object.values(parsed!.tree.blocks).filter(b => b.type === 'if');
    const reparsedIfBlocks = Object.values(reparsed!.tree.blocks).filter(b => b.type === 'if');
    expect(reparsedIfBlocks.length).toBe(originalIfBlocks.length);
  });
});

describe('validateTree', () => {
  it('should validate a valid tree', () => {
    const tree = {
      rootId: 'root',
      blocks: {
        root: {
          id: 'root',
          type: 'root' as const,
          parentId: null,
          name: 'Test',
          childIds: ['asset1'],
        },
        asset1: {
          id: 'asset1',
          type: 'asset' as const,
          parentId: 'root',
          symbol: 'SPY',
          exchange: 'NASDAQ',
          displayName: 'SPY',
        },
      },
    };

    const result = validateTree(tree);
    expect(result.valid).toBe(true);
    expect(result.errors.length).toBe(0);
  });

  it('should detect missing assets', () => {
    const tree = {
      rootId: 'root',
      blocks: {
        root: {
          id: 'root',
          type: 'root' as const,
          parentId: null,
          name: 'Test',
          childIds: [],
        },
      },
    };

    const result = validateTree(tree);
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.message.includes('at least one asset'))).toBe(true);
  });

  it('should detect orphan blocks', () => {
    const tree = {
      rootId: 'root',
      blocks: {
        root: {
          id: 'root',
          type: 'root' as const,
          parentId: null,
          name: 'Test',
          childIds: ['asset1'],
        },
        asset1: {
          id: 'asset1',
          type: 'asset' as const,
          parentId: 'root',
          symbol: 'SPY',
          exchange: 'NASDAQ',
          displayName: 'SPY',
        },
        orphan: {
          id: 'orphan',
          type: 'asset' as const,
          parentId: 'nonexistent',
          symbol: 'BND',
          exchange: 'NASDAQ',
          displayName: 'BND',
        },
      },
    };

    const result = validateTree(tree);
    // Updated message format from validation module
    expect(result.warnings.some(w => w.message.includes('Orphan') || w.message.includes('not reachable'))).toBe(true);
  });
});

describe('parseOperand - symbol extraction', () => {
  it('should extract symbol from (price BTC) syntax', () => {
    const dsl = `(strategy "Crypto Test"
  :rebalance daily
  (if (> (price BTC) 50000)
    (asset BTC :weight 100)))`;

    const result = fromDSLString(dsl);
    expect(result).not.toBeNull();

    const ifBlocks = Object.values(result!.tree.blocks).filter(b => b.type === 'if');
    expect(ifBlocks.length).toBe(1);

    const ifBlock = ifBlocks[0] as { condition: { left: { symbol: string } } };
    expect(ifBlock.condition.left.symbol).toBe('BTC');
  });

  it('should extract symbol from (sma ETH 50) syntax', () => {
    const dsl = `(strategy "MA Test"
  :rebalance daily
  (if (> (price ETH) (sma ETH 50))
    (asset ETH :weight 100)))`;

    const result = fromDSLString(dsl);
    expect(result).not.toBeNull();

    const ifBlocks = Object.values(result!.tree.blocks).filter(b => b.type === 'if');
    expect(ifBlocks.length).toBe(1);

    const ifBlock = ifBlocks[0] as {
      condition: {
        left: { symbol: string };
        right: { symbol: string; period: number };
      }
    };
    expect(ifBlock.condition.left.symbol).toBe('ETH');
    expect(ifBlock.condition.right.symbol).toBe('ETH');
    expect(ifBlock.condition.right.period).toBe(50);
  });

  it('should extract symbol from (rsi SPY 14) syntax', () => {
    const dsl = `(strategy "RSI Test"
  :rebalance daily
  (if (< (rsi SPY 14) 30)
    (asset SPY :weight 100)))`;

    const result = fromDSLString(dsl);
    expect(result).not.toBeNull();

    const ifBlocks = Object.values(result!.tree.blocks).filter(b => b.type === 'if');
    expect(ifBlocks.length).toBe(1);

    const ifBlock = ifBlocks[0] as {
      condition: { left: { symbol: string; period: number } }
    };
    expect(ifBlock.condition.left.symbol).toBe('SPY');
    expect(ifBlock.condition.left.period).toBe(14);
  });

  it('should handle (ema AAPL 20) syntax', () => {
    const dsl = `(strategy "EMA Test"
  :rebalance daily
  (if (> (sma AAPL 50) (ema AAPL 20))
    (asset AAPL :weight 100)))`;

    const result = fromDSLString(dsl);
    expect(result).not.toBeNull();

    const ifBlocks = Object.values(result!.tree.blocks).filter(b => b.type === 'if');
    expect(ifBlocks.length).toBe(1);

    const ifBlock = ifBlocks[0] as {
      condition: {
        left: { symbol: string; indicator: string };
        right: { symbol: string; indicator: string };
      }
    };
    expect(ifBlock.condition.left.symbol).toBe('AAPL');
    expect(ifBlock.condition.left.indicator).toBe('sma');
    expect(ifBlock.condition.right.symbol).toBe('AAPL');
    expect(ifBlock.condition.right.indicator).toBe('ema');
  });

  it('should handle crypto symbols like BTC, ETH, SOL', () => {
    const dsl = `(strategy "Crypto Trend"
  :rebalance daily
  (if (> (price BTC) (sma BTC 50))
    (weight :method equal
      (asset BTC)
      (asset ETH)
      (asset SOL))))`;

    const result = fromDSLString(dsl);
    expect(result).not.toBeNull();

    const ifBlocks = Object.values(result!.tree.blocks).filter(b => b.type === 'if');
    expect(ifBlocks.length).toBe(1);

    const ifBlock = ifBlocks[0] as {
      condition: {
        left: { symbol: string };
        right: { symbol: string };
      }
    };
    // Both sides should use BTC as the symbol
    expect(ifBlock.condition.left.symbol).toBe('BTC');
    expect(ifBlock.condition.right.symbol).toBe('BTC');
  });
});

describe('parseWeightExpr - group weight extraction', () => {
  it('should extract weight from groups with :weight parameter', () => {
    const dsl = `(strategy "Group Weights"
  :rebalance daily
  (weight :method specified
    (group "Tech" :weight 60
      (asset AAPL))
    (group "Finance" :weight 40
      (asset JPM))))`;

    const result = fromDSLString(dsl);
    expect(result).not.toBeNull();

    const weightBlocks = Object.values(result!.tree.blocks).filter(b => b.type === 'weight');
    expect(weightBlocks.length).toBe(1);

    const weightBlock = weightBlocks[0] as { allocations: Record<string, number>; childIds: string[] };
    const groupBlocks = Object.values(result!.tree.blocks).filter(b => b.type === 'group');
    expect(groupBlocks.length).toBe(2);

    // Both groups should have weights in the parent weight block's allocations
    const techGroup = groupBlocks.find(g => (g as { name: string }).name === 'Tech');
    const financeGroup = groupBlocks.find(g => (g as { name: string }).name === 'Finance');

    expect(techGroup).toBeDefined();
    expect(financeGroup).toBeDefined();

    // Weights should be extracted into allocations
    expect(weightBlock.allocations[techGroup!.id]).toBe(60);
    expect(weightBlock.allocations[financeGroup!.id]).toBe(40);
  });
});

// fromDSL — compiled AST → block tree. Fixtures mirror libs/dsl `to_json` (verified against the seeded demo strategies).

// Helpers to pull typed blocks out of the produced map.
function blocksOfType(tree: { blocks: Record<string, Block> }, type: Block['type']): Block[] {
  return Object.values(tree.blocks).filter((b) => b.type === type);
}

describe('fromDSL (compiled AST → tree)', () => {
  it('uses a saved ui_state block tree verbatim when present', () => {
    const uiState = {
      rootId: 'r1',
      blocks: {
        r1: { id: 'r1', type: 'root', parentId: null, name: 'Saved', childIds: [] },
      },
    };
    const tree = fromDSL({ type: 'strategy', name: 'Ignored', children: [] }, uiState);
    expect(tree.rootId).toBe('r1');
    expect(tree.blocks.r1).toBeDefined();
  });

  it('parses a specified-weight tree of weighted groups (All-Weather shape)', () => {
    const compiled = {
      name: 'All-Weather Portfolio',
      type: 'strategy',
      children: [
        {
          type: 'weight',
          method: 'specified',
          children: [
            {
              name: 'Equities',
              type: 'group',
              weight: 30,
              children: [
                {
                  type: 'weight',
                  method: 'equal',
                  children: [
                    { type: 'asset', symbol: 'VTI' },
                    { type: 'asset', symbol: 'VEA' },
                    { type: 'asset', symbol: 'VWO' },
                  ],
                },
              ],
            },
            {
              name: 'Long Bonds',
              type: 'group',
              weight: 40,
              children: [
                {
                  type: 'weight',
                  method: 'specified',
                  children: [
                    { type: 'asset', symbol: 'TLT', weight: 60 },
                    { type: 'asset', symbol: 'EDV', weight: 40 },
                  ],
                },
              ],
            },
          ],
        },
      ],
    };

    const tree = fromDSL(compiled);

    // Root
    const root = tree.blocks[tree.rootId];
    expect(root.type).toBe('root');
    expect((root as { name: string }).name).toBe('All-Weather Portfolio');

    // Top-level specified weight with the two groups recorded as allocations
    const topWeight = blocksOfType(tree, 'weight').find(
      (b) => (b as { method: string }).method === 'specified' && (b as { parentId: string }).parentId === tree.rootId
    ) as { id: string; allocations: Record<string, number>; childIds: string[] } | undefined;
    expect(topWeight).toBeDefined();

    const groups = blocksOfType(tree, 'group');
    expect(groups.map((g) => (g as { name: string }).name).sort()).toEqual(['Equities', 'Long Bonds']);

    const equities = groups.find((g) => (g as { name: string }).name === 'Equities')!;
    const longBonds = groups.find((g) => (g as { name: string }).name === 'Long Bonds')!;
    expect(topWeight!.allocations[equities.id]).toBe(30);
    expect(topWeight!.allocations[longBonds.id]).toBe(40);

    // Assets are present (never dropped)
    const symbols = blocksOfType(tree, 'asset').map((a) => (a as { symbol: string }).symbol).sort();
    expect(symbols).toEqual(['EDV', 'TLT', 'VEA', 'VTI', 'VWO']);

    // Nested specified sub-weight inside "Long Bonds" keeps TLT=60 / EDV=40
    const nestedSpecified = blocksOfType(tree, 'weight').find(
      (b) => (b as { method: string }).method === 'specified' && b.id !== topWeight!.id
    ) as { allocations: Record<string, number> };
    const allocValues = Object.values(nestedSpecified.allocations).sort((a, b) => a - b);
    expect(allocValues).toEqual([40, 60]);
  });

  it('round-trips a weighted-group tree back to DSL without corrupting the split', () => {
    const compiled = {
      name: 'Split',
      type: 'strategy',
      children: [
        {
          type: 'weight',
          method: 'specified',
          children: [
            {
              name: 'Stocks',
              type: 'group',
              weight: 70,
              children: [{ type: 'weight', method: 'equal', children: [{ type: 'asset', symbol: 'VTI' }] }],
            },
            {
              name: 'Bonds',
              type: 'group',
              weight: 30,
              children: [{ type: 'weight', method: 'equal', children: [{ type: 'asset', symbol: 'BND' }] }],
            },
          ],
        },
      ],
    };

    const tree = fromDSL(compiled);
    const dsl = toDSL(tree, { name: 'Split', timeframe: '3M' });

    // Method preserved (NOT downgraded to equal) and group weights emitted.
    expect(dsl).toContain(':method specified');
    expect(dsl).toContain('(group "Stocks" :weight 70');
    expect(dsl).toContain('(group "Bonds" :weight 30');
  });

  it('parses a filter block (Momentum Sectors shape)', () => {
    const compiled = {
      name: 'Momentum Sectors',
      type: 'strategy',
      children: [
        {
          by: 'momentum',
          type: 'filter',
          lookback: 90,
          select_count: 3,
          select_direction: 'top',
          children: [
            {
              type: 'weight',
              method: 'equal',
              children: [
                { type: 'asset', symbol: 'XLK' },
                { type: 'asset', symbol: 'XLF' },
                { type: 'asset', symbol: 'XLI' },
              ],
            },
          ],
        },
      ],
    };

    const tree = fromDSL(compiled);
    const filters = blocksOfType(tree, 'filter');
    expect(filters.length).toBe(1);
    const filter = filters[0] as { config: { sortBy: string; selection: string; count: number; period: string }; childIds: string[] };
    expect(filter.config.sortBy).toBe('momentum');
    expect(filter.config.selection).toBe('top');
    expect(filter.config.count).toBe(3);
    expect(filter.config.period).toBe('6m'); // lookback 90 → 6m bucket
    // Its universe (a nested weight of assets) is preserved as real children
    expect(filter.childIds.length).toBe(1);
    expect(blocksOfType(tree, 'asset').length).toBe(3);
  });

  it('parses an if/else block with an indicator condition, else as a sibling', () => {
    const compiled = {
      name: 'Golden Cross',
      type: 'strategy',
      children: [
        {
          type: 'if',
          condition: {
            type: 'comparison',
            operator: '>',
            left: { type: 'indicator', name: 'sma', symbol: 'SPY', params: [50] },
            right: { type: 'indicator', name: 'sma', symbol: 'SPY', params: [200] },
          },
          then: { type: 'weight', method: 'equal', children: [{ type: 'asset', symbol: 'SPY' }] },
          else_block: { type: 'weight', method: 'equal', children: [{ type: 'asset', symbol: 'BND' }] },
        },
      ],
    };

    const tree = fromDSL(compiled);
    const ifBlocks = blocksOfType(tree, 'if');
    const elseBlocks = blocksOfType(tree, 'else');
    expect(ifBlocks.length).toBe(1);
    expect(elseBlocks.length).toBe(1);

    const ifBlock = ifBlocks[0] as {
      id: string;
      parentId: string;
      childIds: string[];
      condition: { comparator: string; left: { indicator: string; symbol: string; period: number }; right: { period: number } };
    };
    const elseBlock = elseBlocks[0] as { parentId: string; ifBlockId: string };

    // Condition mapped correctly
    expect(ifBlock.condition.comparator).toBe('gt');
    expect(ifBlock.condition.left.indicator).toBe('sma');
    expect(ifBlock.condition.left.symbol).toBe('SPY');
    expect(ifBlock.condition.left.period).toBe(50);
    expect(ifBlock.condition.right.period).toBe(200);

    // ELSE is a sibling (same parent) that references the IF
    expect(elseBlock.parentId).toBe(ifBlock.parentId);
    expect(elseBlock.ifBlockId).toBe(ifBlock.id);

    // IF and ELSE both present in the root's children, IF before ELSE
    const root = tree.blocks[tree.rootId] as { childIds: string[] };
    expect(root.childIds).toContain(ifBlock.id);
    expect(root.childIds.indexOf(ifBlock.id)).toBeLessThan(root.childIds.indexOf(elseBlocks[0]!.id));
  });

  it('maps a crossover condition to cross_above/cross_below', () => {
    const compiled = {
      name: 'X',
      type: 'strategy',
      children: [
        {
          type: 'if',
          condition: {
            type: 'crossover',
            direction: 'above',
            fast: { type: 'indicator', name: 'ema', symbol: 'QQQ', params: [12] },
            slow: { type: 'indicator', name: 'ema', symbol: 'QQQ', params: [26] },
          },
          then: { type: 'weight', method: 'equal', children: [{ type: 'asset', symbol: 'QQQ' }] },
        },
      ],
    };
    const tree = fromDSL(compiled);
    const ifBlock = blocksOfType(tree, 'if')[0] as { condition: { comparator: string } };
    expect(ifBlock.condition.comparator).toBe('cross_above');
  });

  it('degrades an unknown node instead of dropping it (never empty for non-empty AST)', () => {
    const compiled = {
      name: 'Weird',
      type: 'strategy',
      children: [
        { type: 'mystery', name: 'Bucket', children: [{ type: 'asset', symbol: 'SPY' }] },
        { type: 'other-leaf' },
      ],
    };
    const tree = fromDSL(compiled);
    const root = tree.blocks[tree.rootId] as { childIds: string[] };
    // Both nodes survive: container → group, leaf → asset
    expect(root.childIds.length).toBe(2);
    expect(blocksOfType(tree, 'group').length).toBe(1);
    // SPY asset inside the degraded group is preserved
    expect(blocksOfType(tree, 'asset').some((a) => (a as { symbol: string }).symbol === 'SPY')).toBe(true);
  });

  it('falls back to flat asset blocks for a legacy { name, symbols } config', () => {
    const tree = fromDSL({ name: 'Legacy', symbols: ['AAPL', 'MSFT'] });
    const root = tree.blocks[tree.rootId] as { name: string; childIds: string[] };
    expect(root.name).toBe('Legacy');
    expect(root.childIds.length).toBe(2);
    expect(blocksOfType(tree, 'asset').map((a) => (a as { symbol: string }).symbol).sort()).toEqual(['AAPL', 'MSFT']);
  });

  it('produces a valid tree for an empty compiled config', () => {
    const tree = fromDSL({});
    expect(tree.blocks[tree.rootId].type).toBe('root');
  });
});
