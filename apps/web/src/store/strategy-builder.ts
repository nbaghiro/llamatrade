import { enableMapSet } from 'immer';
import { createContext, useContext } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { create, createStore, useStore } from 'zustand';
import { immer } from 'zustand/middleware/immer';

import { strategyClient } from '../services/grpc-client';
import {
  toDSL,
  fromDSL,
  fromDSLString,
  conditionToText,
  validateTree,
} from '../services/strategy-serializer';
import { validateStrategy, type ValidationResult, type ValidationIssue } from '../services/validation';
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
} from '../types/strategy-builder';
import { hasChildren } from '../types/strategy-builder';

import { getTenantContext } from './auth';

// Re-export validation types for consumers
export type { ValidationResult, ValidationIssue };

// Enable immer support for Map and Set
enableMapSet();

// =============================================================================
// Expand/Collapse State Persistence
// =============================================================================
const COLLAPSED_STORAGE_KEY = 'strategy-builder-collapsed';

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

    // Build path -> blockId map
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

// Debounce timer reference
let saveDebounceTimer: ReturnType<typeof setTimeout> | null = null;

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

export type ViewMode = 'tree' | 'code';

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
  strategyName: string;
  strategyDescription: string;
  timeframe: string;
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

  // History operations
  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;

  // Backend operations
  loadStrategy: (id: string) => Promise<void>;
  loadTemplate: (templateId: string) => Promise<void>;
  loadFromDSL: (dslCode: string, name?: string, description?: string) => boolean;
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
    viewMode: 'tree' as ViewMode,
    compactView: false,
    dslCode: '',
    dslParseError: null,

    past: [],
    future: [],

    // Strategy metadata
    strategyId: null,
    strategyName: 'Untitled Strategy',
    strategyDescription: '',
    timeframe: '1D',
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

        if (mode === 'code') {
          // Switching to code view: generate DSL from tree
          const dslCode = state.getDSLCode();
          set((s) => {
            s.viewMode = 'code';
            s.dslCode = dslCode;
            s.dslParseError = null;
          });
        } else {
          // Switching to tree view: parse DSL back to tree
          const success = state.syncTreeFromCode();
          if (success) {
            set((s) => {
              s.viewMode = 'tree';
            });
          }
          // If parsing failed, stay in code view (error is already set)
        }
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
      },

      syncTreeFromCode: () => {
        const { dslCode } = get();

        // Try to parse the DSL code
        const parsed = fromDSLString(dslCode);
        if (!parsed) {
          set((s) => {
            s.dslParseError = 'Invalid DSL syntax. Please check your code.';
          });
          return false;
        }

        const { tree, metadata } = parsed;

        // Validate the parsed tree
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
        const { tree, strategyName, strategyDescription, timeframe } = get();
        return toDSL(tree, {
          name: strategyName,
          description: strategyDescription,
          timeframe,
        });
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
          state.viewMode = 'tree';
          state.dslCode = '';
          state.dslParseError = null;
          state.past = [];
          state.future = [];
          state.strategyId = null;
          state.strategyName = 'Untitled Strategy';
          state.strategyDescription = '';
          state.timeframe = '1D';
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
            state.strategyName = strategy.name;
            state.strategyDescription = strategy.description || '';
            state.timeframe = strategy.timeframe;

            // Track server version for optimistic locking
            state.serverVersion = strategy.version || 1;
            state.lastSavedAt = Date.now();
            state.conflictDetected = false;

            // Convert compiled JSON to block tree
            const compiledJson = strategy.compiledJson ? JSON.parse(strategy.compiledJson) : {};
            const uiStateStr = strategy.parameters['ui_state'];
            const uiState = uiStateStr ? JSON.parse(uiStateStr) : undefined;
            const tree = fromDSL(compiledJson, uiState);
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
          // Templates use strategy service - get strategy as template
          const context = getTenantContext();
          const response = await strategyClient.getStrategy({ context, strategyId: templateId });
          const template = response.strategy;
          if (!template) {
            throw new Error('Template not found');
          }

          const compiledJson = template.compiledJson ? JSON.parse(template.compiledJson) : {};

          set((state) => {
            state.strategyId = null; // New strategy from template
            state.strategyName = template.name;
            state.strategyDescription = template.description || '';
            state.timeframe = compiledJson.timeframe || template.timeframe || '1D';

            // Convert config to block tree
            const tree = fromDSL(compiledJson);
            state.tree = tree;

            // Update root block name
            const root = tree.blocks[tree.rootId];
            if (root && root.type === 'root') {
              root.name = template.name;
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
        // Parse the DSL string
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

          state.tree = tree;

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
          const metadata = {
            name: state.strategyName,
            description: state.strategyDescription,
            timeframe: state.timeframe,
          };

          const dslCode = toDSL(state.tree, metadata);
          const context = getTenantContext();

          // Save UI state (block tree) in parameters for round-trip editing
          const uiState = JSON.stringify({
            rootId: state.tree.rootId,
            blocks: state.tree.blocks,
          });
          const parameters: Record<string, string> = {
            ui_state: uiState,
          };

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
              timeframe: state.timeframe,
              parameters,
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
              timeframe: state.timeframe,
              parameters,
            });
            if (!response.strategy?.id) {
              throw new Error('Failed to create strategy');
            }
            savedStrategyId = response.strategy.id;
            savedName = response.strategy.name;
          }

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
            // Update version tracking after successful save
            s.serverVersion += 1;
            s.lastSavedAt = Date.now();
            s.conflictDetected = false;
          });

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
          // Force save local changes, overwriting server version
          // Clear conflict flag and try saving again
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
          state.strategyName = 'New Strategy';
          state.strategyDescription = '';
          state.timeframe = '1D';
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

// =============================================================================
// Scoped Store Pattern for Inline Previews
// =============================================================================

/**
 * Type for a scoped strategy builder store instance
 */
export type StrategyBuilderStoreInstance = ReturnType<typeof createStrategyBuilderStore>;

/**
 * Create a new strategy builder store instance with the given initial tree.
 * Used for inline previews that need isolated state.
 */
export function createStrategyBuilderStore(initialTree?: StrategyTree) {
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

  return createStore<StrategyBuilderState>()(
    immer((set, get) => ({
      tree: initState.tree,
      ui: {
        selectedBlockId: null,
        expandedBlocks: initState.expandedBlocks,
        editingBlockId: null,
      },

      // View mode state - always tree for inline previews
      viewMode: 'tree' as ViewMode,
      compactView: true, // Default to compact for inline previews
      dslCode: '',
      dslParseError: null,

      past: [],
      future: [],

      // Strategy metadata
      strategyId: null,
      strategyName: initialTree?.blocks[initialTree.rootId]?.type === 'root'
        ? (initialTree.blocks[initialTree.rootId] as { name: string }).name
        : 'Preview Strategy',
      strategyDescription: '',
      timeframe: '1D',
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

      // Minimal implementations for preview stores
      // Most actions are no-ops in preview mode

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

      undo: () => {},
      redo: () => {},
      canUndo: () => false,
      canRedo: () => false,

      loadStrategy: async () => {},
      loadTemplate: async () => {},
      loadFromDSL: () => false,
      saveStrategy: async () => null,
      saveStrategyDebounced: () => {},
      cancelDebouncedSave: () => {},
      resolveConflict: async () => {},
      createNew: () => {},

      setViewMode: () => {},
      toggleCompactView: () => {},
      updateDSLCode: () => {},
      syncTreeFromCode: () => false,
      getDSLCode: () => '',
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

  // Use useStore with either scoped store or global store (as store reference)
  // Zustand's create() returns a hook that also acts as a store reference
  const effectiveSelector = selector ?? ((state: StrategyBuilderState) => state as unknown as T);

  return useStore(scopedStore ?? useStrategyBuilderStore, effectiveSelector);
}

/**
 * Export the state type for external use
 */
export type { StrategyBuilderState };
