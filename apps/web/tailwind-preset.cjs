/**
 * LlamaTrade Tailwind preset. Every value is a reference into src/styles/tokens.css, which holds
 * the colours as RGB channels so opacity modifiers work (`bg-accent/40`).
 *
 * The legacy Monolith keys (ink, bone, paper, orange, green, red, blue, gray, warning, block,
 * primary, success, danger) are transition aliases onto the semantic tokens. They go once
 * `grep -rE "(bg|text|border)-(ink|bone|paper|orange-)" src` is clean.
 */

const c = (name) => `rgb(var(--${name}) / <alpha-value>)`;
const tint = (name, amount) => `rgb(var(--${name}) / calc(<alpha-value> * ${amount}))`;

const STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];
const TINTS = { 50: 0.08, 100: 0.14, 200: 0.24, 300: 0.45, 400: 0.75 };
const legacyRamp = (name) =>
  Object.fromEntries(STEPS.map((s) => [s, TINTS[s] ? tint(name, TINTS[s]) : c(name)]));

const GRAY = {
  50: 'sunk',
  100: 'sunk',
  200: 'line',
  300: 'line-strong',
  400: 'fg-3',
  500: 'fg-3',
  600: 'fg-2',
  700: 'fg-2',
  800: 'fg',
  900: 'fg',
  950: 'fg',
};

const accentRamp = legacyRamp('accent');
const gainRamp = legacyRamp('gain');
const lossRamp = legacyRamp('loss');

/** @type {Partial<import('tailwindcss').Config>} */
module.exports = {
  // Tokens adapt per mode, so `dark:` variants stay inert (no element carries .dark).
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        canvas: c('canvas'),
        panel: c('panel'),
        sunk: c('sunk'),
        line: { DEFAULT: c('line'), strong: c('line-strong') },
        fg: { DEFAULT: c('fg'), 2: c('fg-2'), 3: c('fg-3') },
        accent: {
          DEFAULT: c('accent'),
          fill: c('accent-fill'),
          ink: c('accent-ink'),
          soft: 'var(--accent-soft)',
          ...accentRamp,
        },
        gain: c('gain'),
        loss: c('loss'),
        risk: { DEFAULT: c('risk'), soft: 'var(--risk-soft)', line: 'var(--risk-line)' },
        chart: {
          1: c('chart-1'),
          2: c('chart-2'),
          3: c('chart-3'),
          4: c('chart-4'),
          5: c('chart-5'),
        },
        grid: c('grid'),
        hatch: 'var(--hatch)',

        ink: c('fg'),
        bone: c('canvas'),
        paper: c('panel'),
        orange: accentRamp,
        primary: accentRamp,
        blue: accentRamp,
        green: gainRamp,
        red: lossRamp,
        success: { 50: gainRamp[50], 500: gainRamp[500], 600: gainRamp[600] },
        danger: { 50: lossRamp[50], 500: lossRamp[500], 600: lossRamp[600] },
        warning: { 50: tint('risk', 0.1), 500: c('risk'), 600: c('risk') },
        block: { else: c('sunk'), weight: tint('accent', 0.14) },
        gray: Object.fromEntries(STEPS.map((s) => [s, c(GRAY[s])])),
      },
      fontFamily: {
        sans: 'var(--font-sans)',
        mono: 'var(--font-mono)',
        display: 'var(--font-display)',
      },
      fontSize: {
        xs: ['0.75rem', { lineHeight: '1rem' }],
        sm: ['0.8125rem', { lineHeight: '1.25rem' }],
        base: ['0.875rem', { lineHeight: '1.5rem' }],
        lg: ['1rem', { lineHeight: '1.5rem' }],
        xl: ['1.125rem', { lineHeight: '1.75rem' }],
        '2xl': ['1.25rem', { lineHeight: '1.75rem' }],
        '3xl': ['1.5rem', { lineHeight: '2rem' }],
      },
      borderWidth: {
        3: '3px',
      },
      letterSpacing: {
        display: 'var(--display-tracking)',
      },
      borderRadius: {
        sm: 'var(--radius-sm)',
        DEFAULT: 'var(--radius)',
        md: 'var(--radius-panel)',
        lg: 'var(--radius-window)',
        r: 'var(--radius)',
        panel: 'var(--radius-panel)',
        window: 'var(--radius-window)',
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        DEFAULT: 'var(--shadow)',
        md: 'var(--shadow)',
        lg: 'var(--shadow-lg)',
        xl: 'var(--shadow-xl)',
        '2xl': 'var(--shadow-xl)',
        dropdown: 'var(--shadow-lg)',
        block: 'var(--shadow-sm)',
      },
      borderColor: {
        DEFAULT: 'rgb(var(--line) / <alpha-value>)',
      },
      ringColor: {
        // A function, because Tailwind parses the default ring colour and cannot parse var().
        DEFAULT: ({ opacityValue }) =>
          opacityValue === undefined
            ? 'rgb(var(--accent))'
            : `rgb(var(--accent) / ${opacityValue})`,
      },
      ringOffsetColor: {
        DEFAULT: 'rgb(var(--canvas))',
      },
      maxWidth: {
        content: '1384px',
      },
    },
  },
};
