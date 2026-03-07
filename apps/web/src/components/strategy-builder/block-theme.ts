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
// THEME 1: Green Blue - Green weights, blue IF, purple ELSE
// =============================================================================
const greenBlue: ThemeColors = {
  name: 'Green Blue',
  description: 'Green weights, blue conditionals',
  weight: {
    bg: 'bg-green-600/85 dark:bg-green-600/90',
    hover: 'hover:bg-green-500/90 dark:hover:bg-green-500/95',
    ring: 'ring-green-400/50 dark:ring-green-400/50',
  },
  ifBlock: {
    bg: 'bg-blue-600/85 dark:bg-blue-600/90',
    hover: 'hover:bg-blue-500/90 dark:hover:bg-blue-500/95',
    ring: 'ring-blue-400/50 dark:ring-blue-400/50',
  },
  elseBlock: {
    bg: 'bg-purple-500/80 dark:bg-purple-500/85',
    hover: 'hover:bg-purple-400/85 dark:hover:bg-purple-400/90',
    ring: 'ring-purple-400/50 dark:ring-purple-400/50',
  },
  filter: {
    bg: 'bg-violet-600/80 dark:bg-violet-600/85',
    hover: 'hover:bg-violet-500/85 dark:hover:bg-violet-500/90',
    ring: 'ring-violet-400/50 dark:ring-violet-400/50',
  },
  allocation: {
    bg: 'bg-blue-600/90 dark:bg-blue-600/90',
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

// =============================================================================
// THEME 2: Blue Green - Blue weights, green IF, purple ELSE
// =============================================================================
const blueGreen: ThemeColors = {
  name: 'Blue Green',
  description: 'Blue weights, green conditionals',
  weight: {
    bg: 'bg-blue-600/85 dark:bg-blue-600/90',
    hover: 'hover:bg-blue-500/90 dark:hover:bg-blue-500/95',
    ring: 'ring-blue-400/50 dark:ring-blue-400/50',
  },
  ifBlock: {
    bg: 'bg-emerald-600/85 dark:bg-emerald-600/90',
    hover: 'hover:bg-emerald-500/90 dark:hover:bg-emerald-500/95',
    ring: 'ring-emerald-400/50 dark:ring-emerald-400/50',
  },
  elseBlock: {
    bg: 'bg-violet-500/80 dark:bg-violet-500/85',
    hover: 'hover:bg-violet-400/85 dark:hover:bg-violet-400/90',
    ring: 'ring-violet-400/50 dark:ring-violet-400/50',
  },
  filter: {
    bg: 'bg-purple-600/80 dark:bg-purple-600/85',
    hover: 'hover:bg-purple-500/85 dark:hover:bg-purple-500/90',
    ring: 'ring-purple-400/50 dark:ring-purple-400/50',
  },
  allocation: {
    bg: 'bg-emerald-600/90 dark:bg-emerald-600/90',
    text: 'text-white',
  },
  group: {
    bg: 'bg-white dark:bg-gray-900',
    border: 'border-gray-200 dark:border-gray-700',
    borderHover: 'hover:border-gray-300 dark:hover:border-gray-600',
    borderSelected: 'border-blue-500 dark:border-blue-400',
    ringSelected: 'ring-2 ring-blue-500/20 dark:ring-blue-500/20',
    text: 'text-gray-900 dark:text-gray-100',
    textMuted: 'text-gray-500 dark:text-gray-400',
    icon: 'text-blue-600 dark:text-blue-400',
    expandHover: 'hover:bg-gray-50 dark:hover:bg-gray-800',
  },
  asset: {
    bg: 'bg-white dark:bg-gray-900',
    border: 'border-gray-200 dark:border-gray-700',
    borderHover: 'hover:border-gray-300 dark:hover:border-gray-600',
    borderSelected: 'border-blue-500 dark:border-blue-400',
    ringSelected: 'ring-2 ring-blue-500/20 dark:ring-blue-500/20',
    text: 'text-gray-900 dark:text-gray-100',
    textMuted: 'text-gray-500 dark:text-gray-400',
    bullet: 'border-blue-600 dark:border-blue-400',
  },
  picker: {
    asset: { bg: 'bg-blue-50 dark:bg-blue-900/30', icon: 'text-blue-600 dark:text-blue-400' },
    group: { bg: 'bg-gray-100 dark:bg-gray-800', icon: 'text-gray-500 dark:text-gray-400' },
    weight: { bg: 'bg-blue-50 dark:bg-blue-900/30', icon: 'text-blue-600 dark:text-blue-400' },
    ifElse: { bg: 'bg-emerald-50 dark:bg-emerald-900/30', icon: 'text-emerald-600 dark:text-emerald-400' },
    filter: { bg: 'bg-purple-50 dark:bg-purple-900/30', icon: 'text-purple-600 dark:text-purple-400' },
  },
};

// =============================================================================
// THEME 3: Emerald Violet - Emerald weights, violet IF, blue ELSE
// =============================================================================
const emeraldViolet: ThemeColors = {
  name: 'Emerald Violet',
  description: 'Emerald weights, violet conditionals',
  weight: {
    bg: 'bg-emerald-600/85 dark:bg-emerald-600/90',
    hover: 'hover:bg-emerald-500/90 dark:hover:bg-emerald-500/95',
    ring: 'ring-emerald-400/50 dark:ring-emerald-400/50',
  },
  ifBlock: {
    bg: 'bg-violet-600/85 dark:bg-violet-600/90',
    hover: 'hover:bg-violet-500/90 dark:hover:bg-violet-500/95',
    ring: 'ring-violet-400/50 dark:ring-violet-400/50',
  },
  elseBlock: {
    bg: 'bg-blue-500/80 dark:bg-blue-500/85',
    hover: 'hover:bg-blue-400/85 dark:hover:bg-blue-400/90',
    ring: 'ring-blue-400/50 dark:ring-blue-400/50',
  },
  filter: {
    bg: 'bg-indigo-600/80 dark:bg-indigo-600/85',
    hover: 'hover:bg-indigo-500/85 dark:hover:bg-indigo-500/90',
    ring: 'ring-indigo-400/50 dark:ring-indigo-400/50',
  },
  allocation: {
    bg: 'bg-violet-600/90 dark:bg-violet-600/90',
    text: 'text-white',
  },
  group: {
    bg: 'bg-white dark:bg-gray-900',
    border: 'border-gray-200 dark:border-gray-700',
    borderHover: 'hover:border-gray-300 dark:hover:border-gray-600',
    borderSelected: 'border-emerald-500 dark:border-emerald-400',
    ringSelected: 'ring-2 ring-emerald-500/20 dark:ring-emerald-500/20',
    text: 'text-gray-900 dark:text-gray-100',
    textMuted: 'text-gray-500 dark:text-gray-400',
    icon: 'text-emerald-600 dark:text-emerald-400',
    expandHover: 'hover:bg-gray-50 dark:hover:bg-gray-800',
  },
  asset: {
    bg: 'bg-white dark:bg-gray-900',
    border: 'border-gray-200 dark:border-gray-700',
    borderHover: 'hover:border-gray-300 dark:hover:border-gray-600',
    borderSelected: 'border-emerald-500 dark:border-emerald-400',
    ringSelected: 'ring-2 ring-emerald-500/20 dark:ring-emerald-500/20',
    text: 'text-gray-900 dark:text-gray-100',
    textMuted: 'text-gray-500 dark:text-gray-400',
    bullet: 'border-emerald-600 dark:border-emerald-400',
  },
  picker: {
    asset: { bg: 'bg-emerald-50 dark:bg-emerald-900/30', icon: 'text-emerald-600 dark:text-emerald-400' },
    group: { bg: 'bg-gray-100 dark:bg-gray-800', icon: 'text-gray-500 dark:text-gray-400' },
    weight: { bg: 'bg-emerald-50 dark:bg-emerald-900/30', icon: 'text-emerald-600 dark:text-emerald-400' },
    ifElse: { bg: 'bg-violet-50 dark:bg-violet-900/30', icon: 'text-violet-600 dark:text-violet-400' },
    filter: { bg: 'bg-indigo-50 dark:bg-indigo-900/30', icon: 'text-indigo-600 dark:text-indigo-400' },
  },
};

// =============================================================================
// THEME 4: Teal Violet - Teal weights, violet IF, blue ELSE
// =============================================================================
const tealViolet: ThemeColors = {
  name: 'Teal Violet',
  description: 'Teal weights, violet conditionals',
  weight: {
    bg: 'bg-teal-600/85 dark:bg-teal-600/90',
    hover: 'hover:bg-teal-500/90 dark:hover:bg-teal-500/95',
    ring: 'ring-teal-400/50 dark:ring-teal-400/50',
  },
  ifBlock: {
    bg: 'bg-violet-600/85 dark:bg-violet-600/90',
    hover: 'hover:bg-violet-500/90 dark:hover:bg-violet-500/95',
    ring: 'ring-violet-400/50 dark:ring-violet-400/50',
  },
  elseBlock: {
    bg: 'bg-blue-500/80 dark:bg-blue-500/85',
    hover: 'hover:bg-blue-400/85 dark:hover:bg-blue-400/90',
    ring: 'ring-blue-400/50 dark:ring-blue-400/50',
  },
  filter: {
    bg: 'bg-indigo-600/80 dark:bg-indigo-600/85',
    hover: 'hover:bg-indigo-500/85 dark:hover:bg-indigo-500/90',
    ring: 'ring-indigo-400/50 dark:ring-indigo-400/50',
  },
  allocation: {
    bg: 'bg-violet-600/90 dark:bg-violet-600/90',
    text: 'text-white',
  },
  group: {
    bg: 'bg-white dark:bg-gray-900',
    border: 'border-gray-200 dark:border-gray-700',
    borderHover: 'hover:border-gray-300 dark:hover:border-gray-600',
    borderSelected: 'border-teal-500 dark:border-teal-400',
    ringSelected: 'ring-2 ring-teal-500/20 dark:ring-teal-500/20',
    text: 'text-gray-900 dark:text-gray-100',
    textMuted: 'text-gray-500 dark:text-gray-400',
    icon: 'text-teal-600 dark:text-teal-400',
    expandHover: 'hover:bg-gray-50 dark:hover:bg-gray-800',
  },
  asset: {
    bg: 'bg-white dark:bg-gray-900',
    border: 'border-gray-200 dark:border-gray-700',
    borderHover: 'hover:border-gray-300 dark:hover:border-gray-600',
    borderSelected: 'border-teal-500 dark:border-teal-400',
    ringSelected: 'ring-2 ring-teal-500/20 dark:ring-teal-500/20',
    text: 'text-gray-900 dark:text-gray-100',
    textMuted: 'text-gray-500 dark:text-gray-400',
    bullet: 'border-teal-600 dark:border-teal-400',
  },
  picker: {
    asset: { bg: 'bg-teal-50 dark:bg-teal-900/30', icon: 'text-teal-600 dark:text-teal-400' },
    group: { bg: 'bg-gray-100 dark:bg-gray-800', icon: 'text-gray-500 dark:text-gray-400' },
    weight: { bg: 'bg-teal-50 dark:bg-teal-900/30', icon: 'text-teal-600 dark:text-teal-400' },
    ifElse: { bg: 'bg-violet-50 dark:bg-violet-900/30', icon: 'text-violet-600 dark:text-violet-400' },
    filter: { bg: 'bg-indigo-50 dark:bg-indigo-900/30', icon: 'text-indigo-600 dark:text-indigo-400' },
  },
};

// =============================================================================
// THEME REGISTRY
// =============================================================================
export const themes = {
  greenBlue,
  blueGreen,
  emeraldViolet,
  tealViolet,
} as const;

export type ThemeName = keyof typeof themes;

// Current active theme - change this to switch themes
let currentTheme: ThemeName = 'greenBlue';

export function setTheme(name: ThemeName): void {
  currentTheme = name;
  // Trigger re-render by dispatching a custom event
  window.dispatchEvent(new CustomEvent('theme-change', { detail: name }));
}

export function getTheme(): ThemeColors {
  return themes[currentTheme];
}

export function getCurrentThemeName(): ThemeName {
  return currentTheme;
}

export function getThemeNames(): ThemeName[] {
  return Object.keys(themes) as ThemeName[];
}

// =============================================================================
// BACKWARDS-COMPATIBLE EXPORTS (use getTheme() for dynamic access)
// =============================================================================

// These are kept for backwards compatibility but now pull from the active theme
export function getWeightColors(_method: string): BlockColorScheme {
  return getTheme().weight;
}

export function getIfColors(_hasIndicator: boolean): BlockColorScheme {
  return getTheme().ifBlock;
}

// Static exports that reference current theme
export const weightColors: Record<string, BlockColorScheme> = {
  get specified() { return getTheme().weight; },
  get equal() { return getTheme().weight; },
  get momentum() { return getTheme().weight; },
  get dynamic() { return getTheme().weight; },
};

export const ifColors: Record<string, BlockColorScheme> = {
  get price() { return getTheme().ifBlock; },
  get indicator() { return getTheme().ifBlock; },
};

export const elseColors: BlockColorScheme = new Proxy({} as BlockColorScheme, {
  get(_, prop) { return getTheme().elseBlock[prop as keyof BlockColorScheme]; },
});

export const filterColors: BlockColorScheme = new Proxy({} as BlockColorScheme, {
  get(_, prop) { return getTheme().filter[prop as keyof BlockColorScheme]; },
});

export const groupColors = new Proxy({} as ThemeColors['group'], {
  get(_, prop) { return getTheme().group[prop as keyof ThemeColors['group']]; },
});

export const assetColors = new Proxy({} as ThemeColors['asset'], {
  get(_, prop) { return getTheme().asset[prop as keyof ThemeColors['asset']]; },
});

export const allocationBadgeColors = new Proxy({} as { bg: string; text: string }, {
  get(_, prop) { return getTheme().allocation[prop as keyof { bg: string; text: string }]; },
});

export const pickerColors = new Proxy({} as ThemeColors['picker'], {
  get(_, prop) { return getTheme().picker[prop as keyof ThemeColors['picker']]; },
});
