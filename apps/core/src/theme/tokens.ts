/**
 * LlamaTrade "Monolith" design tokens — the CSS custom-property layer
 * (packages/ui/src/themes/monolith.css) mirrored as plain data so React Native
 * (and any non-CSS consumer) can read the exact same values.
 *
 * Monolith is a deliberate light-only, brutalist system:
 * bone / ink / signal-orange · Anton · Archivo · Space Mono · zero radius ·
 * hard offset shadows. Keep these in sync with monolith.css.
 */

export const palette = {
  bone: '#fbf8f1',
  ink: '#0d0d0d',
  paper: '#ffffff',
  bone2: '#f2efe6',

  orange: {
    50: '#fff1ec', 100: '#ffddd0', 200: '#ffb59e', 300: '#ff8c6b', 400: '#ff6a3d',
    500: '#ff4d1c', 600: '#e63e10', 700: '#b8300b', 800: '#8f2609', 900: '#6b1d08', 950: '#451204',
  },
  green: {
    50: '#e8f3ec', 100: '#c9e4d2', 200: '#94c9a8', 300: '#5fae7e', 400: '#2f9257',
    500: '#0f7a34', 600: '#0c6a2d', 700: '#095324', 800: '#06401c', 900: '#042e14', 950: '#021d0d',
  },
  red: {
    50: '#fbeae9', 100: '#f5c9c6', 200: '#eb9793', 300: '#e06560', 400: '#d63f39',
    500: '#c81e1e', 600: '#a81919', 700: '#841414', 800: '#631010', 900: '#46110f', 950: '#2b0a09',
  },
  blue: {
    50: '#ececff', 100: '#d0d0ff', 200: '#a3a3ff', 300: '#7676ff', 400: '#4a4aff',
    500: '#1a1aff', 600: '#1414cc', 700: '#0f0f99', 800: '#0a0a70', 900: '#070750', 950: '#040433',
  },
  gray: {
    50: '#f7f5ef', 100: '#f2efe6', 200: '#e6e1d4', 300: '#d4cdba', 400: '#a8a08c',
    500: '#7a7362', 600: '#565044', 700: '#3a352d', 800: '#221f1a', 900: '#141210', 950: '#0d0d0d',
  },
} as const;

/** Semantic aliases — point INTO the ramps above (quick-reskin levers). */
export const semantic = {
  surface: palette.bone,
  card: palette.paper,
  text: palette.ink,
  accent: palette.orange[500],
  success: palette.green[500], // up / positive
  danger: palette.red[500], // down / negative
  info: palette.blue[500],
  muted: palette.gray[500],
  line: 'rgba(13,13,13,0.14)',
  gridDot: 'rgba(13,13,13,0.10)',
} as const;

/** Strategy identity palette — a strategy keeps its color across every surface. */
export const strategyColors = [
  palette.green[500], // #0f7a34
  palette.blue[500], // #1a1aff
  palette.orange[500], // #ff4d1c
  palette.red[500], // #c81e1e
  '#6b2fb3', // violet
  '#0e8ba0', // cyan
] as const;

/** Block-editor branch fills (read-only strategy tree). */
export const blockFills = {
  else: '#e6e0d2',
  weight: '#d4eddb',
} as const;

/** Font family keys — must match the names registered with expo-font / @font-face. */
export const fonts = {
  display: 'Anton', // uppercase display face
  sans: 'Archivo', // body
  mono: 'SpaceMono', // labels + tabular data
} as const;

export const radius = 0; // brutalist: zeroed everywhere

/** Hard offset shadow depths (px). RN consumers turn these into shadow styles. */
export const shadowOffset = { sm: 2, md: 4, lg: 8, xl: 12 } as const;

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;

export const type = {
  micro: 10, label: 11, xs: 12, sm: 13, base: 14, lg: 16, xl: 18, xxl: 22, display: 30, hero: 44,
} as const;

export const tokens = {
  palette,
  semantic,
  strategyColors,
  blockFills,
  fonts,
  radius,
  shadowOffset,
  space,
  type,
} as const;

export type Tokens = typeof tokens;
