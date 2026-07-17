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

const theme: ThemeColors = {
  name: 'Monolith',
  description: 'Brutalist — green weights, orange conditionals & filters, blue assets',
  // Palette matches the shared StrategyTree; each block carries a hard 2px ink border.
  weight: {
    bg: 'bg-green-600 text-bone border-2 border-ink',
    hover: 'hover:bg-green-700',
    ring: 'ring-orange-500',
  },
  ifBlock: {
    bg: 'bg-orange-500 text-ink border-2 border-ink',
    hover: 'hover:bg-orange-600',
    ring: 'ring-ink',
  },
  elseBlock: {
    bg: 'bg-block-else text-ink border-2 border-ink',
    hover: 'hover:bg-ink/5',
    ring: 'ring-orange-500',
  },
  filter: {
    bg: 'bg-orange-500 text-ink border-2 border-ink',
    hover: 'hover:bg-orange-600',
    ring: 'ring-ink',
  },
  allocation: {
    bg: 'bg-ink border-2 border-ink',
    text: 'text-bone',
  },
  group: {
    bg: 'bg-paper',
    border: 'border-2 border-ink',
    borderHover: 'hover:border-ink',
    borderSelected: 'border-orange-500',
    ringSelected: 'ring-2 ring-orange-500',
    text: 'text-ink',
    textMuted: 'text-ink/50',
    icon: 'text-green-600',
    expandHover: 'hover:bg-ink/5',
  },
  asset: {
    bg: 'bg-paper',
    border: 'border-2 border-ink',
    borderHover: 'hover:border-ink',
    borderSelected: 'border-orange-500',
    ringSelected: 'ring-2 ring-orange-500',
    text: 'text-ink',
    textMuted: 'text-ink/50',
    bullet: 'border-blue-600',
  },
  picker: {
    asset: { bg: 'bg-blue-100 border-2 border-ink', icon: 'text-blue-700' },
    group: { bg: 'bg-bone border-2 border-ink', icon: 'text-ink' },
    weight: { bg: 'bg-green-100 border-2 border-ink', icon: 'text-green-700' },
    ifElse: { bg: 'bg-orange-100 border-2 border-ink', icon: 'text-orange-700' },
    filter: { bg: 'bg-orange-100 border-2 border-ink', icon: 'text-orange-700' },
  },
};

export function getTheme(): ThemeColors {
  return theme;
}
