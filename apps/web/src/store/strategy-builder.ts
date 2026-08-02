import {
  toDSL,
  fromDSLString,
  conditionToText,
  validateTree,
  type StrategyMetadata,
} from '@llamatrade/core/strategy/serializer';
import type {
  BlockId,
  Block,
  StrategyTree,
  StrategyBuilderUI,
  WeightMethod,
  ParentBlock,
  ConditionExpression,
  FilterConfig,
  IfBlock,
  ElseBlock,
  FilterBlock,
  WeightBlock,
} from '@llamatrade/core/strategy/types';
import { hasChildren } from '@llamatrade/core/strategy/types';
import { validateStrategy, type ValidationResult, type ValidationIssue } from '@llamatrade/core/strategy/validator';
import { enableMapSet } from 'immer';
import { createContext, useContext } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { create, createStore, useStore } from 'zustand';
import { immer } from 'zustand/middleware/immer';

import { agentClient, strategyClient } from '../services/grpc-client';

import { getTenantContext } from './auth';

export type { ValidationResult, ValidationIssue };

enableMapSet();

// View mode type (defined early for use in persistence helpers)
export type ViewMode = 'tree' | 'code' | 'split';

// Expand/Collapse State Persistence
const COLLAPSED_STORAGE_KEY = 'strategy-builder-collapsed';

// View Mode Persistence
const VIEW_MODE_STORAGE_KEY = 'strategy-builder-viewmode';

/**
 * Get stored view mode for a strategy or preview ID.
 */
function getStoredViewMode(strategyId: string | null, fallback: ViewMode = 'tree'): ViewMode {
  if (!strategyId) return fallback;
  try {
    const stored = localStorage.getItem(VIEW_MODE_STORAGE_KEY);
    if (!stored) return fallback;
    const map = JSON.parse(stored) as Record<string, ViewMode>;
    return map[strategyId] ?? fallback;
  } catch {
    return fallback;
  }
}

/**
 * Save view mode for a strategy or preview ID.
 */
function saveViewMode(strategyId: string | null, mode: ViewMode): void {
  if (!strategyId) return;
  try {
    const stored = localStorage.getItem(VIEW_MODE_STORAGE_KEY);
    const map: Record<string, ViewMode> = stored ? JSON.parse(stored) : {};
    map[strategyId] = mode;
    localStorage.setItem(VIEW_MODE_STORAGE_KEY, JSON.stringify(map));
  } catch {
    // Ignore storage errors
  }
}

/**
 * Generate a stable path for a block that survives DSL round-trips.
 * Uses block type, name/symbol, and position in parent.
 */
function getBlockPath(blocks: Record<BlockId, Block>, blockId: BlockId): string {
  const parts: string[] = [];
  let current = blocks[blockId];

  while (current) {
    let identifier: string = current.type;
    if (current.type === 'root' && 'name' in current) {
      identifier = `root`;
    } else if (current.type === 'group' && 'name' in current) {
      identifier = `group:${current.name}`;
    } else if (current.type === 'asset' && 'symbol' in current) {
      identifier = `asset:${current.symbol}`;
    } else if (current.type === 'weight' && 'method' in current) {
      identifier = `weight:${current.method}`;
    } else if (current.type === 'if') {
      identifier = `if`;
    } else if (current.type === 'else') {
      identifier = `else`;
    } else if (current.type === 'filter' && 'config' in current) {
      const cfg = current.config as FilterConfig;
      identifier = `filter:${cfg.sortBy}`;
    }

    // Add position in parent for disambiguation
    if (current.parentId) {
      const parent = blocks[current.parentId];
      if (parent && 'childIds' in parent) {
        const idx = (parent.childIds as BlockId[]).indexOf(current.id);
        identifier += `[${idx}]`;
      }
    }

    parts.unshift(identifier);
    current = current.parentId ? blocks[current.parentId] : undefined as unknown as Block;
  }

  return parts.join('/');
}

/**
 * Save collapsed block paths to localStorage for a strategy.
 */
function saveCollapsedState(strategyId: string | null, blocks: Record<BlockId, Block>, expandedBlocks: Set<BlockId>): void {
  if (!strategyId) return;

  try {
    const stored = localStorage.getItem(COLLAPSED_STORAGE_KEY);
    const allCollapsed: Record<string, string[]> = stored ? JSON.parse(stored) : {};

    // Find all collapsible blocks that are NOT expanded (i.e., collapsed)
    const collapsedPaths: string[] = [];
    for (const block of Object.values(blocks)) {
      if (hasChildren(block) && !expandedBlocks.has(block.id)) {
        collapsedPaths.push(getBlockPath(blocks, block.id));
      }
    }

    allCollapsed[strategyId] = collapsedPaths;
    localStorage.setItem(COLLAPSED_STORAGE_KEY, JSON.stringify(allCollapsed));
  } catch {
    // Ignore localStorage errors
  }
}

/**
 * Load collapsed block paths from localStorage and return collapsed block IDs.
 */
function loadCollapsedState(strategyId: string | null, blocks: Record<BlockId, Block>): Set<BlockId> {
  const collapsedIds = new Set<BlockId>();
  if (!strategyId) return collapsedIds;

  try {
    const stored = localStorage.getItem(COLLAPSED_STORAGE_KEY);
    if (!stored) return collapsedIds;

    const allCollapsed: Record<string, string[]> = JSON.parse(stored);
    const collapsedPaths = allCollapsed[strategyId] || [];

    if (collapsedPaths.length === 0) return collapsedIds;

    const pathToId = new Map<string, BlockId>();
    for (const block of Object.values(blocks)) {
      pathToId.set(getBlockPath(blocks, block.id), block.id);
    }

    // Find blocks that should be collapsed
    for (const path of collapsedPaths) {
      const blockId = pathToId.get(path);
      if (blockId) {
        collapsedIds.add(blockId);
      }
    }
  } catch {
    // Ignore localStorage errors
  }

  return collapsedIds;
}

// Maximum history entries for undo/redo
const MAX_HISTORY = 50;

// Debounce delay for auto-save (in milliseconds)
const DEBOUNCE_SAVE_MS = 2000;

let saveDebounceTimer: ReturnType<typeof setTimeout> | null = null;

// Live code⇄tree sync: debounce for committing typed DSL back into the tree.
const CODE_COMMIT_MS = 250;
let codeCommitTimer: ReturnType<typeof setTimeout> | null = null;
// Guards the tree→code regeneration subscription while a code→tree commit runs,
// so the user's in-progress code isn't reformatted under their cursor.
let suppressTreeToCode = false;

/**
 * Re-key a freshly-parsed tree onto the previous tree's block ids by walking
 * both in parallel: a block at the same position with the same type keeps its
 * old id (so selection, expand state, and weight allocations survive), while
 * genuinely new blocks keep their fresh ids. This is what makes the live code→
 * tree bind non-destructive instead of churning every id on each keystroke.
 */
export function reconcileIds(oldTree: StrategyTree, newTree: StrategyTree): StrategyTree {
  const outBlocks: Record<BlockId, Block> = {};
  const newToOut = new Map<BlockId, BlockId>();

  const walk = (oldId: BlockId | undefined, newId: BlockId, outParentId: BlockId | null): BlockId => {
    const nb = newTree.blocks[newId];
    const ob = oldId ? oldTree.blocks[oldId] : undefined;
    const reuse = !!ob && ob.type === nb.type;
    const outId = reuse ? (oldId as BlockId) : newId;
    newToOut.set(newId, outId);

    const clone = { ...nb, id: outId, parentId: outParentId } as Block;

    if (hasChildren(nb)) {
      const oldChildIds = reuse && ob && hasChildren(ob) ? ob.childIds : [];
      const outChildIds = nb.childIds.map((cNewId, idx) => walk(oldChildIds[idx], cNewId, outId));
      (clone as ParentBlock).childIds = outChildIds;

      if (nb.type === 'weight') {
        const remapped: Record<BlockId, number> = {};
        nb.childIds.forEach((cNewId, idx) => {
          remapped[outChildIds[idx]] = (nb as WeightBlock).allocations[cNewId] ?? 0;
        });
        (clone as WeightBlock).allocations = remapped;
      }
    }

    outBlocks[outId] = clone;
    return outId;
  };

  const outRootId = walk(oldTree.rootId, newTree.rootId, null);

  // ElseBlock.ifBlockId points at a sibling if-block by id — remap onto out ids.
  for (const block of Object.values(outBlocks)) {
    if (block.type === 'else') {
      const mapped = newToOut.get((block as ElseBlock).ifBlockId);
      if (mapped) (block as ElseBlock).ifBlockId = mapped;
    }
  }

  return { rootId: outRootId, blocks: outBlocks };
}

// Create empty initial state (just root block, no demo content)
function createInitialState(): { tree: StrategyTree; expandedBlocks: Set<BlockId> } {
  const rootId = uuidv4();

  const blocks: Record<BlockId, Block> = {
    [rootId]: {
      id: rootId,
      type: 'root',
      parentId: null,
      name: 'New Strategy',
      childIds: [],
    },
  };

  return {
    tree: { rootId, blocks },
    expandedBlocks: new Set([rootId]),
  };
}

// Initialize once and reuse
const initialState = createInitialState();

interface StrategyBuilderState {
  // Tree data
  tree: StrategyTree;

  // UI state
  ui: StrategyBuilderUI;

  // View mode state
  viewMode: ViewMode;
  compactView: boolean; // Hide edit controls for cleaner view
  dslCode: string;
  dslParseError: string | null;

  // History for undo/redo
  past: StrategyTree[];
  future: StrategyTree[];

  // Strategy metadata
  strategyId: string | null;
  pendingArtifactId: string | null;  // ID of artifact being edited (survives refresh)
  pendingTemplateId: string | null;  // ID of template being edited (survives refresh)
  strategyName: string;
  strategyDescription: string;
  timeframe: string;
  benchmark: string;
  isDirty: boolean;

  // Version tracking for optimistic locking
  serverVersion: number;        // Version from last load/save
  lastSavedAt: number | null;   // Timestamp of last successful save
  conflictDetected: boolean;    // True if server has newer version

  // Async state
  loading: boolean;
  saving: boolean;
  error: string | null;

  // Real-time validation state
  validationResult: ValidationResult;
  isValid: boolean;

  // Block CRUD operations
  addAsset: (
    parentId: BlockId,
    symbol: string,
    exchange: string,
    displayName: string
  ) => BlockId;
  addGroup: (parentId: BlockId, name: string) => BlockId;
  addWeight: (parentId: BlockId, method: WeightMethod) => BlockId;
  updateBlock: (id: BlockId, updates: Partial<Block>) => void;
  deleteBlock: (id: BlockId) => void;

  // Weight-specific operations
  setWeightAllocation: (weightId: BlockId, childId: BlockId, percent: number) => void;

  // Condition operations (IF/ELSE blocks)
  addCondition: (parentId: BlockId, condition: ConditionExpression) => BlockId;
  updateCondition: (id: BlockId, condition: ConditionExpression) => void;

  // Filter operations
  addFilter: (parentId: BlockId, config: FilterConfig) => BlockId;
  updateFilter: (id: BlockId, config: FilterConfig) => void;

  // UI operations
  selectBlock: (id: BlockId | null) => void;
  toggleExpand: (id: BlockId) => void;
  setEditing: (id: BlockId | null) => void;

  // Metadata operations
  setStrategyName: (name: string) => void;
  setStrategyDescription: (description: string) => void;
  setTimeframe: (timeframe: string) => void;
  setBenchmark: (benchmark: string) => void;

  // History operations
  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;

  // Backend operations
  loadStrategy: (id: string) => Promise<void>;
  loadTemplate: (templateId: string) => Promise<void>;
  loadFromDSL: (dslCode: string, name?: string, description?: string) => boolean;
  loadFromArtifact: (artifactId: string) => Promise<void>;
  saveStrategy: () => Promise<string | null>;
  saveStrategyDebounced: () => void;  // Debounced save for frequent updates
  cancelDebouncedSave: () => void;    // Cancel pending debounced save
  resolveConflict: (useLocal: boolean) => Promise<void>;  // Handle version conflicts
  createNew: () => void;

  // View mode operations
  setViewMode: (mode: ViewMode) => void;
  toggleCompactView: () => void;
  updateDSLCode: (code: string) => void;
  syncTreeFromCode: () => boolean;
  commitCodeToTree: () => void;  // Live-parse dslCode into the tree (id-preserving)
  getDSLCode: () => string;
  clearDSLParseError: () => void;

  // Validation operations
  getBlockErrors: (blockId: BlockId) => ValidationIssue[];
  getBlockWarnings: (blockId: BlockId) => ValidationIssue[];
  refreshValidation: () => void;

  // Utility
  getBlock: (id: BlockId) => Block | undefined;
  getParent: (id: BlockId) => ParentBlock | undefined;
  reset: () => void;
  clearError: () => void;
}

/** Strategy-level metadata the DSL emitter needs, read off the store's own fields. */
function dslMetadata(state: {
  strategyName: string;
  strategyDescription: string;
  timeframe: string;
  benchmark: string;
}): StrategyMetadata {
  return {
    name: state.strategyName,
    description: state.strategyDescription,
    timeframe: state.timeframe,
    benchmark: state.benchmark || undefined,
  };
}

// Helper to save current state to history
function pushToHistory(state: StrategyBuilderState): void {
  state.past.push(JSON.parse(JSON.stringify(state.tree)));
  if (state.past.length > MAX_HISTORY) {
    state.past.shift();
  }
  state.future = [];
}

// Helper to run validation and update state
function runValidation(state: StrategyBuilderState): void {
  const result = validateStrategy(state.tree);
  state.validationResult = result;
  state.isValid = result.valid;
}

// Initial empty validation result
const emptyValidationResult: ValidationResult = {
  valid: true,
  issues: [],
  errors: [],
  warnings: [],
};

// Helper to add child to parent
function addChildToParent(blocks: Record<BlockId, Block>, parentId: BlockId, childId: BlockId): void {
  const parent = blocks[parentId];
  if (hasChildren(parent)) {
    parent.childIds.push(childId);
  }
}

// Helper to remove child from parent
function removeChildFromParent(blocks: Record<BlockId, Block>, parentId: BlockId, childId: BlockId): void {
  const parent = blocks[parentId];
  if (hasChildren(parent)) {
    const index = parent.childIds.indexOf(childId);
    if (index !== -1) {
      parent.childIds.splice(index, 1);
    }
  }
}

// Recursively delete a block and all its children
function deleteBlockRecursive(blocks: Record<BlockId, Block>, blockId: BlockId): void {
  const block = blocks[blockId];
  if (!block) return;

  // Delete children first
  if (hasChildren(block)) {
    [...block.childIds].forEach((childId) => {
      deleteBlockRecursive(blocks, childId);
    });
  }

  // Delete the block itself
  delete blocks[blockId];
}

// Generate verbose display text for filter config
function filterConfigToDisplayText(config: FilterConfig): string {
  const periodLabels: Record<string, string> = {
    '1m': '1 month',
    '3m': '3 months',
    '6m': '6 months',
    '12m': '12 months',
  };
  const sortLabels: Record<string, string> = {
    momentum: 'Momentum',
    market_cap: 'Market Cap',
    volume: 'Volume',
    volatility: 'Volatility',
    rsi: 'RSI',
    dividend_yield: 'Dividend Yield',
  };
  return `${config.selection === 'top' ? 'Top' : 'Bottom'} ${config.count} by ${sortLabels[config.sortBy] || config.sortBy} (${periodLabels[config.period] || config.period})`;
}

export const useStrategyBuilderStore = create<StrategyBuilderState>()(
  immer((set, get) => ({
    tree: initialState.tree,
    ui: {
      selectedBlockId: null,
      expandedBlocks: initialState.expandedBlocks,
      editingBlockId: null,
    },

    // View mode state
    viewMode: 'split' as ViewMode,
    compactView: false,
    dslCode: '',
    dslParseError: null,

    past: [],
    future: [],

    // Strategy metadata
    strategyId: null,
    pendingArtifactId: null,
    pendingTemplateId: null,
    strategyName: 'Untitled Strategy',
    strategyDescription: '',
    timeframe: '1D',
    benchmark: '',
    isDirty: false,

    // Version tracking for optimistic locking
    serverVersion: 0,
    lastSavedAt: null,
    conflictDetected: false,

    // Async state
    loading: false,
    saving: false,
    error: null,

    // Real-time validation state
    validationResult: emptyValidationResult,
    isValid: true,

      addAsset: (parentId, symbol, exchange, displayName) => {
        const id = uuidv4();
        set((state) => {
          pushToHistory(state);
          state.tree.blocks[id] = {
            id,
            type: 'asset',
            parentId,
            symbol,
            exchange,
            displayName,
          };
          addChildToParent(state.tree.blocks, parentId, id);
          state.ui.expandedBlocks.add(parentId);
          state.isDirty = true;
          runValidation(state);
        });
        return id;
      },

      addGroup: (parentId, name) => {
        const id = uuidv4();
        set((state) => {
          pushToHistory(state);
          state.tree.blocks[id] = {
            id,
            type: 'group',
            parentId,
            name,
            childIds: [],
          };
          addChildToParent(state.tree.blocks, parentId, id);
          state.ui.expandedBlocks.add(parentId);
          state.ui.expandedBlocks.add(id);
          state.isDirty = true;
          runValidation(state);
        });
        return id;
      },

      addWeight: (parentId, method) => {
        const id = uuidv4();
        set((state) => {
          pushToHistory(state);
          state.tree.blocks[id] = {
            id,
            type: 'weight',
            parentId,
            method,
            allocations: {},
            lookbackDays: method === 'inverse_volatility' || method === 'momentum' || method === 'min_variance' ? 30 : undefined,
            childIds: [],
          };
          addChildToParent(state.tree.blocks, parentId, id);
          state.ui.expandedBlocks.add(parentId);
          state.ui.expandedBlocks.add(id);
          state.isDirty = true;
          runValidation(state);
        });
        return id;
      },

      updateBlock: (id, updates) => {
        set((state) => {
          const block = state.tree.blocks[id];
          if (!block) return;
          pushToHistory(state);
          Object.assign(block, updates);
          state.isDirty = true;
          runValidation(state);
        });
      },

      deleteBlock: (id) => {
        set((state) => {
          const block = state.tree.blocks[id];
          if (!block || block.type === 'root') return;

          pushToHistory(state);

          // Remove from parent
          if (block.parentId) {
            removeChildFromParent(state.tree.blocks, block.parentId, id);
          }

          // Delete block and all children
          deleteBlockRecursive(state.tree.blocks, id);

          // Clear selection if deleted
          if (state.ui.selectedBlockId === id) {
            state.ui.selectedBlockId = null;
          }
          state.ui.expandedBlocks.delete(id);
          state.isDirty = true;
          runValidation(state);
        });
      },

      setWeightAllocation: (weightId, childId, percent) => {
        set((state) => {
          const block = state.tree.blocks[weightId];
          if (!block || block.type !== 'weight') return;
          pushToHistory(state);
          block.allocations[childId] = Math.max(0, Math.min(100, percent));
          state.isDirty = true;
          runValidation(state);
        });
      },

      // Condition operations
      addCondition: (parentId, condition) => {
        const ifId = uuidv4();
        const elseId = uuidv4();
        set((state) => {
          pushToHistory(state);

          // Create IF block
          const ifBlock: IfBlock = {
            id: ifId,
            type: 'if',
            parentId,
            condition,
            conditionText: conditionToText(condition),
            childIds: [],
          };
          state.tree.blocks[ifId] = ifBlock;
          addChildToParent(state.tree.blocks, parentId, ifId);

          // Create associated ELSE block
          const elseBlock: ElseBlock = {
            id: elseId,
            type: 'else',
            parentId,
            ifBlockId: ifId,
            childIds: [],
          };
          state.tree.blocks[elseId] = elseBlock;
          addChildToParent(state.tree.blocks, parentId, elseId);

          // Expand parents
          state.ui.expandedBlocks.add(parentId);
          state.ui.expandedBlocks.add(ifId);
          state.ui.expandedBlocks.add(elseId);
          state.isDirty = true;
          runValidation(state);
        });
        return ifId;
      },

      updateCondition: (id, condition) => {
        set((state) => {
          const block = state.tree.blocks[id];
          if (!block || block.type !== 'if') return;
          pushToHistory(state);
          (block as IfBlock).condition = condition;
          (block as IfBlock).conditionText = conditionToText(condition);
          state.isDirty = true;
          runValidation(state);
        });
      },

      // Filter operations
      addFilter: (parentId, config) => {
        const id = uuidv4();
        set((state) => {
          pushToHistory(state);
          const filterBlock: FilterBlock = {
            id,
            type: 'filter',
            parentId,
            config,
            displayText: filterConfigToDisplayText(config),
            childIds: [], // Populated dynamically
          };
          state.tree.blocks[id] = filterBlock;
          addChildToParent(state.tree.blocks, parentId, id);
          state.ui.expandedBlocks.add(parentId);
          state.ui.expandedBlocks.add(id);
          state.isDirty = true;
          runValidation(state);
        });
        return id;
      },

      updateFilter: (id, config) => {
        set((state) => {
          const block = state.tree.blocks[id];
          if (!block || block.type !== 'filter') return;
          pushToHistory(state);
          (block as FilterBlock).config = config;
          (block as FilterBlock).displayText = filterConfigToDisplayText(config);
          state.isDirty = true;
          runValidation(state);
        });
      },

      selectBlock: (id) => {
        set((state) => {
          state.ui.selectedBlockId = id;
        });
      },

      toggleExpand: (id) => {
        set((state) => {
          if (state.ui.expandedBlocks.has(id)) {
            state.ui.expandedBlocks.delete(id);
          } else {
            state.ui.expandedBlocks.add(id);
          }
        });
        // Persist collapsed state after toggle
        const { strategyId, tree, ui } = get();
        saveCollapsedState(strategyId, tree.blocks, ui.expandedBlocks);
      },

      setEditing: (id) => {
        set((state) => {
          state.ui.editingBlockId = id;
        });
      },

      undo: () => {
        set((state) => {
          const previous = state.past.pop();
          if (!previous) return;
          state.future.push(JSON.parse(JSON.stringify(state.tree)));
          state.tree = previous;
          runValidation(state);
        });
      },

      redo: () => {
        set((state) => {
          const next = state.future.pop();
          if (!next) return;
          state.past.push(JSON.parse(JSON.stringify(state.tree)));
          state.tree = next;
          runValidation(state);
        });
      },

      canUndo: () => get().past.length > 0,
      canRedo: () => get().future.length > 0,

      getBlock: (id) => get().tree.blocks[id],
      getParent: (id) => {
        const block = get().tree.blocks[id];
        if (!block || !block.parentId) return undefined;
        const parent = get().tree.blocks[block.parentId];
        return parent && hasChildren(parent) ? parent : undefined;
      },

      // View mode operations
      setViewMode: (mode) => {
        const state = get();
        if (mode === state.viewMode) return;

        const showsCode = mode === 'code' || mode === 'split';
        if (showsCode) {
          // Entering a code-visible mode: refresh the buffer from the tree.
          const dslCode = state.getDSLCode();
          set((s) => {
            s.viewMode = mode;
            s.dslCode = dslCode;
            s.dslParseError = null;
          });
        } else {
          // Entering tree-only: the live bind already kept the tree current.
          set((s) => {
            s.viewMode = mode;
            s.dslParseError = null;
          });
        }
        saveViewMode(state.strategyId, mode);
      },

      toggleCompactView: () => {
        set((s) => {
          s.compactView = !s.compactView;
        });
      },

      updateDSLCode: (code) => {
        set((state) => {
          state.dslCode = code;
          state.isDirty = true;
          // Clear parse error when user edits
          state.dslParseError = null;
        });
        // Live-commit the typed code back into the tree (debounced).
        if (codeCommitTimer) clearTimeout(codeCommitTimer);
        codeCommitTimer = setTimeout(() => {
          get().commitCodeToTree();
        }, CODE_COMMIT_MS);
      },

      commitCodeToTree: () => {
        const { dslCode, tree: prevTree, viewMode } = get();
        // Only bind live while a code surface is visible.
        if (viewMode !== 'code' && viewMode !== 'split') return;

        const parsed = fromDSLString(dslCode);
        if (!parsed) {
          set((s) => {
            s.dslParseError = 'Invalid DSL syntax. Please check your code.';
          });
          return;
        }
        const validation = validateTree(parsed.tree);
        if (!validation.valid) {
          set((s) => {
            s.dslParseError = validation.errors.map((e) => e.message).join(', ');
          });
          return;
        }

        const reconciled = reconcileIds(prevTree, parsed.tree);
        const oldIds = new Set(Object.keys(prevTree.blocks));
        const { metadata } = parsed;

        // Suppress the tree→code subscription so the code isn't reformatted mid-type.
        suppressTreeToCode = true;
        set((s) => {
          const prevExpanded = s.ui.expandedBlocks;
          s.tree = reconciled;

          if (metadata.name) s.strategyName = metadata.name;
          if (metadata.description !== undefined) s.strategyDescription = metadata.description;
          if (metadata.timeframe) s.timeframe = metadata.timeframe;
          s.benchmark = metadata.benchmark ?? '';
          const root = s.tree.blocks[s.tree.rootId];
          if (root && root.type === 'root' && metadata.name) root.name = metadata.name;

          // Keep expand state for surviving blocks; auto-expand newly added parents.
          const expanded = new Set<BlockId>();
          for (const b of Object.values(reconciled.blocks)) {
            if (!hasChildren(b)) continue;
            if (!oldIds.has(b.id) || prevExpanded.has(b.id)) expanded.add(b.id);
          }
          s.ui.expandedBlocks = expanded;

          if (s.ui.selectedBlockId && !reconciled.blocks[s.ui.selectedBlockId]) {
            s.ui.selectedBlockId = null;
          }
          if (s.ui.editingBlockId && !reconciled.blocks[s.ui.editingBlockId]) {
            s.ui.editingBlockId = null;
          }

          s.dslParseError = null;
          s.isDirty = true;
          runValidation(s);
        });
        suppressTreeToCode = false;
      },

      syncTreeFromCode: () => {
        const { dslCode } = get();

        const parsed = fromDSLString(dslCode);
        if (!parsed) {
          set((s) => {
            s.dslParseError = 'Invalid DSL syntax. Please check your code.';
          });
          return false;
        }

        const { tree, metadata } = parsed;

        const validation = validateTree(tree);
        if (!validation.valid) {
          set((s) => {
            s.dslParseError = validation.errors.map((e) => e.message).join(', ');
          });
          return false;
        }

        set((s) => {
          pushToHistory(s);
          s.tree = tree;

          // Update metadata from parsed DSL
          if (metadata.name) {
            s.strategyName = metadata.name;
          }
          if (metadata.description !== undefined) {
            s.strategyDescription = metadata.description;
          }
          if (metadata.timeframe) {
            s.timeframe = metadata.timeframe;
          }
          s.benchmark = metadata.benchmark ?? '';

          // Update root block name to match parsed strategy name
          const root = s.tree.blocks[s.tree.rootId];
          if (root && root.type === 'root' && metadata.name) {
            root.name = metadata.name;
          }

          // Expand all parent blocks
          const expandedBlocks = new Set<BlockId>();
          for (const block of Object.values(tree.blocks)) {
            if (hasChildren(block)) {
              expandedBlocks.add(block.id);
            }
          }
          s.ui.expandedBlocks = expandedBlocks;
          s.dslParseError = null;
          runValidation(s);
        });
        return true;
      },

      getDSLCode: () => {
        const state = get();
        return toDSL(state.tree, dslMetadata(state));
      },

      clearDSLParseError: () => {
        set((state) => {
          state.dslParseError = null;
        });
      },

      reset: () => {
        // Cancel any pending debounced save
        if (saveDebounceTimer) {
          clearTimeout(saveDebounceTimer);
          saveDebounceTimer = null;
        }
        set((state) => {
          const newState = createInitialState();
          state.tree = newState.tree;
          state.ui = {
            selectedBlockId: null,
            expandedBlocks: newState.expandedBlocks,
            editingBlockId: null,
          };
          state.viewMode = 'split';
          state.dslCode = '';
          state.dslParseError = null;
          state.past = [];
          state.future = [];
          state.strategyId = null;
          state.pendingArtifactId = null;
          state.pendingTemplateId = null;
          state.strategyName = 'Untitled Strategy';
          state.strategyDescription = '';
          state.timeframe = '1D';
          state.benchmark = '';
          state.isDirty = false;
          state.serverVersion = 0;
          state.lastSavedAt = null;
          state.conflictDetected = false;
          state.error = null;
          state.validationResult = emptyValidationResult;
          state.isValid = true;
          runValidation(state);
        });
      },

      clearError: () => {
        set((state) => {
          state.error = null;
        });
      },

      // Metadata operations
      setStrategyName: (name) => {
        set((state) => {
          state.strategyName = name;
          // Also update the root block name
          const root = state.tree.blocks[state.tree.rootId];
          if (root && root.type === 'root') {
            root.name = name;
          }
          state.isDirty = true;
        });
      },

      setStrategyDescription: (description) => {
        set((state) => {
          state.strategyDescription = description;
          state.isDirty = true;
        });
      },

      setTimeframe: (timeframe) => {
        set((state) => {
          state.timeframe = timeframe;
          state.isDirty = true;
        });
      },

      setBenchmark: (benchmark) => {
        set((state) => {
          state.benchmark = benchmark;
          state.isDirty = true;
        });
      },

      // Backend operations
      loadStrategy: async (id) => {
        set((state) => {
          state.loading = true;
          state.error = null;
        });

        // Load strategy from backend
        try {
          const context = getTenantContext();
          const response = await strategyClient.getStrategy({ context, strategyId: id });
          const strategy = response.strategy;
          if (!strategy) {
            throw new Error('Strategy not found');
          }

          set((state) => {
            state.strategyId = strategy.id;
            state.pendingArtifactId = null; // Clear artifact reference when loading saved strategy
            state.pendingTemplateId = null; // Clear template reference when loading saved strategy
            state.strategyName = strategy.name;
            state.strategyDescription = strategy.description || '';

            // Track server version for optimistic locking
            state.serverVersion = strategy.version || 1;
            state.lastSavedAt = Date.now();
            state.conflictDetected = false;

            // Derive the block tree + strategy-level metadata (rebalance surfaces as the
            // UI timeframe) from the DSL string.
            const parsed = fromDSLString(strategy.dslCode);
            state.timeframe = parsed?.metadata?.timeframe ?? '1D';
            state.benchmark = parsed?.metadata?.benchmark ?? '';
            let tree = parsed?.tree;
            if (!tree) {
              const rootId = uuidv4();
              tree = {
                rootId,
                blocks: {
                  [rootId]: {
                    id: rootId,
                    type: 'root',
                    parentId: null,
                    name: strategy.name || 'Strategy',
                    childIds: [],
                  },
                },
              };
            }
            state.tree = tree;

            // Expand all parent blocks by default
            const expandedBlocks = new Set<BlockId>();
            for (const block of Object.values(tree.blocks)) {
              if (hasChildren(block)) {
                expandedBlocks.add(block.id);
              }
            }

            // Restore collapsed state from localStorage
            const collapsedIds = loadCollapsedState(strategy.id, tree.blocks);
            for (const id of collapsedIds) {
              expandedBlocks.delete(id);
            }

            state.ui.expandedBlocks = expandedBlocks;

            // Restore view mode from localStorage
            const savedViewMode = getStoredViewMode(strategy.id, 'split');
            state.viewMode = savedViewMode;
            // If restoring to a code-visible view, seed the DSL buffer.
            if (savedViewMode === 'code' || savedViewMode === 'split') {
              state.dslCode = toDSL(tree, {
                name: strategy.name,
                description: strategy.description || '',
                timeframe: state.timeframe,
                benchmark: state.benchmark || undefined,
              });
            }

            state.isDirty = false;
            state.loading = false;
            state.past = [];
            state.future = [];
            runValidation(state);
          });
        } catch {
          set((state) => {
            state.error = 'Strategy not found';
            state.loading = false;
          });
        }
      },

      loadTemplate: async (templateId) => {
        set((state) => {
          state.loading = true;
          state.error = null;
        });

        try {
          // Fetch template by slug ID
          const response = await strategyClient.getTemplate({ templateId });
          const template = response.template;
          if (!template) {
            throw new Error('Template not found');
          }

          // Parse the S-expression DSL
          const parsed = fromDSLString(template.configSexpr);
          if (!parsed) {
            throw new Error('Failed to parse template DSL');
          }

          const { tree, metadata } = parsed;

          set((state) => {
            state.strategyId = null; // New strategy from template
            state.pendingTemplateId = templateId; // Track template for URL update after save
            state.strategyName = metadata.name || template.name;
            state.strategyDescription = template.description || '';
            state.timeframe = metadata.timeframe || '1D';
            state.benchmark = metadata.benchmark ?? '';

            state.tree = tree;
            state.viewMode = 'split';

            // Update root block name
            const root = tree.blocks[tree.rootId];
            if (root && root.type === 'root') {
              root.name = state.strategyName;
            }

            // Expand all parent blocks
            const expandedBlocks = new Set<BlockId>();
            for (const block of Object.values(tree.blocks)) {
              if (hasChildren(block)) {
                expandedBlocks.add(block.id);
              }
            }
            state.ui.expandedBlocks = expandedBlocks;

            state.isDirty = true; // Mark dirty since it's not saved yet
            state.loading = false;
            state.past = [];
            state.future = [];
            runValidation(state);
          });
        } catch (error) {
          set((state) => {
            state.error = error instanceof Error ? error.message : 'Failed to load template';
            state.loading = false;
          });
        }
      },

      loadFromDSL: (dslCode, name, description) => {
        const parsed = fromDSLString(dslCode);
        if (!parsed) {
          set((state) => {
            state.error = 'Failed to parse strategy DSL';
            state.loading = false;
          });
          return false;
        }

        const { tree, metadata } = parsed;

        set((state) => {
          state.strategyId = null; // New strategy, not saved yet
          state.strategyName = name || metadata.name || 'Untitled Strategy';
          state.strategyDescription = description || metadata.description || '';
          state.timeframe = metadata.timeframe || '1D';
          state.benchmark = metadata.benchmark ?? '';

          state.tree = tree;
          state.viewMode = 'split';

          // Update root block name
          const root = tree.blocks[tree.rootId];
          if (root && root.type === 'root') {
            root.name = state.strategyName;
          }

          // Expand all parent blocks
          const expandedBlocks = new Set<BlockId>();
          for (const block of Object.values(tree.blocks)) {
            if (hasChildren(block)) {
              expandedBlocks.add(block.id);
            }
          }
          state.ui.expandedBlocks = expandedBlocks;

          state.isDirty = true; // Mark dirty since it's not saved yet
          state.loading = false;
          state.past = [];
          state.future = [];
          runValidation(state);
        });

        return true;
      },

      loadFromArtifact: async (artifactId: string) => {
        set((state) => {
          state.loading = true;
          state.error = null;
        });

        try {
          const context = getTenantContext();
          const response = await agentClient.getArtifact({ context, artifactId });
          const artifact = response.artifact;

          if (!artifact) {
            throw new Error('Artifact not found');
          }

          // If already committed, redirect to the strategy
          if (artifact.isCommitted && artifact.committedResourceId) {
            window.location.href = `/strategies/${artifact.committedResourceId}`;
            return;
          }

          // Parse the preview JSON to get DSL code
          const preview = JSON.parse(artifact.previewJson) as {
            dsl_code?: string;
            name?: string;
            description?: string;
            timeframe?: string;
          };

          if (!preview.dsl_code) {
            throw new Error('Artifact has no DSL code');
          }

          const parsed = fromDSLString(preview.dsl_code);
          if (!parsed) {
            set((state) => {
              state.error = 'Failed to parse artifact DSL';
              state.loading = false;
            });
            return;
          }

          const { tree, metadata } = parsed;

          set((state) => {
            state.strategyId = null; // Not saved yet
            state.pendingArtifactId = artifactId;
            state.strategyName = artifact.name || metadata.name || 'Untitled Strategy';
            state.strategyDescription = artifact.description || metadata.description || '';
            state.timeframe = metadata.timeframe || '1D';
            state.benchmark = metadata.benchmark ?? '';

            state.tree = tree;
            state.viewMode = 'split';

            // Update root block name
            const root = tree.blocks[tree.rootId];
            if (root && root.type === 'root') {
              root.name = state.strategyName;
            }

            // Expand all parent blocks
            const expandedBlocks = new Set<BlockId>();
            for (const block of Object.values(tree.blocks)) {
              if (hasChildren(block)) {
                expandedBlocks.add(block.id);
              }
            }
            state.ui.expandedBlocks = expandedBlocks;

            state.isDirty = true; // Mark dirty since not saved yet
            state.loading = false;
            state.past = [];
            state.future = [];
            runValidation(state);
          });
        } catch (error) {
          set((state) => {
            state.error = error instanceof Error ? error.message : 'Failed to load artifact';
            state.loading = false;
          });
        }
      },

      saveStrategy: async () => {
        const state = get();

        // Validate tree before saving
        const validation = validateTree(state.tree);
        if (!validation.valid) {
          set((s) => {
            s.error = validation.errors.map((e) => e.message).join(', ');
          });
          return null;
        }

        set((s) => {
          s.saving = true;
          s.error = null;
        });

        try {
          // The DSL string is the single source of truth; the tree is derived from it on load.
          const dslCode = toDSL(state.tree, dslMetadata(state));
          const context = getTenantContext();

          let savedStrategyId: string;
          let savedName: string = state.strategyName;

          if (state.strategyId) {
            // Update existing
            const response = await strategyClient.updateStrategy({
              context,
              strategyId: state.strategyId,
              name: state.strategyName,
              description: state.strategyDescription || undefined,
              dslCode,
            });
            savedStrategyId = response.strategy?.id ?? state.strategyId;
            savedName = response.strategy?.name ?? state.strategyName;
          } else {
            // Create new
            const response = await strategyClient.createStrategy({
              context,
              name: state.strategyName,
              description: state.strategyDescription || undefined,
              dslCode,
            });
            if (!response.strategy?.id) {
              throw new Error('Failed to create strategy');
            }
            savedStrategyId = response.strategy.id;
            savedName = response.strategy.name;
          }

          // Check if this was from an artifact or template before updating state
          const wasFromArtifact = state.pendingArtifactId !== null;
          const wasFromTemplate = state.pendingTemplateId !== null;

          set((s) => {
            s.strategyId = savedStrategyId;
            s.strategyName = savedName;
            // Update root block name if it was changed by backend
            const rootBlock = s.tree.blocks[s.tree.rootId];
            if (rootBlock && rootBlock.type === 'root') {
              rootBlock.name = savedName;
            }
            s.isDirty = false;
            s.saving = false;
            // Clear pending artifact/template reference after save
            s.pendingArtifactId = null;
            s.pendingTemplateId = null;
            // Update version tracking after successful save
            s.serverVersion += 1;
            s.lastSavedAt = Date.now();
            s.conflictDetected = false;
          });

          // If this was from an artifact or template, update URL to reflect saved strategy
          if (wasFromArtifact || wasFromTemplate) {
            window.history.replaceState(null, '', `/strategies/${savedStrategyId}`);
          }

          return savedStrategyId;
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : 'Failed to save strategy';
          // Check for version conflict errors
          const isConflict = errorMessage.includes('version') || errorMessage.includes('conflict');
          set((s) => {
            s.error = errorMessage;
            s.saving = false;
            if (isConflict) {
              s.conflictDetected = true;
            }
          });
          return null;
        }
      },

      // Debounced save - useful for auto-save on frequent changes
      saveStrategyDebounced: () => {
        // Clear any existing timer
        if (saveDebounceTimer) {
          clearTimeout(saveDebounceTimer);
        }
        // Set new timer
        saveDebounceTimer = setTimeout(() => {
          const { isDirty, strategyId, saving } = get();
          // Only save if dirty, has ID (not new), and not already saving
          if (isDirty && strategyId && !saving) {
            get().saveStrategy();
          }
          saveDebounceTimer = null;
        }, DEBOUNCE_SAVE_MS);
      },

      // Cancel any pending debounced save
      cancelDebouncedSave: () => {
        if (saveDebounceTimer) {
          clearTimeout(saveDebounceTimer);
          saveDebounceTimer = null;
        }
      },

      // Resolve version conflict
      resolveConflict: async (useLocal: boolean) => {
        const state = get();
        if (!state.conflictDetected || !state.strategyId) return;

        if (useLocal) {
          // Force-save local changes over the server version.
          set((s) => {
            s.conflictDetected = false;
            s.error = null;
          });
          // Re-fetch to get latest version, then save
          try {
            const context = getTenantContext();
            const response = await strategyClient.getStrategy({
              context,
              strategyId: state.strategyId
            });
            const strategy = response.strategy;
            if (strategy) {
              set((s) => {
                s.serverVersion = strategy.version || 1;
              });
            }
            // Now save with updated version
            await get().saveStrategy();
          } catch {
            set((s) => {
              s.error = 'Failed to resolve conflict';
            });
          }
        } else {
          // Discard local changes and reload from server
          try {
            await get().loadStrategy(state.strategyId);
          } catch {
            set((s) => {
              s.error = 'Failed to reload strategy';
            });
          }
        }
      },

      createNew: () => {
        // Cancel any pending debounced save
        if (saveDebounceTimer) {
          clearTimeout(saveDebounceTimer);
          saveDebounceTimer = null;
        }
        const rootId = uuidv4();
        set((state) => {
          state.loading = false;
          state.saving = false;
          state.tree = {
            rootId,
            blocks: {
              [rootId]: {
                id: rootId,
                type: 'root',
                parentId: null,
                name: 'New Strategy',
                childIds: [],
              },
            },
          };
          state.ui = {
            selectedBlockId: null,
            expandedBlocks: new Set([rootId]),
            editingBlockId: null,
          };
          state.viewMode = 'tree';
          state.dslCode = '';
          state.dslParseError = null;
          state.past = [];
          state.future = [];
          state.strategyId = null;
          state.pendingArtifactId = null;
          state.pendingTemplateId = null;
          state.strategyName = 'New Strategy';
          state.strategyDescription = '';
          state.timeframe = '1D';
          state.benchmark = '';
          state.isDirty = false;
          state.serverVersion = 0;
          state.lastSavedAt = null;
          state.conflictDetected = false;
          state.error = null;
          state.validationResult = emptyValidationResult;
          state.isValid = true;
          runValidation(state);
        });
      },

      // Validation operations
      getBlockErrors: (blockId) => {
        const { validationResult } = get();
        return validationResult.errors.filter((e) => e.blockId === blockId);
      },

      getBlockWarnings: (blockId) => {
        const { validationResult } = get();
        return validationResult.warnings.filter((w) => w.blockId === blockId);
      },

      refreshValidation: () => {
        set((state) => {
          runValidation(state);
        });
      },
    }))
);

/**
 * Tree → code live bind. Whenever the tree changes while a code surface is
 * visible (code or split), regenerate the DSL buffer — unless the change came
 * from a code→tree commit (guarded by `suppressTreeToCode`), which would
 * otherwise reformat the user's in-progress code.
 */
useStrategyBuilderStore.subscribe((state, prev) => {
  if (state.tree === prev.tree) return;
  if (suppressTreeToCode) return;
  if (state.viewMode !== 'code' && state.viewMode !== 'split') return;
  const dsl = toDSL(state.tree, dslMetadata(state));
  if (dsl !== state.dslCode) {
    useStrategyBuilderStore.setState((s) => {
      s.dslCode = dsl;
    });
  }
});

// Scoped Store Pattern for Inline Previews

/**
 * Type for a scoped strategy builder store instance
 */
export type StrategyBuilderStoreInstance = ReturnType<typeof createStrategyBuilderStore>;

/**
 * Create a new strategy builder store instance with the given initial tree.
 * Used for inline previews that need isolated state.
 *
 * @param initialTree - The strategy tree to initialize with
 * @param previewId - Optional ID for view mode persistence (e.g., artifact ID)
 */
export function createStrategyBuilderStore(initialTree?: StrategyTree, previewId?: string) {
  // Use provided tree or create empty initial state
  const initState = initialTree
    ? {
        tree: initialTree,
        expandedBlocks: new Set(
          Object.values(initialTree.blocks)
            .filter((b) => hasChildren(b))
            .map((b) => b.id)
        ),
      }
    : createInitialState();

  // Restore view mode from localStorage if previewId is provided
  const storedViewMode = previewId ? getStoredViewMode(previewId) : 'tree';

  // Generate initial DSL code if starting in code view
  const initialDslCode = storedViewMode === 'code' && initialTree
    ? toDSL(initState.tree, {
        name: initialTree.blocks[initialTree.rootId]?.type === 'root'
          ? (initialTree.blocks[initialTree.rootId] as { name: string }).name
          : 'Preview Strategy',
        description: '',
        timeframe: '1D',
        benchmark: undefined,
      })
    : '';

  return createStore<StrategyBuilderState>()(
    immer((set, get) => ({
      tree: initState.tree,
      ui: {
        selectedBlockId: null,
        expandedBlocks: initState.expandedBlocks,
        editingBlockId: null,
      },

      // View mode state - restore from localStorage if previewId provided
      viewMode: storedViewMode,
      compactView: true, // Default to compact for inline previews
      dslCode: initialDslCode,
      dslParseError: null,

      past: [],
      future: [],

      // Strategy metadata
      strategyId: null,
      pendingArtifactId: null,
      pendingTemplateId: null,
      strategyName: initialTree?.blocks[initialTree.rootId]?.type === 'root'
        ? (initialTree.blocks[initialTree.rootId] as { name: string }).name
        : 'Preview Strategy',
      strategyDescription: '',
      timeframe: '1D',
      benchmark: '',
      isDirty: false,

      // Version tracking
      serverVersion: 0,
      lastSavedAt: null,
      conflictDetected: false,

      // Async state
      loading: false,
      saving: false,
      error: null,

      // Validation state
      validationResult: emptyValidationResult,
      isValid: true,

      // Preview stores are read-only — most actions are no-ops.

      addAsset: () => '',
      addGroup: () => '',
      addWeight: () => '',
      updateBlock: () => {},
      deleteBlock: () => {},
      setWeightAllocation: () => {},
      addCondition: () => '',
      updateCondition: () => {},
      addFilter: () => '',
      updateFilter: () => {},

      selectBlock: (id) => {
        set((state) => {
          state.ui.selectedBlockId = id;
        });
      },

      toggleExpand: (id) => {
        set((state) => {
          if (state.ui.expandedBlocks.has(id)) {
            state.ui.expandedBlocks.delete(id);
          } else {
            state.ui.expandedBlocks.add(id);
          }
        });
      },

      setEditing: () => {},

      setStrategyName: () => {},
      setStrategyDescription: () => {},
      setTimeframe: () => {},
      setBenchmark: () => {},

      undo: () => {},
      redo: () => {},
      canUndo: () => false,
      canRedo: () => false,

      loadStrategy: async () => {},
      loadTemplate: async () => {},
      loadFromDSL: () => false,
      loadFromArtifact: async () => {},
      saveStrategy: async () => null,
      saveStrategyDebounced: () => {},
      cancelDebouncedSave: () => {},
      resolveConflict: async () => {},
      createNew: () => {},

      setViewMode: (mode) => {
        const state = get();
        if (mode === state.viewMode) return;

        if (mode === 'code' || mode === 'split') {
          // Switching to a code-visible view: generate DSL from tree
          const dslCode = state.getDSLCode();
          set((s) => {
            s.viewMode = mode;
            s.dslCode = dslCode;
            s.dslParseError = null;
          });
        } else {
          // Switching to tree view (preview is read-only, just switch view)
          set((s) => {
            s.viewMode = 'tree';
          });
        }
        // Persist view mode if previewId was provided
        if (previewId) {
          saveViewMode(previewId, mode);
        }
      },
      toggleCompactView: () => {
        set((s) => {
          s.compactView = !s.compactView;
        });
      },
      updateDSLCode: () => {},
      syncTreeFromCode: () => false,
      commitCodeToTree: () => {},
      getDSLCode: () => {
        const state = get();
        return toDSL(state.tree, dslMetadata(state));
      },
      clearDSLParseError: () => {},

      getBlockErrors: () => [],
      getBlockWarnings: () => [],
      refreshValidation: () => {},

      getBlock: (id) => get().tree.blocks[id],
      getParent: (id) => {
        const block = get().tree.blocks[id];
        if (!block || !block.parentId) return undefined;
        const parent = get().tree.blocks[block.parentId];
        return parent && hasChildren(parent) ? parent : undefined;
      },
      reset: () => {},
      clearError: () => {},
    }))
  );
}

/**
 * Context for providing a scoped strategy builder store.
 * When provided, components using useStrategyBuilderStoreWithContext will use the scoped store.
 */
export const StrategyBuilderStoreContext = createContext<StrategyBuilderStoreInstance | null>(null);

/**
 * Hook to access strategy builder store, preferring scoped store if available.
 *
 * Uses a single useStore call with either the scoped store (from context)
 * or the global store, avoiding conditional hook calls.
 *
 * @param selector - Optional selector function to extract part of the state
 */
export function useStrategyBuilderStoreWithContext<T = StrategyBuilderState>(
  selector?: (state: StrategyBuilderState) => T
): T {
  const scopedStore = useContext(StrategyBuilderStoreContext);

  // Zustand's create() hook doubles as a store reference, so it can be passed to useStore.
  const effectiveSelector = selector ?? ((state: StrategyBuilderState) => state as unknown as T);

  return useStore(scopedStore ?? useStrategyBuilderStore, effectiveSelector);
}

/**
 * Export the state type for external use
 */
export type { StrategyBuilderState };
