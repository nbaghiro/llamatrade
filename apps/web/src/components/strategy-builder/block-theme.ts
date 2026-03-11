// Centralized color theme for strategy builder blocks

export type BlockColorScheme = {
  bg: string;
  hover: string;
  ring: string;
};

export type PickerIconColors = {
  bg: string;
  icon: string;
};

export type ThemeColors = {
  name: string;
  description: string;
  weight: BlockColorScheme;
  ifBlock: BlockColorScheme;
  elseBlock: BlockColorScheme;
  filter: BlockColorScheme;
  allocation: { bg: string; text: string };
  group: {
    bg: string;
    border: string;
    borderHover: string;
    borderSelected: string;
    ringSelected: string;
    text: string;
    textMuted: string;
    icon: string;
    expandHover: string;
  };
  asset: {
    bg: string;
    border: string;
    borderHover: string;
    borderSelected: string;
    ringSelected: string;
    text: string;
    textMuted: string;
    bullet: string;
  };
  picker: {
    asset: PickerIconColors;
    group: PickerIconColors;
    weight: PickerIconColors;
    ifElse: PickerIconColors;
    filter: PickerIconColors;
  };
};

// =============================================================================
// Default Theme: Green Blue (Muted)
// =============================================================================
const theme: ThemeColors = {
  name: 'Green Blue',
  description: 'Green weights, blue conditionals',
  weight: {
    bg: 'bg-green-600/65 dark:bg-green-600/65',
    hover: 'hover:bg-green-500/70 dark:hover:bg-green-500/70',
    ring: 'ring-green-400/35 dark:ring-green-400/35',
  },
  ifBlock: {
    bg: 'bg-blue-600/65 dark:bg-blue-600/65',
    hover: 'hover:bg-blue-500/70 dark:hover:bg-blue-500/70',
    ring: 'ring-blue-400/35 dark:ring-blue-400/35',
  },
  elseBlock: {
    bg: 'bg-purple-500/60 dark:bg-purple-500/60',
    hover: 'hover:bg-purple-400/65 dark:hover:bg-purple-400/65',
    ring: 'ring-purple-400/35 dark:ring-purple-400/35',
  },
  filter: {
    bg: 'bg-violet-600/60 dark:bg-violet-600/60',
    hover: 'hover:bg-violet-500/65 dark:hover:bg-violet-500/65',
    ring: 'ring-violet-400/35 dark:ring-violet-400/35',
  },
  allocation: {
    bg: 'bg-blue-600/65 dark:bg-blue-600/65',
    text: 'text-white',
  },
  group: {
    bg: 'bg-white dark:bg-gray-900',
    border: 'border-gray-200 dark:border-gray-700',
    borderHover: 'hover:border-gray-300 dark:hover:border-gray-600',
    borderSelected: 'border-green-500 dark:border-green-400',
    ringSelected: 'ring-2 ring-green-500/20 dark:ring-green-500/20',
    text: 'text-gray-900 dark:text-gray-100',
    textMuted: 'text-gray-500 dark:text-gray-400',
    icon: 'text-green-600 dark:text-green-400',
    expandHover: 'hover:bg-gray-50 dark:hover:bg-gray-800',
  },
  asset: {
    bg: 'bg-white dark:bg-gray-900',
    border: 'border-gray-200 dark:border-gray-700',
    borderHover: 'hover:border-gray-300 dark:hover:border-gray-600',
    borderSelected: 'border-green-500 dark:border-green-400',
    ringSelected: 'ring-2 ring-green-500/20 dark:ring-green-500/20',
    text: 'text-gray-900 dark:text-gray-100',
    textMuted: 'text-gray-500 dark:text-gray-400',
    bullet: 'border-green-600 dark:border-green-400',
  },
  picker: {
    asset: { bg: 'bg-green-50 dark:bg-green-900/30', icon: 'text-green-600 dark:text-green-400' },
    group: { bg: 'bg-gray-100 dark:bg-gray-800', icon: 'text-gray-500 dark:text-gray-400' },
    weight: { bg: 'bg-green-50 dark:bg-green-900/30', icon: 'text-green-600 dark:text-green-400' },
    ifElse: { bg: 'bg-blue-50 dark:bg-blue-900/30', icon: 'text-blue-600 dark:text-blue-400' },
    filter: { bg: 'bg-violet-50 dark:bg-violet-900/30', icon: 'text-violet-600 dark:text-violet-400' },
  },
};

export function getTheme(): ThemeColors {
  return theme;
}
