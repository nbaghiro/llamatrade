import { enableMapSet } from 'immer';
import { v4 as uuidv4 } from 'uuid';
import { create } from 'zustand';
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
import type { StrategyType } from '../types/strategy';
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

// Maximum history entries for undo/redo
const MAX_HISTORY = 50;

// Debounce delay for auto-save (in milliseconds)
const DEBOUNCE_SAVE_MS = 2000;

// Debounce timer reference
let saveDebounceTimer: ReturnType<typeof setTimeout> | null = null;

// Create demo strategy with all block types
function createInitialState(): { tree: StrategyTree; expandedBlocks: Set<BlockId> } {
  // Generate all IDs upfront
  const rootId = uuidv4();
  const weightSpecifiedId = uuidv4();
  const coreGroupId = uuidv4();
  const growthGroupId = uuidv4();
  const bondsGroupId = uuidv4();
  const coreWeightId = uuidv4();
  const growthWeightId = uuidv4();
  const spyId = uuidv4();
  const vtiId = uuidv4();
  const qqqId = uuidv4();
  const arkkId = uuidv4();
  const bndId = uuidv4();
  const tltId = uuidv4();

  const blocks: Record<BlockId, Block> = {
    // Root
    [rootId]: {
      id: rootId,
      type: 'root',
      parentId: null,
      name: 'Core Satellite Strategy',
      childIds: [weightSpecifiedId],
    },

    // Top-level specified weight
    [weightSpecifiedId]: {
      id: weightSpecifiedId,
      type: 'weight',
      parentId: rootId,
      method: 'specified',
      allocations: {
        [coreGroupId]: 60,
        [growthGroupId]: 25,
        [bondsGroupId]: 15,
      },
      childIds: [coreGroupId, growthGroupId, bondsGroupId],
    },

    // Core Group (60%)
    [coreGroupId]: {
      id: coreGroupId,
      type: 'group',
      parentId: weightSpecifiedId,
      name: 'Core Holdings',
      childIds: [coreWeightId],
    },

    // Equal weight inside Core
    [coreWeightId]: {
      id: coreWeightId,
      type: 'weight',
      parentId: coreGroupId,
      method: 'equal',
      allocations: {},
      childIds: [spyId, vtiId],
    },

    // Core assets
    [spyId]: {
      id: spyId,
      type: 'asset',
      parentId: coreWeightId,
      symbol: 'SPY',
      exchange: 'NYSEARCA',
      displayName: 'SPDR S&P 500 ETF Trust',
    },
    [vtiId]: {
      id: vtiId,
      type: 'asset',
      parentId: coreWeightId,
      symbol: 'VTI',
      exchange: 'NYSEARCA',
      displayName: 'Vanguard Total Stock Market ETF',
    },

    // Growth Group (25%)
    [growthGroupId]: {
      id: growthGroupId,
      type: 'group',
      parentId: weightSpecifiedId,
      name: 'Growth',
      childIds: [growthWeightId],
    },

    // Inverse volatility weight inside Growth
    [growthWeightId]: {
      id: growthWeightId,
      type: 'weight',
      parentId: growthGroupId,
      method: 'inverse_volatility',
      allocations: {},
      lookbackDays: 30,
      childIds: [qqqId, arkkId],
    },

    // Growth assets
    [qqqId]: {
      id: qqqId,
      type: 'asset',
      parentId: growthWeightId,
      symbol: 'QQQ',
      exchange: 'NASDAQ',
      displayName: 'Invesco QQQ Trust',
    },
    [arkkId]: {
      id: arkkId,
      type: 'asset',
      parentId: growthWeightId,
      symbol: 'ARKK',
      exchange: 'NYSEARCA',
      displayName: 'ARK Innovation ETF',
    },

    // Bonds Group (15%)
    [bondsGroupId]: {
      id: bondsGroupId,
      type: 'group',
      parentId: weightSpecifiedId,
      name: 'Bonds',
      childIds: [bndId, tltId],
    },

    // Bond assets (directly under group, no weight)
    [bndId]: {
      id: bndId,
      type: 'asset',
      parentId: bondsGroupId,
      symbol: 'BND',
      exchange: 'NYSEARCA',
      displayName: 'Vanguard Total Bond Market ETF',
    },
    [tltId]: {
      id: tltId,
      type: 'asset',
      parentId: bondsGroupId,
      symbol: 'TLT',
      exchange: 'NASDAQ',
      displayName: 'iShares 20+ Year Treasury Bond ETF',
    },
  };

  // Expand all parent blocks by default for demo
  const expandedBlocks = new Set([
    rootId,
    weightSpecifiedId,
    coreGroupId,
    growthGroupId,
    bondsGroupId,
    coreWeightId,
    growthWeightId,
  ]);

  return {
    tree: { rootId, blocks },
    expandedBlocks,
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
  dslCode: string;
  dslParseError: string | null;

  // History for undo/redo
  past: StrategyTree[];
  future: StrategyTree[];

  // Strategy metadata
  strategyId: string | null;
  strategyName: string;
  strategyDescription: string;
  strategyType: StrategyType;
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
  setStrategyType: (type: StrategyType) => void;
  setTimeframe: (timeframe: string) => void;

  // History operations
  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;

  // Backend operations
  loadStrategy: (id: string) => Promise<void>;
  loadTemplate: (templateId: string) => Promise<void>;
  saveStrategy: () => Promise<string | null>;
  saveStrategyDebounced: () => void;  // Debounced save for frequent updates
  cancelDebouncedSave: () => void;    // Cancel pending debounced save
  resolveConflict: (useLocal: boolean) => Promise<void>;  // Handle version conflicts
  createNew: () => void;

  // View mode operations
  setViewMode: (mode: ViewMode) => void;
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
    dslCode: '',
    dslParseError: null,

    past: [],
    future: [],

    // Strategy metadata
    strategyId: null,
    strategyName: 'Untitled Strategy',
    strategyDescription: '',
    strategyType: 'custom' as StrategyType,
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
          if (metadata.strategyType) {
            s.strategyType = metadata.strategyType;
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
        const { tree, strategyName, strategyDescription, strategyType, timeframe } = get();
        return toDSL(tree, {
          name: strategyName,
          description: strategyDescription,
          strategyType,
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
          state.strategyType = 'custom';
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

      setStrategyType: (type) => {
        set((state) => {
          state.strategyType = type;
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
            // StrategyType is frontend-only categorization; strategies default to 'custom'
            state.strategyType = 'custom';
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

            // Expand all parent blocks
            const expandedBlocks = new Set<BlockId>();
            for (const block of Object.values(tree.blocks)) {
              if (hasChildren(block)) {
                expandedBlocks.add(block.id);
              }
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
            // StrategyType is frontend-only categorization; templates default to 'custom'
            state.strategyType = 'custom';
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
            strategyType: state.strategyType,
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
          }

          set((s) => {
            s.strategyId = savedStrategyId;
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
          state.strategyType = 'custom';
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
