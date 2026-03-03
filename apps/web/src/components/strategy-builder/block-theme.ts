// Centralized color theme for strategy builder blocks
// Update colors here to change them across all block components
//
// OPTION E: "Tricolor Distinct" (Light mode optimized)
// Each block category gets exactly one brand color - maximum differentiation
// - Weight → Emerald (growth/money)
// - IF/ELSE → Blue (logic/decisions)
// - Filter → Violet (selection/filtering)
//
// Light mode uses -500 shades, dark mode uses -600 shades

export type BlockColorScheme = {
  bg: string;
  hover: string;
  ring: string;
};

export type PickerIconColors = {
  bg: string;
  icon: string;
};

// =============================================================================
// PICKER ICON COLORS (Add Block menu) - Clear color separation
// =============================================================================
export const pickerColors = {
  asset: {
    bg: 'bg-emerald-100 dark:bg-emerald-900/40',
    icon: 'text-emerald-500 dark:text-emerald-400',
  },
  group: {
    bg: 'bg-gray-100 dark:bg-gray-800',
    icon: 'text-blue-500 dark:text-blue-400',
  },
  weight: {
    bg: 'bg-emerald-100 dark:bg-emerald-900/40',
    icon: 'text-emerald-500 dark:text-emerald-400',
  },
  ifElse: {
    bg: 'bg-blue-100 dark:bg-blue-900/40',
    icon: 'text-blue-500 dark:text-blue-400',
  },
  filter: {
    bg: 'bg-violet-100 dark:bg-violet-900/40',
    icon: 'text-violet-500 dark:text-violet-400',
  },
};

// =============================================================================
// WEIGHT BLOCK COLORS - Green (with opacity for softer look)
// =============================================================================
export const weightColors: Record<string, BlockColorScheme> = {
  specified: {
    bg: 'bg-green-600/80 dark:bg-green-600/80',
    hover: 'hover:bg-green-600/90 dark:hover:bg-green-700/90',
    ring: 'ring-green-300 dark:ring-green-400',
  },
  equal: {
    bg: 'bg-green-600/80 dark:bg-green-600/80',
    hover: 'hover:bg-green-600/90 dark:hover:bg-green-700/90',
    ring: 'ring-green-300 dark:ring-green-400',
  },
  momentum: {
    bg: 'bg-green-600/80 dark:bg-green-600/80',
    hover: 'hover:bg-green-600/90 dark:hover:bg-green-700/90',
    ring: 'ring-green-300 dark:ring-green-400',
  },
  dynamic: {
    bg: 'bg-green-600/80 dark:bg-green-600/80',
    hover: 'hover:bg-green-600/90 dark:hover:bg-green-700/90',
    ring: 'ring-green-300 dark:ring-green-400',
  },
};

export function getWeightColors(method: string): BlockColorScheme {
  if (method === 'specified') return weightColors.specified;
  if (method === 'equal') return weightColors.equal;
  if (method === 'momentum') return weightColors.momentum;
  return weightColors.dynamic;
}

// =============================================================================
// IF BLOCK COLORS - Blue
// =============================================================================
export const ifColors: Record<string, BlockColorScheme> = {
  price: {
    bg: 'bg-blue-500 dark:bg-blue-600',
    hover: 'hover:bg-blue-600 dark:hover:bg-blue-700',
    ring: 'ring-blue-300 dark:ring-blue-400',
  },
  indicator: {
    bg: 'bg-blue-500 dark:bg-blue-600',
    hover: 'hover:bg-blue-600 dark:hover:bg-blue-700',
    ring: 'ring-blue-300 dark:ring-blue-400',
  },
};

export function getIfColors(hasIndicator: boolean): BlockColorScheme {
  return hasIndicator ? ifColors.indicator : ifColors.price;
}

// =============================================================================
// ELSE BLOCK COLORS - Blue (slightly lighter)
// =============================================================================
export const elseColors: BlockColorScheme = {
  bg: 'bg-blue-400 dark:bg-blue-500',
  hover: 'hover:bg-blue-500 dark:hover:bg-blue-600',
  ring: 'ring-blue-200 dark:ring-blue-300',
};

// =============================================================================
// FILTER BLOCK COLORS - Violet pill (inline style like Weight)
// =============================================================================
export const filterColors: BlockColorScheme = {
  bg: 'bg-violet-500 dark:bg-violet-600',
  hover: 'hover:bg-violet-600 dark:hover:bg-violet-700',
  ring: 'ring-violet-300 dark:ring-violet-400',
};

// =============================================================================
// GROUP BLOCK COLORS - Gray with blue icon
// =============================================================================
export const groupColors = {
  bg: 'bg-white dark:bg-gray-900',
  border: 'border-gray-200 dark:border-gray-700',
  borderHover: 'hover:border-gray-300 dark:hover:border-gray-600',
  borderSelected: 'border-blue-500 dark:border-blue-500',
  ringSelected: 'ring-2 ring-blue-500/20 dark:ring-blue-600/20',
  text: 'text-gray-900 dark:text-gray-100',
  textMuted: 'text-gray-500 dark:text-gray-400',
  icon: 'text-blue-500 dark:text-blue-400',
  expandHover: 'hover:bg-gray-50 dark:hover:bg-gray-800',
};

// =============================================================================
// ASSET BLOCK COLORS - Gray with emerald bullet
// =============================================================================
export const assetColors = {
  bg: 'bg-white dark:bg-gray-900',
  border: 'border-gray-200 dark:border-gray-700',
  borderHover: 'hover:border-gray-300 dark:hover:border-gray-600',
  borderSelected: 'border-emerald-500 dark:border-emerald-500',
  ringSelected: 'ring-2 ring-emerald-500/20 dark:ring-emerald-600/20',
  text: 'text-gray-900 dark:text-gray-100',
  textMuted: 'text-gray-500 dark:text-gray-400',
  bullet: 'border-emerald-500 dark:border-emerald-500',
};

// =============================================================================
// ALLOCATION BADGE COLORS - Blue
// =============================================================================
export const allocationBadgeColors = {
  bg: 'bg-blue-500 dark:bg-blue-600',
  text: 'text-white',
};
