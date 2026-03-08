/* eslint-disable @typescript-eslint/no-non-null-assertion */
import { describe, it, expect } from 'vitest';

import {
  tokenizeWithPositions,
  toKebabCase,
  fromKebabCase,
  isKebabCaseKeyword,
  fromDSLString,
  toDSL,
  validateTree,
  type StrategyMetadata,
} from '../strategy-serializer';

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
