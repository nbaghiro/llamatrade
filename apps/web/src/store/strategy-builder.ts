import { enableMapSet } from 'immer';
import { v4 as uuidv4 } from 'uuid';
import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';

// Enable immer support for Map and Set
enableMapSet();

import type {
  BlockId,
  Block,
  StrategyTree,
  StrategyBuilderUI,
  WeightMethod,
  ParentBlock,
} from '../types/strategy-builder';
import { hasChildren } from '../types/strategy-builder';

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

  // UI operations
  selectBlock: (id: BlockId | null) => void;
  toggleExpand: (id: BlockId) => void;
  setEditing: (id: BlockId | null) => void;

  // History operations
  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;

  // Utility
  getBlock: (id: BlockId) => Block | undefined;
  getParent: (id: BlockId) => ParentBlock | undefined;
  reset: () => void;
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
        });
        return id;
      },

      updateBlock: (id, updates) => {
        set((state) => {
          const block = state.tree.blocks[id];
          if (!block) return;
          pushToHistory(state);
          Object.assign(block, updates);
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
        });
      },

      setWeightAllocation: (weightId, childId, percent) => {
        set((state) => {
          const block = state.tree.blocks[weightId];
          if (!block || block.type !== 'weight') return;
          pushToHistory(state);
          block.allocations[childId] = Math.max(0, Math.min(100, percent));
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
        });
      },
    }))
);
