import { enableMapSet } from 'immer';
import { v4 as uuidv4 } from 'uuid';
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';

import { getDemoStrategy } from '../data/demo-strategies';
import { StrategyType as ProtoStrategyType } from '../generated/proto/llamatrade/v1/strategy_pb';
import { strategyClient } from '../services/grpc-client';
import { toDSL, fromDSL, fromDSLString, conditionToText, validateTree } from '../services/strategy-serializer';
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

// Enable immer support for Map and Set
enableMapSet();

// Convert proto enum to local UI type
function protoTypeToLocal(protoType: ProtoStrategyType): StrategyType {
  switch (protoType) {
    case ProtoStrategyType.DSL:
      return 'custom'; // DSL maps to custom for now
    case ProtoStrategyType.PYTHON:
      return 'custom';
    case ProtoStrategyType.TEMPLATE:
      return 'custom';
    default:
      return 'custom';
  }
}

// Convert local UI type to proto enum
function localTypeToProto(_localType: StrategyType): ProtoStrategyType {
  // All UI types are DSL-based for now
  return ProtoStrategyType.DSL;
}

// Maximum history entries for undo/redo
const MAX_HISTORY = 50;

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

interface StrategyBuilderState {
  // Tree data
  tree: StrategyTree;

  // UI state
  ui: StrategyBuilderUI;

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

  // Async state
  loading: boolean;
  saving: boolean;
  error: string | null;

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
  createNew: () => void;

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
    past: [],
    future: [],

    // Strategy metadata
    strategyId: null,
    strategyName: 'Untitled Strategy',
    strategyDescription: '',
    strategyType: 'custom' as StrategyType,
    timeframe: '1D',
    isDirty: false,

    // Async state
    loading: false,
    saving: false,
    error: null,

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
        });
      },

      setWeightAllocation: (weightId, childId, percent) => {
        set((state) => {
          const block = state.tree.blocks[weightId];
          if (!block || block.type !== 'weight') return;
          pushToHistory(state);
          block.allocations[childId] = Math.max(0, Math.min(100, percent));
          state.isDirty = true;
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
        });
      },

      redo: () => {
        set((state) => {
          const next = state.future.pop();
          if (!next) return;
          state.past.push(JSON.parse(JSON.stringify(state.tree)));
          state.tree = next;
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

      reset: () => {
        set((state) => {
          const newState = createInitialState();
          state.tree = newState.tree;
          state.ui = {
            selectedBlockId: null,
            expandedBlocks: newState.expandedBlocks,
            editingBlockId: null,
          };
          state.past = [];
          state.future = [];
          state.strategyId = null;
          state.strategyName = 'Untitled Strategy';
          state.strategyDescription = '';
          state.strategyType = 'custom';
          state.timeframe = '1D';
          state.isDirty = false;
          state.error = null;
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

        // Check for demo data FIRST to avoid API errors during development
        const demoStrategy = getDemoStrategy(id);
        if (demoStrategy) {
          // Special case: Core Satellite Strategy uses portfolio builder format
          if (demoStrategy.config_sexpr === '__PORTFOLIO_CORE_SATELLITE__') {
            const { tree, expandedBlocks } = createInitialState();
            set((state) => {
              state.strategyId = demoStrategy.id;
              state.strategyName = demoStrategy.name;
              state.strategyDescription = demoStrategy.description;
              state.strategyType = demoStrategy.type;
              state.timeframe = demoStrategy.timeframe;
              state.tree = tree;
              state.ui.expandedBlocks = expandedBlocks;
              state.isDirty = false;
              state.loading = false;
              state.past = [];
              state.future = [];
              state.error = null;
            });
            return;
          }

          // Parse the DSL to create block tree with conditions
          const parsedTree = fromDSLString(demoStrategy.config_sexpr);

          set((state) => {
            state.strategyId = demoStrategy.id;
            state.strategyName = demoStrategy.name;
            state.strategyDescription = demoStrategy.description;
            state.strategyType = demoStrategy.type;
            state.timeframe = demoStrategy.timeframe;

            if (parsedTree) {
              state.tree = parsedTree;
              // Expand all blocks
              const expandedBlocks = new Set<BlockId>();
              for (const block of Object.values(parsedTree.blocks)) {
                if (hasChildren(block)) {
                  expandedBlocks.add(block.id);
                }
              }
              state.ui.expandedBlocks = expandedBlocks;
            } else {
              // Fallback: create simple tree with just assets
              const rootId = uuidv4() as BlockId;
              const blocks: Record<BlockId, Block> = {
                [rootId]: {
                  id: rootId,
                  type: 'root',
                  parentId: null,
                  name: demoStrategy.name,
                  childIds: [],
                },
              };

              for (const symbol of demoStrategy.symbols) {
                const assetId = uuidv4() as BlockId;
                blocks[assetId] = {
                  id: assetId,
                  type: 'asset',
                  parentId: rootId,
                  symbol: symbol,
                  displayName: symbol,
                  exchange: 'NASDAQ',
                };
                (blocks[rootId] as { childIds: BlockId[] }).childIds.push(assetId);
              }

              state.tree = { rootId, blocks };
              state.ui.expandedBlocks = new Set([rootId]);
            }

            state.isDirty = false;
            state.loading = false;
            state.past = [];
            state.future = [];
            state.error = null;
          });
          return;
        }

        // If not demo, try loading from backend
        try {
          const response = await strategyClient.getStrategy({ strategyId: id });
          const strategy = response.strategy;
          if (!strategy) {
            throw new Error('Strategy not found');
          }

          set((state) => {
            state.strategyId = strategy.id;
            state.strategyName = strategy.name;
            state.strategyDescription = strategy.description || '';
            state.strategyType = protoTypeToLocal(strategy.type);
            state.timeframe = strategy.timeframe;

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
          const response = await strategyClient.getStrategy({ strategyId: templateId });
          const template = response.strategy;
          if (!template) {
            throw new Error('Template not found');
          }

          const compiledJson = template.compiledJson ? JSON.parse(template.compiledJson) : {};

          set((state) => {
            state.strategyId = null; // New strategy from template
            state.strategyName = template.name;
            state.strategyDescription = template.description || '';
            state.strategyType = protoTypeToLocal(template.type);
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

          let savedStrategyId: string;

          if (state.strategyId) {
            // Update existing
            const response = await strategyClient.updateStrategy({
              strategyId: state.strategyId,
              name: state.strategyName,
              description: state.strategyDescription || undefined,
              dslCode,
              timeframe: state.timeframe,
            });
            savedStrategyId = response.strategy?.id ?? state.strategyId;
          } else {
            // Create new
            const response = await strategyClient.createStrategy({
              name: state.strategyName,
              description: state.strategyDescription || undefined,
              type: localTypeToProto(state.strategyType),
              dslCode,
              timeframe: state.timeframe,
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
          });

          return savedStrategyId;
        } catch (error) {
          set((s) => {
            s.error = error instanceof Error ? error.message : 'Failed to save strategy';
            s.saving = false;
          });
          return null;
        }
      },

      createNew: () => {
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
          state.past = [];
          state.future = [];
          state.strategyId = null;
          state.strategyName = 'New Strategy';
          state.strategyDescription = '';
          state.strategyType = 'custom';
          state.timeframe = '1D';
          state.isDirty = false;
          state.error = null;
        });
      },
    }))
);
