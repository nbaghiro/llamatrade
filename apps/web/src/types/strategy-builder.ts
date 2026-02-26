// Strategy Builder Type Definitions

export type BlockId = string;
export type BlockType = 'root' | 'asset' | 'group' | 'weight';
export type WeightMethod =
  | 'specified'
  | 'equal'
  | 'inverse_volatility'
  | 'market_cap'
  | 'momentum'
  | 'min_variance';

// Base block interface
interface BaseBlock {
  id: BlockId;
  parentId: BlockId | null;
}

// Root block - strategy container
export interface RootBlock extends BaseBlock {
  type: 'root';
  parentId: null;
  name: string;
  childIds: BlockId[];
}

// Asset block - individual stock/ETF
export interface AssetBlock extends BaseBlock {
  type: 'asset';
  parentId: BlockId;
  symbol: string;
  exchange: string;
  displayName: string;
}

// Group block - named container for organizing assets
export interface GroupBlock extends BaseBlock {
  type: 'group';
  parentId: BlockId;
  name: string;
  childIds: BlockId[];
}

// Weight block - allocation method
export interface WeightBlock extends BaseBlock {
  type: 'weight';
  parentId: BlockId;
  method: WeightMethod;
  allocations: Record<BlockId, number>; // for 'specified' method
  lookbackDays?: number; // for momentum, inverse_volatility, min_variance
  childIds: BlockId[];
}

// Union type for all blocks
export type Block = RootBlock | AssetBlock | GroupBlock | WeightBlock;

// Type guards
export function isRootBlock(block: Block): block is RootBlock {
  return block.type === 'root';
}

export function isAssetBlock(block: Block): block is AssetBlock {
  return block.type === 'asset';
}

export function isGroupBlock(block: Block): block is GroupBlock {
  return block.type === 'group';
}

export function isWeightBlock(block: Block): block is WeightBlock {
  return block.type === 'weight';
}

// Blocks that can have children
export type ParentBlock = RootBlock | GroupBlock | WeightBlock;

export function hasChildren(block: Block): block is ParentBlock {
  return block.type === 'root' || block.type === 'group' || block.type === 'weight';
}

// Strategy tree structure
export interface StrategyTree {
  rootId: BlockId;
  blocks: Record<BlockId, Block>;
}

// UI state
export interface StrategyBuilderUI {
  selectedBlockId: BlockId | null;
  expandedBlocks: Set<BlockId>;
  editingBlockId: BlockId | null;
}

// Weight method metadata for UI
export interface WeightMethodInfo {
  method: WeightMethod;
  label: string;
  description: string;
  hasLookback: boolean;
  color: {
    bg: string;
    text: string;
    border: string;
  };
}

export const WEIGHT_METHODS: WeightMethodInfo[] = [
  {
    method: 'specified',
    label: 'Specified',
    description: 'Fixed percentage allocations',
    hasLookback: false,
    color: { bg: 'bg-blue-100 dark:bg-blue-900', text: 'text-blue-700 dark:text-blue-300', border: 'border-blue-200 dark:border-blue-800' },
  },
  {
    method: 'equal',
    label: 'Equal Weight',
    description: 'Split evenly across children',
    hasLookback: false,
    color: { bg: 'bg-green-100 dark:bg-green-900', text: 'text-green-700 dark:text-green-300', border: 'border-green-200 dark:border-green-800' },
  },
  {
    method: 'inverse_volatility',
    label: 'Inverse Volatility',
    description: 'Risk parity weighting',
    hasLookback: true,
    color: { bg: 'bg-purple-100 dark:bg-purple-900', text: 'text-purple-700 dark:text-purple-300', border: 'border-purple-200 dark:border-purple-800' },
  },
  {
    method: 'market_cap',
    label: 'Market Cap',
    description: 'Cap-weighted allocation',
    hasLookback: false,
    color: { bg: 'bg-orange-100 dark:bg-orange-900', text: 'text-orange-700 dark:text-orange-300', border: 'border-orange-200 dark:border-orange-800' },
  },
  {
    method: 'momentum',
    label: 'Momentum',
    description: 'Momentum-weighted allocation',
    hasLookback: true,
    color: { bg: 'bg-pink-100 dark:bg-pink-900', text: 'text-pink-700 dark:text-pink-300', border: 'border-pink-200 dark:border-pink-800' },
  },
  {
    method: 'min_variance',
    label: 'Min Variance',
    description: 'Minimum variance optimization',
    hasLookback: true,
    color: { bg: 'bg-cyan-100 dark:bg-cyan-900', text: 'text-cyan-700 dark:text-cyan-300', border: 'border-cyan-200 dark:border-cyan-800' },
  },
];

export function getWeightMethodInfo(method: WeightMethod): WeightMethodInfo {
  const info = WEIGHT_METHODS.find((m) => m.method === method);
  if (!info) {
    throw new Error(`Unknown weight method: ${method}`);
  }
  return info;
}

// Node position for connector rendering
export interface NodePosition {
  blockId: BlockId;
  x: number;
  y: number;
  width: number;
  height: number;
}

// Connector path data
export interface ConnectorPath {
  parentId: BlockId;
  childId: BlockId;
  path: string;
}
