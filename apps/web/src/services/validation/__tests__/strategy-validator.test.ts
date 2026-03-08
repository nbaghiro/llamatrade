import { describe, it, expect } from 'vitest';

import type { StrategyTree } from '../../../types/strategy-builder';
import {
  validateStrategy,
  VALIDATION_RULES,
  blockHasError,
  blockHasWarning,
  getBlockIssues,
} from '../strategy-validator';

// Helper to create a minimal valid tree
function createBaseTree(): StrategyTree {
  const rootId = 'root-1';
  const weightId = 'weight-1';
  const assetId = 'asset-1';

  return {
    rootId,
    blocks: {
      [rootId]: {
        id: rootId,
        type: 'root',
        parentId: null,
        name: 'Test Strategy',
        childIds: [weightId],
      },
      [weightId]: {
        id: weightId,
        type: 'weight',
        parentId: rootId,
        method: 'equal',
        allocations: {},
        childIds: [assetId],
      },
      [assetId]: {
        id: assetId,
        type: 'asset',
        parentId: weightId,
        symbol: 'SPY',
        exchange: 'NYSE',
        displayName: 'S&P 500 ETF',
      },
    },
  };
}

describe('validateStrategy', () => {
  it('should validate a minimal valid tree', () => {
    const tree = createBaseTree();
    const result = validateStrategy(tree);

    expect(result.valid).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  it('should return all defined validation rules', () => {
    // Ensure rules are defined
    expect(VALIDATION_RULES.length).toBeGreaterThan(0);
    expect(VALIDATION_RULES.every(r => r.id && r.name && r.validate)).toBe(true);
  });
});

describe('structure.has-assets rule', () => {
  it('should error when strategy has no assets', () => {
    const tree: StrategyTree = {
      rootId: 'root-1',
      blocks: {
        'root-1': {
          id: 'root-1',
          type: 'root',
          parentId: null,
          name: 'Empty Strategy',
          childIds: [],
        },
      },
    };

    const result = validateStrategy(tree);
    expect(result.valid).toBe(false);
    expect(result.errors.some(e => e.ruleId === 'structure.has-assets')).toBe(true);
  });

  it('should pass when strategy has at least one asset', () => {
    const tree = createBaseTree();
    const result = validateStrategy(tree);

    expect(result.errors.some(e => e.ruleId === 'structure.has-assets')).toBe(false);
  });
});

describe('weight.sum rule', () => {
  it('should warn when specified weights do not sum to 100', () => {
    const tree: StrategyTree = {
      rootId: 'root-1',
      blocks: {
        'root-1': {
          id: 'root-1',
          type: 'root',
          parentId: null,
          name: 'Test',
          childIds: ['weight-1'],
        },
        'weight-1': {
          id: 'weight-1',
          type: 'weight',
          parentId: 'root-1',
          method: 'specified',
          allocations: {
            'asset-1': 60,
            'asset-2': 30, // Sum = 90, not 100
          },
          childIds: ['asset-1', 'asset-2'],
        },
        'asset-1': {
          id: 'asset-1',
          type: 'asset',
          parentId: 'weight-1',
          symbol: 'SPY',
          exchange: 'NYSE',
          displayName: 'SPY',
        },
        'asset-2': {
          id: 'asset-2',
          type: 'asset',
          parentId: 'weight-1',
          symbol: 'BND',
          exchange: 'NYSE',
          displayName: 'BND',
        },
      },
    };

    const result = validateStrategy(tree);
    // weight.sum is now a warning (to support patterns like pairs trading, core-satellite)
    expect(result.warnings.some(w => w.ruleId === 'weight.sum')).toBe(true);
    expect(result.warnings.find(w => w.ruleId === 'weight.sum')?.message).toContain('90');
  });

  it('should pass when specified weights sum to 100', () => {
    const tree: StrategyTree = {
      rootId: 'root-1',
      blocks: {
        'root-1': {
          id: 'root-1',
          type: 'root',
          parentId: null,
          name: 'Test',
          childIds: ['weight-1'],
        },
        'weight-1': {
          id: 'weight-1',
          type: 'weight',
          parentId: 'root-1',
          method: 'specified',
          allocations: {
            'asset-1': 60,
            'asset-2': 40,
          },
          childIds: ['asset-1', 'asset-2'],
        },
        'asset-1': {
          id: 'asset-1',
          type: 'asset',
          parentId: 'weight-1',
          symbol: 'SPY',
          exchange: 'NYSE',
          displayName: 'SPY',
        },
        'asset-2': {
          id: 'asset-2',
          type: 'asset',
          parentId: 'weight-1',
          symbol: 'BND',
          exchange: 'NYSE',
          displayName: 'BND',
        },
      },
    };

    const result = validateStrategy(tree);
    expect(result.errors.some(e => e.ruleId === 'weight.sum')).toBe(false);
  });

  it('should not apply to equal weight method', () => {
    const tree = createBaseTree();
    const result = validateStrategy(tree);

    expect(result.errors.some(e => e.ruleId === 'weight.sum')).toBe(false);
  });
});

describe('weight.positive rule', () => {
  it('should warn when weight is zero or negative', () => {
    const tree: StrategyTree = {
      rootId: 'root-1',
      blocks: {
        'root-1': {
          id: 'root-1',
          type: 'root',
          parentId: null,
          name: 'Test',
          childIds: ['weight-1'],
        },
        'weight-1': {
          id: 'weight-1',
          type: 'weight',
          parentId: 'root-1',
          method: 'specified',
          allocations: {
            'asset-1': 0, // Zero weight
            'asset-2': 100,
          },
          childIds: ['asset-1', 'asset-2'],
        },
        'asset-1': {
          id: 'asset-1',
          type: 'asset',
          parentId: 'weight-1',
          symbol: 'SPY',
          exchange: 'NYSE',
          displayName: 'SPY',
        },
        'asset-2': {
          id: 'asset-2',
          type: 'asset',
          parentId: 'weight-1',
          symbol: 'BND',
          exchange: 'NYSE',
          displayName: 'BND',
        },
      },
    };

    const result = validateStrategy(tree);
    // weight.positive is now a warning (to support pairs trading with negative weights for shorts)
    expect(result.warnings.some(w => w.ruleId === 'weight.positive')).toBe(true);
  });
});

describe('weight.specified-missing rule', () => {
  it('should error when specified method child has no weight', () => {
    const tree: StrategyTree = {
      rootId: 'root-1',
      blocks: {
        'root-1': {
          id: 'root-1',
          type: 'root',
          parentId: null,
          name: 'Test',
          childIds: ['weight-1'],
        },
        'weight-1': {
          id: 'weight-1',
          type: 'weight',
          parentId: 'root-1',
          method: 'specified',
          allocations: {
            'asset-1': 60,
            // asset-2 missing from allocations
          },
          childIds: ['asset-1', 'asset-2'],
        },
        'asset-1': {
          id: 'asset-1',
          type: 'asset',
          parentId: 'weight-1',
          symbol: 'SPY',
          exchange: 'NYSE',
          displayName: 'SPY',
        },
        'asset-2': {
          id: 'asset-2',
          type: 'asset',
          parentId: 'weight-1',
          symbol: 'BND',
          exchange: 'NYSE',
          displayName: 'BND',
        },
      },
    };

    const result = validateStrategy(tree);
    expect(result.errors.some(e => e.ruleId === 'weight.specified-missing')).toBe(true);
    expect(result.errors.find(e => e.ruleId === 'weight.specified-missing')?.message).toContain('BND');
  });
});

describe('condition.required rule', () => {
  it('should error when IF block has no condition', () => {
    const tree: StrategyTree = {
      rootId: 'root-1',
      blocks: {
        'root-1': {
          id: 'root-1',
          type: 'root',
          parentId: null,
          name: 'Test',
          childIds: ['if-1'],
        },
        'if-1': {
          id: 'if-1',
          type: 'if',
          parentId: 'root-1',
          condition: undefined as unknown as never, // No condition
          conditionText: '',
          childIds: ['asset-1'],
        },
        'asset-1': {
          id: 'asset-1',
          type: 'asset',
          parentId: 'if-1',
          symbol: 'SPY',
          exchange: 'NYSE',
          displayName: 'SPY',
        },
      },
    };

    const result = validateStrategy(tree);
    expect(result.errors.some(e => e.ruleId === 'condition.required')).toBe(true);
  });
});

describe('structure.no-orphans rule', () => {
  it('should warn about orphan blocks not connected to root', () => {
    const tree: StrategyTree = {
      rootId: 'root-1',
      blocks: {
        'root-1': {
          id: 'root-1',
          type: 'root',
          parentId: null,
          name: 'Test',
          childIds: ['asset-1'],
        },
        'asset-1': {
          id: 'asset-1',
          type: 'asset',
          parentId: 'root-1',
          symbol: 'SPY',
          exchange: 'NYSE',
          displayName: 'SPY',
        },
        'orphan': {
          id: 'orphan',
          type: 'asset',
          parentId: 'nonexistent', // Not connected
          symbol: 'BND',
          exchange: 'NYSE',
          displayName: 'BND',
        },
      },
    };

    const result = validateStrategy(tree);
    expect(result.warnings.some(w => w.ruleId === 'structure.no-orphans')).toBe(true);
    expect(result.warnings.find(w => w.ruleId === 'structure.no-orphans')?.blockId).toBe('orphan');
  });
});

describe('structure.group-not-empty rule', () => {
  it('should warn when group has no children', () => {
    const tree: StrategyTree = {
      rootId: 'root-1',
      blocks: {
        'root-1': {
          id: 'root-1',
          type: 'root',
          parentId: null,
          name: 'Test',
          childIds: ['group-1', 'asset-1'],
        },
        'group-1': {
          id: 'group-1',
          type: 'group',
          parentId: 'root-1',
          name: 'Empty Group',
          childIds: [], // Empty
        },
        'asset-1': {
          id: 'asset-1',
          type: 'asset',
          parentId: 'root-1',
          symbol: 'SPY',
          exchange: 'NYSE',
          displayName: 'SPY',
        },
      },
    };

    const result = validateStrategy(tree);
    expect(result.warnings.some(w => w.ruleId === 'structure.group-not-empty')).toBe(true);
  });
});

describe('filter.count-positive rule', () => {
  it('should error when filter count is less than 1', () => {
    const tree: StrategyTree = {
      rootId: 'root-1',
      blocks: {
        'root-1': {
          id: 'root-1',
          type: 'root',
          parentId: null,
          name: 'Test',
          childIds: ['filter-1'],
        },
        'filter-1': {
          id: 'filter-1',
          type: 'filter',
          parentId: 'root-1',
          config: {
            selection: 'top',
            count: 0, // Invalid
            universe: 'sp500',
            sortBy: 'momentum',
            period: '12m',
          },
          displayText: 'Top 0',
          childIds: ['asset-1'],
        },
        'asset-1': {
          id: 'asset-1',
          type: 'asset',
          parentId: 'filter-1',
          symbol: 'SPY',
          exchange: 'NYSE',
          displayName: 'SPY',
        },
      },
    };

    const result = validateStrategy(tree);
    expect(result.errors.some(e => e.ruleId === 'filter.count-positive')).toBe(true);
  });
});

describe('utility functions', () => {
  it('blockHasError should return true for blocks with errors', () => {
    // Test with IF block missing condition (which is an error, not a warning)
    const tree: StrategyTree = {
      rootId: 'root-1',
      blocks: {
        'root-1': {
          id: 'root-1',
          type: 'root',
          parentId: null,
          name: 'Test',
          childIds: ['if-1'],
        },
        'if-1': {
          id: 'if-1',
          type: 'if',
          parentId: 'root-1',
          condition: undefined as unknown as never, // Missing condition = error
          conditionText: '',
          childIds: ['asset-1'],
        },
        'asset-1': {
          id: 'asset-1',
          type: 'asset',
          parentId: 'if-1',
          symbol: 'SPY',
          exchange: 'NYSE',
          displayName: 'SPY',
        },
      },
    };

    const result = validateStrategy(tree);
    expect(blockHasError(result, 'if-1')).toBe(true);
    expect(blockHasError(result, 'asset-1')).toBe(false);
  });

  it('blockHasWarning should return true for blocks with warnings', () => {
    const tree: StrategyTree = {
      rootId: 'root-1',
      blocks: {
        'root-1': {
          id: 'root-1',
          type: 'root',
          parentId: null,
          name: 'Test',
          childIds: ['weight-1'],
        },
        'weight-1': {
          id: 'weight-1',
          type: 'weight',
          parentId: 'root-1',
          method: 'specified',
          allocations: { 'asset-1': 50 }, // Sum != 100 = warning
          childIds: ['asset-1'],
        },
        'asset-1': {
          id: 'asset-1',
          type: 'asset',
          parentId: 'weight-1',
          symbol: 'SPY',
          exchange: 'NYSE',
          displayName: 'SPY',
        },
      },
    };

    const result = validateStrategy(tree);
    expect(blockHasWarning(result, 'weight-1')).toBe(true);
    expect(blockHasWarning(result, 'asset-1')).toBe(false);
  });

  it('getBlockIssues should return issues for a specific block', () => {
    const tree: StrategyTree = {
      rootId: 'root-1',
      blocks: {
        'root-1': {
          id: 'root-1',
          type: 'root',
          parentId: null,
          name: 'Test',
          childIds: ['weight-1'],
        },
        'weight-1': {
          id: 'weight-1',
          type: 'weight',
          parentId: 'root-1',
          method: 'specified',
          allocations: { 'asset-1': 50 },
          childIds: ['asset-1'],
        },
        'asset-1': {
          id: 'asset-1',
          type: 'asset',
          parentId: 'weight-1',
          symbol: 'SPY',
          exchange: 'NYSE',
          displayName: 'SPY',
        },
      },
    };

    const result = validateStrategy(tree);
    const weightIssues = getBlockIssues(result, 'weight-1');
    expect(weightIssues.length).toBeGreaterThan(0);
    expect(weightIssues.every(i => i.blockId === 'weight-1')).toBe(true);
  });
});
