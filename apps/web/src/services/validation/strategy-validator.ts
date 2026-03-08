/**
 * Strategy Validation Module
 *
 * Comprehensive validation for strategy block trees.
 * Rules are designed to match backend validator.py for consistency.
 */

import type {
  Block,
  BlockId,
  StrategyTree,
} from '../../types/strategy-builder';
import {
  hasChildren,
  isAssetBlock,
  isWeightBlock,
  isIfBlock,
  isElseBlock,
  isGroupBlock,
  isFilterBlock,
} from '../../types/strategy-builder';

// ============================================
// Validation Types
// ============================================

export type ValidationSeverity = 'error' | 'warning';

export interface ValidationIssue {
  /** Unique rule identifier */
  ruleId: string;
  /** Block ID where the issue was found */
  blockId?: BlockId;
  /** Field name within the block */
  field?: string;
  /** Human-readable error message */
  message: string;
  /** Error or warning */
  severity: ValidationSeverity;
  /** Suggested fixes */
  suggestions?: string[];
}

export interface ValidationResult {
  /** True if no errors (warnings don't affect validity) */
  valid: boolean;
  /** All validation issues found */
  issues: ValidationIssue[];
  /** Convenience accessors */
  errors: ValidationIssue[];
  warnings: ValidationIssue[];
}

// ============================================
// Validation Rule Interface
// ============================================

export interface ValidationRule {
  /** Unique rule ID for grouping and filtering */
  id: string;
  /** Human-readable name */
  name: string;
  /** Description of what this rule checks */
  description: string;
  /** Error or warning */
  severity: ValidationSeverity;
  /** The validation function */
  validate: (tree: StrategyTree) => ValidationIssue[];
}

// ============================================
// Helper Functions
// ============================================

/**
 * Get all blocks of a specific type
 */
function getBlocksByType<T extends Block>(
  tree: StrategyTree,
  typeGuard: (block: Block) => block is T
): T[] {
  return Object.values(tree.blocks).filter(typeGuard);
}

/**
 * Get direct children of a block
 */
function getChildren(tree: StrategyTree, blockId: BlockId): Block[] {
  const block = tree.blocks[blockId];
  if (!block || !hasChildren(block)) return [];
  return block.childIds
    .map((id) => tree.blocks[id])
    .filter((b): b is Block => b !== undefined);
}

/**
 * Get all reachable block IDs from a starting block
 */
function getReachableIds(tree: StrategyTree, startId: BlockId): Set<BlockId> {
  const reachable = new Set<BlockId>();
  const queue: BlockId[] = [startId];

  while (queue.length > 0) {
    const id = queue.shift();
    if (id === undefined) break;
    if (reachable.has(id)) continue;
    reachable.add(id);

    const block = tree.blocks[id];
    if (block && hasChildren(block)) {
      queue.push(...block.childIds);
    }
  }

  return reachable;
}

/**
 * Count assets in a subtree (including nested in groups, weights, etc.)
 */
function countAssetsInSubtree(tree: StrategyTree, blockId: BlockId): number {
  const block = tree.blocks[blockId];
  if (!block) return 0;

  if (isAssetBlock(block)) return 1;

  if (hasChildren(block)) {
    return block.childIds.reduce(
      (count, childId) => count + countAssetsInSubtree(tree, childId),
      0
    );
  }

  return 0;
}

// ============================================
// Helper: Check if block is a container (handles its own allocation)
// ============================================

/**
 * Check if a block is a container that handles its own allocation logic.
 * Groups, weights, filters, and if blocks are containers.
 */
function isContainerBlock(block: Block): boolean {
  return isGroupBlock(block) || isWeightBlock(block) || isFilterBlock(block) || isIfBlock(block) || isElseBlock(block);
}

/**
 * Check if a weight block only has container children (no direct assets).
 * This means the weight allocation is distributed through nested structures.
 */
function hasOnlyContainerChildren(tree: StrategyTree, weightBlockId: BlockId): boolean {
  const weight = tree.blocks[weightBlockId];
  if (!weight || !isWeightBlock(weight)) return false;

  for (const childId of weight.childIds) {
    const child = tree.blocks[childId];
    if (!child) continue;
    // If any child is a direct asset, return false
    if (isAssetBlock(child)) return false;
  }

  return weight.childIds.length > 0;
}

// ============================================
// Validation Rules
// ============================================

/**
 * Rule: Strategy must have at least one asset
 *
 * Note: Filter blocks with a universe (sp500, nasdaq100, etc.) are considered
 * to have "potential" assets even if childIds is empty.
 */
const hasAssetsRule: ValidationRule = {
  id: 'structure.has-assets',
  name: 'Has Assets',
  description: 'Strategy must contain at least one asset',
  severity: 'error',
  validate: (tree) => {
    // Check for direct assets
    const assets = getBlocksByType(tree, isAssetBlock);
    if (assets.length > 0) {
      return [];
    }

    // Check for filter blocks with non-custom universe (dynamic asset selection)
    const filters = getBlocksByType(tree, isFilterBlock);
    const hasDynamicFilter = filters.some(f => f.config.universe !== 'custom');
    if (hasDynamicFilter) {
      return []; // Filter with universe provides assets dynamically
    }

    return [{
      ruleId: 'structure.has-assets',
      message: 'Strategy must contain at least one asset',
      severity: 'error',
      suggestions: ['Add an asset by dragging a ticker from the search panel'],
    }];
  },
};

/**
 * Rule: Weight allocations should sum to 100% for specified method
 *
 * Note: This rule only applies when the weight block has direct assets as children.
 * If all children are containers (groups, nested weights, filters, if blocks),
 * the allocation is handled by the nested structures.
 *
 * This is a warning because some valid strategies use relative weights within
 * nested structures, where the sum doesn't need to be exactly 100%.
 */
const weightSumRule: ValidationRule = {
  id: 'weight.sum',
  name: 'Weight Sum',
  description: 'Specified weight allocations should sum to 100%',
  severity: 'warning',
  validate: (tree) => {
    const issues: ValidationIssue[] = [];
    const weightBlocks = getBlocksByType(tree, isWeightBlock);

    for (const weight of weightBlocks) {
      if (weight.method !== 'specified') continue;
      if (weight.childIds.length === 0) continue;

      // Skip if all children are containers - allocation handled by nested structures
      if (hasOnlyContainerChildren(tree, weight.id)) continue;

      // Count only direct asset children for weight sum validation
      const directAssetChildren = weight.childIds.filter(id => {
        const child = tree.blocks[id];
        return child && isAssetBlock(child);
      });

      // If no direct assets, skip this weight block
      if (directAssetChildren.length === 0) continue;

      // Sum allocations for direct assets only
      let total = 0;
      for (const childId of directAssetChildren) {
        total += weight.allocations[childId] || 0;
      }

      // Allow small tolerance for rounding
      if (Math.abs(total - 100) > 0.01) {
        issues.push({
          ruleId: 'weight.sum',
          blockId: weight.id,
          field: 'allocations',
          message: `Weight allocations sum to ${total.toFixed(1)}%, should be 100%`,
          severity: 'warning',
          suggestions: total < 100
            ? [`Add ${(100 - total).toFixed(1)}% to reach 100%`]
            : [`Remove ${(total - 100).toFixed(1)}% to reach 100%`],
        });
      }
    }

    return issues;
  },
};

/**
 * Rule: All weights should be positive (> 0)
 *
 * Note: Some strategies (like pairs trading) may use negative weights
 * for short positions, so this is a warning rather than an error.
 */
const weightsPositiveRule: ValidationRule = {
  id: 'weight.positive',
  name: 'Positive Weights',
  description: 'Weight allocations should be greater than 0',
  severity: 'warning',
  validate: (tree) => {
    const issues: ValidationIssue[] = [];
    const weightBlocks = getBlocksByType(tree, isWeightBlock);

    for (const weight of weightBlocks) {
      if (weight.method !== 'specified') continue;

      for (const [childId, allocation] of Object.entries(weight.allocations)) {
        if (allocation <= 0) {
          const child = tree.blocks[childId];
          const childName = child
            ? isAssetBlock(child)
              ? child.symbol
              : isGroupBlock(child)
                ? child.name
                : 'block'
            : 'unknown';
          issues.push({
            ruleId: 'weight.positive',
            blockId: weight.id,
            field: `allocations.${childId}`,
            message: `Weight for "${childName}" is ${allocation}% (negative weights are typically for short positions)`,
            severity: 'warning',
            suggestions: ['Set a positive weight for long positions, or keep negative for short positions'],
          });
        }
      }
    }

    return issues;
  },
};

/**
 * Rule: Specified method requires all direct asset children to have weights
 *
 * Note: Container children (groups, nested weights, filters, if blocks) handle
 * their own allocation logic and don't require explicit weights in the parent.
 */
const specifiedHasWeightsRule: ValidationRule = {
  id: 'weight.specified-missing',
  name: 'Specified Weights Required',
  description: 'All asset children of a specified weight block must have weights assigned',
  severity: 'error',
  validate: (tree) => {
    const issues: ValidationIssue[] = [];
    const weightBlocks = getBlocksByType(tree, isWeightBlock);

    for (const weight of weightBlocks) {
      if (weight.method !== 'specified') continue;

      for (const childId of weight.childIds) {
        const child = tree.blocks[childId];
        if (!child) continue;

        // Skip container blocks - they handle their own allocation
        if (isContainerBlock(child)) continue;

        // Only require weights for direct asset children
        if (!isAssetBlock(child)) continue;

        if (!(childId in weight.allocations) || weight.allocations[childId] === 0) {
          issues.push({
            ruleId: 'weight.specified-missing',
            blockId: weight.id,
            field: `allocations.${childId}`,
            message: `"${child.symbol}" needs a weight allocation`,
            severity: 'error',
            suggestions: ['Assign a percentage weight to this block'],
          });
        }
      }
    }

    return issues;
  },
};

/**
 * Rule: IF blocks must have a condition (not the default placeholder)
 */
const conditionExistsRule: ValidationRule = {
  id: 'condition.required',
  name: 'Condition Required',
  description: 'IF blocks must have a valid condition',
  severity: 'error',
  validate: (tree) => {
    const issues: ValidationIssue[] = [];
    const ifBlocks = getBlocksByType(tree, isIfBlock);

    for (const ifBlock of ifBlocks) {
      if (!ifBlock.condition) {
        issues.push({
          ruleId: 'condition.required',
          blockId: ifBlock.id,
          field: 'condition',
          message: 'IF block must have a condition',
          severity: 'error',
          suggestions: ['Click on the IF block to set a condition'],
        });
      }
    }

    return issues;
  },
};

/**
 * Rule: Warn if condition is a default placeholder (close of SPY > 0)
 */
const conditionNotDefaultRule: ValidationRule = {
  id: 'condition.meaningful',
  name: 'Meaningful Condition',
  description: 'Condition should be meaningful, not a default placeholder',
  severity: 'warning',
  validate: (tree) => {
    const issues: ValidationIssue[] = [];
    const ifBlocks = getBlocksByType(tree, isIfBlock);

    for (const ifBlock of ifBlocks) {
      const { condition } = ifBlock;
      if (!condition) continue;

      // Check for default placeholder condition: close of SPY > 0
      const isDefault =
        condition.left.type === 'price' &&
        condition.left.symbol === 'SPY' &&
        condition.left.field === 'close' &&
        condition.comparator === 'gt' &&
        condition.right.type === 'number' &&
        condition.right.value === 0;

      if (isDefault) {
        issues.push({
          ruleId: 'condition.meaningful',
          blockId: ifBlock.id,
          field: 'condition',
          message: 'This looks like a default condition - consider setting a meaningful trigger',
          severity: 'warning',
          suggestions: [
            'Set a price comparison (e.g., price > moving average)',
            'Use an indicator (e.g., RSI < 30)',
          ],
        });
      }
    }

    return issues;
  },
};

/**
 * Rule: No orphan blocks (blocks not reachable from root)
 */
const noOrphansRule: ValidationRule = {
  id: 'structure.no-orphans',
  name: 'No Orphan Blocks',
  description: 'All blocks should be reachable from the root',
  severity: 'warning',
  validate: (tree) => {
    const issues: ValidationIssue[] = [];
    const reachable = getReachableIds(tree, tree.rootId);

    for (const blockId of Object.keys(tree.blocks)) {
      if (!reachable.has(blockId)) {
        const block = tree.blocks[blockId];
        const blockType = block?.type || 'unknown';
        issues.push({
          ruleId: 'structure.no-orphans',
          blockId,
          message: `Orphan ${blockType} block is not connected to the strategy`,
          severity: 'warning',
          suggestions: ['Remove this block or connect it to the tree'],
        });
      }
    }

    return issues;
  },
};

/**
 * Rule: Groups should not be empty
 */
const groupsNotEmptyRule: ValidationRule = {
  id: 'structure.group-not-empty',
  name: 'Groups Have Children',
  description: 'Groups should contain at least one child block',
  severity: 'warning',
  validate: (tree) => {
    const issues: ValidationIssue[] = [];
    const groupBlocks = getBlocksByType(tree, isGroupBlock);

    for (const group of groupBlocks) {
      if (group.childIds.length === 0) {
        issues.push({
          ruleId: 'structure.group-not-empty',
          blockId: group.id,
          message: `Group "${group.name}" is empty`,
          severity: 'warning',
          suggestions: ['Add assets or nested blocks to this group'],
        });
      }
    }

    return issues;
  },
};

/**
 * Rule: Filter count must be positive
 */
const filterCountPositiveRule: ValidationRule = {
  id: 'filter.count-positive',
  name: 'Filter Count Positive',
  description: 'Filter must select at least 1 asset',
  severity: 'error',
  validate: (tree) => {
    const issues: ValidationIssue[] = [];
    const filterBlocks = getBlocksByType(tree, isFilterBlock);

    for (const filter of filterBlocks) {
      if (filter.config.count < 1) {
        issues.push({
          ruleId: 'filter.count-positive',
          blockId: filter.id,
          field: 'config.count',
          message: 'Filter must select at least 1 asset',
          severity: 'error',
          suggestions: ['Set count to 1 or higher'],
        });
      }
    }

    return issues;
  },
};

/**
 * Rule: Filter count should not exceed available assets
 */
const filterCountExceedsAssetsRule: ValidationRule = {
  id: 'filter.count-exceeds',
  name: 'Filter Count Valid',
  description: 'Filter count should not exceed available assets',
  severity: 'warning',
  validate: (tree) => {
    const issues: ValidationIssue[] = [];
    const filterBlocks = getBlocksByType(tree, isFilterBlock);

    for (const filter of filterBlocks) {
      // Count assets in filter's children
      const assetCount = filter.childIds.reduce(
        (count, childId) => count + countAssetsInSubtree(tree, childId),
        0
      );

      // Also count custom symbols if specified
      const customCount = filter.config.customSymbols?.length || 0;
      const totalAvailable = assetCount + customCount;

      // For non-custom universe, we don't know the exact count
      if (filter.config.universe !== 'custom' && totalAvailable === 0) continue;

      if (filter.config.count > totalAvailable && totalAvailable > 0) {
        issues.push({
          ruleId: 'filter.count-exceeds',
          blockId: filter.id,
          field: 'config.count',
          message: `Filter selects ${filter.config.count} but only ${totalAvailable} assets available`,
          severity: 'warning',
          suggestions: [`Reduce count to ${totalAvailable} or add more assets`],
        });
      }
    }

    return issues;
  },
};

/**
 * Rule: Weight blocks should have children
 */
const weightHasChildrenRule: ValidationRule = {
  id: 'weight.has-children',
  name: 'Weight Has Children',
  description: 'Weight blocks should have at least one child',
  severity: 'warning',
  validate: (tree) => {
    const issues: ValidationIssue[] = [];
    const weightBlocks = getBlocksByType(tree, isWeightBlock);

    for (const weight of weightBlocks) {
      if (weight.childIds.length === 0) {
        issues.push({
          ruleId: 'weight.has-children',
          blockId: weight.id,
          message: 'Weight block has no children',
          severity: 'warning',
          suggestions: ['Add assets to this weight block'],
        });
      }
    }

    return issues;
  },
};

/**
 * Rule: IF blocks should have content in the then branch
 */
const ifHasThenContentRule: ValidationRule = {
  id: 'condition.has-then',
  name: 'IF Has Then Content',
  description: 'IF blocks should have content in the then branch',
  severity: 'warning',
  validate: (tree) => {
    const issues: ValidationIssue[] = [];
    const ifBlocks = getBlocksByType(tree, isIfBlock);

    for (const ifBlock of ifBlocks) {
      if (ifBlock.childIds.length === 0) {
        issues.push({
          ruleId: 'condition.has-then',
          blockId: ifBlock.id,
          message: 'IF block has no content - add assets or nested blocks',
          severity: 'warning',
          suggestions: ['Add content to define what happens when the condition is true'],
        });
      }
    }

    return issues;
  },
};

/**
 * Rule: Check for duplicate assets
 */
const noDuplicateAssetsRule: ValidationRule = {
  id: 'structure.no-duplicates',
  name: 'No Duplicate Assets',
  description: 'Warn about duplicate asset symbols in the same context',
  severity: 'warning',
  validate: (tree) => {
    const issues: ValidationIssue[] = [];

    // Check each parent container for duplicates
    const checkContainer = (parentId: BlockId) => {
      const children = getChildren(tree, parentId);
      const assets = children.filter(isAssetBlock);
      const symbolCounts = new Map<string, BlockId[]>();

      for (const asset of assets) {
        const existing = symbolCounts.get(asset.symbol) || [];
        existing.push(asset.id);
        symbolCounts.set(asset.symbol, existing);
      }

      for (const [symbol, ids] of symbolCounts) {
        if (ids.length > 1) {
          issues.push({
            ruleId: 'structure.no-duplicates',
            blockId: ids[0],
            message: `Asset "${symbol}" appears ${ids.length} times in this container`,
            severity: 'warning',
            suggestions: ['Remove duplicate assets or move them to different containers'],
          });
        }
      }
    };

    // Check all parent blocks
    for (const block of Object.values(tree.blocks)) {
      if (hasChildren(block)) {
        checkContainer(block.id);
      }
    }

    return issues;
  },
};

// ============================================
// All Validation Rules
// ============================================

export const VALIDATION_RULES: ValidationRule[] = [
  // Critical structure rules
  hasAssetsRule,

  // Weight rules
  weightSumRule,
  weightsPositiveRule,
  specifiedHasWeightsRule,
  weightHasChildrenRule,

  // Condition rules
  conditionExistsRule,
  conditionNotDefaultRule,
  ifHasThenContentRule,

  // Filter rules
  filterCountPositiveRule,
  filterCountExceedsAssetsRule,

  // Structure rules
  noOrphansRule,
  groupsNotEmptyRule,
  noDuplicateAssetsRule,
];

// ============================================
// Main Validation Function
// ============================================

/**
 * Run all validation rules on a strategy tree
 */
export function validateStrategy(tree: StrategyTree): ValidationResult {
  const issues: ValidationIssue[] = [];

  for (const rule of VALIDATION_RULES) {
    const ruleIssues = rule.validate(tree);
    issues.push(...ruleIssues);
  }

  const errors = issues.filter((i) => i.severity === 'error');
  const warnings = issues.filter((i) => i.severity === 'warning');

  return {
    valid: errors.length === 0,
    issues,
    errors,
    warnings,
  };
}

/**
 * Run validation with specific rule IDs only
 */
export function validateWithRules(
  tree: StrategyTree,
  ruleIds: string[]
): ValidationResult {
  const issues: ValidationIssue[] = [];
  const rules = VALIDATION_RULES.filter((r) => ruleIds.includes(r.id));

  for (const rule of rules) {
    const ruleIssues = rule.validate(tree);
    issues.push(...ruleIssues);
  }

  const errors = issues.filter((i) => i.severity === 'error');
  const warnings = issues.filter((i) => i.severity === 'warning');

  return {
    valid: errors.length === 0,
    issues,
    errors,
    warnings,
  };
}

/**
 * Get validation issues for a specific block
 */
export function getBlockIssues(
  result: ValidationResult,
  blockId: BlockId
): ValidationIssue[] {
  return result.issues.filter((i) => i.blockId === blockId);
}

/**
 * Check if a specific block has errors
 */
export function blockHasError(result: ValidationResult, blockId: BlockId): boolean {
  return result.errors.some((e) => e.blockId === blockId);
}

/**
 * Check if a specific block has warnings
 */
export function blockHasWarning(result: ValidationResult, blockId: BlockId): boolean {
  return result.warnings.some((w) => w.blockId === blockId);
}

export default validateStrategy;
