/**
 * LlamaTrade "Monolith" Tailwind preset.
 *
 * This preset maps Tailwind's theme keys onto the CSS custom-property TOKEN
 * LAYER defined in `src/themes/monolith.css` — that file is the single source of
 * truth for every themeable value (palette, type, radius, shadows). Nothing here
 * holds a raw hex/px value that a theme would want to change; each entry is a
 * `var(--lt-*)` reference, so swapping the theme file (or a `[data-theme]` block)
 * reskins the whole product with zero preset edits.
 *
 * Colors use the `rgb(var(--lt-<name>) / <alpha-value>)` form so Tailwind opacity
 * modifiers keep working: `bg-orange-500/50` -> `rgb(var(--lt-orange-500) / 0.5)`.
 * The theme file therefore stores colors as space-separated RGB channels
 * (`255 77 28`), NOT as `#ff4d1c`. See that file's header for the full rationale.
 *
 * Consume from a Vite app's `tailwind.config.js`:
 *   presets: [require('@llamatrade/ui/tailwind-preset')]
 * and import the token layer FIRST in the app's entry CSS:
 *   @import '@llamatrade/ui/themes/monolith.css';
 *
 * Authored as CommonJS (`module.exports`) so it is `require()`-able from an ESM
 * `tailwind.config.js` (Tailwind loads the config in a CJS context).
 *
 * Monolith is a light-only system — `darkMode: 'class'` here keeps any stale
 * `dark:` variants inert unless a `.dark` class is explicitly present.
 */

/** Build an 11-step ramp of `rgb(var(--lt-<name>-<step>) / <alpha-value>)`. */
const ramp = (name, steps) =>
  Object.fromEntries(
    steps.map((step) => [step, `rgb(var(--lt-${name}-${step}) / <alpha-value>)`]),
  );

const FULL_STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950];

const orange = ramp('orange', FULL_STEPS);
const blue = ramp('blue', FULL_STEPS);
const green = ramp('green', FULL_STEPS);
const red = ramp('red', FULL_STEPS);
const gray = ramp('gray', FULL_STEPS);

/** @type {Partial<import('tailwindcss').Config>} */
module.exports = {
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // ---- Monolith core ----
        bone: 'rgb(var(--lt-bone) / <alpha-value>)',
        ink: 'rgb(var(--lt-ink) / <alpha-value>)',
        paper: 'rgb(var(--lt-paper) / <alpha-value>)',
        // Hairline rule carries a baked 14% alpha — mapped straight through (no
        // <alpha-value> slot, matching its prior rgba() behaviour).
        line: 'var(--lt-line)',
        // Signal orange = primary/brand accent
        orange,
        // primary repointed to signal orange (brand/primary usages become orange)
        primary: orange,
        // accent repointed from pink -> electric blue
        accent: blue,
        // green = success / up (Monolith #0f7a34)
        green,
        // red = danger / down (Monolith #c81e1e)
        red,
        // blue = info / links (Monolith #1a1aff)
        blue,
        success: { 50: green[50], 500: green[500], 600: green[600] },
        danger: { 50: red[50], 500: red[500], 600: red[600] },
        warning: {
          50: orange[50], // #fff1ec — identical to orange-50
          500: 'rgb(var(--lt-warning-500) / <alpha-value>)',
          600: 'rgb(var(--lt-warning-600) / <alpha-value>)',
        },
        // Block-editor branch fills (StrategyTree). Exposed as named colors so
        // `bg-block-else` / `bg-block-weight` keep Tailwind's opacity machinery.
        block: {
          else: 'rgb(var(--lt-block-else-bg) / <alpha-value>)',
          weight: 'rgb(var(--lt-block-weight-bg) / <alpha-value>)',
        },
        // Warm ink-biased neutral ramp (bone -> ink). Repoints all gray-* usages.
        gray,
      },
      fontFamily: {
        display: 'var(--lt-font-display)',
        sans: 'var(--lt-font-sans)',
        mono: 'var(--lt-font-mono)',
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
      // Hard offset shadows — every shadow-* utility becomes a brutalist drop.
      // Values live in the token layer (built from the ink channels).
      boxShadow: {
        sm: 'var(--lt-shadow-sm)',
        DEFAULT: 'var(--lt-shadow)',
        md: 'var(--lt-shadow)',
        lg: 'var(--lt-shadow-lg)',
        xl: 'var(--lt-shadow-lg)',
        '2xl': 'var(--lt-shadow-xl)',
        inner: 'var(--lt-shadow-inner)',
        dropdown: 'var(--lt-shadow)',
        // Bone-tinted drop the StrategyTree blocks cast on the ink ground.
        // A named utility (`shadow-block`) so Tailwind treats it as a box-shadow
        // (a bare `shadow-[var(...)]` would be misread as a shadow *color*).
        block: 'var(--lt-block-shadow)',
        none: 'none',
      },
      // Zero radius everywhere — every rounded-* utility flattens (token-driven).
      borderRadius: {
        none: 'var(--lt-radius)',
        sm: 'var(--lt-radius)',
        DEFAULT: 'var(--lt-radius)',
        md: 'var(--lt-radius)',
        lg: 'var(--lt-radius)',
        xl: 'var(--lt-radius)',
        '2xl': 'var(--lt-radius)',
        '3xl': 'var(--lt-radius)',
        full: 'var(--lt-radius)',
      },
      // Border/ring scale stays fixed (not theme-swappable); only their default
      // colors are tokenized.
      borderWidth: {
        DEFAULT: '1px',
        3: '3px',
      },
      borderColor: {
        DEFAULT: 'rgb(var(--lt-ink) / <alpha-value>)',
      },
      ringColor: {
        // A color FUNCTION (not the `<alpha-value>` string form): Tailwind builds
        // the global `*` ring-reset default via `withAlphaValue`, which PARSES the
        // color and cannot parse a `var()`-based one — it would silently fall back
        // to Tailwind's built-in blue. The function is invoked with the resolved
        // opacity, so the reset stays tokenized orange @ 0.5, matching the prior
        // hardcoded `#ff4d1c`. (The `ring-<color>` utilities come from `colors`.)
        DEFAULT: ({ opacityValue }) =>
          opacityValue === undefined
            ? 'rgb(var(--lt-orange-500))'
            : `rgb(var(--lt-orange-500) / ${opacityValue})`,
      },
    },
  },
};
