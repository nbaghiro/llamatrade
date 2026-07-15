/** @type {import('tailwindcss').Config} */
export default {
  // Scan the app source AND the shared @llamatrade/ui package source, so the
  // design-system components' classes (StrategyTree/Marquee/Logo, etc.) used by
  // the marketing page are generated in this app's build.
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
    '../../packages/ui/src/**/*.{ts,tsx}',
  ],
  // The Monolith design tokens (palette, type, zeroed radius, hard shadows,
  // border scale) live in the shared preset — the single source of truth.
  // `darkMode: 'class'` is also inherited from the preset.
  presets: [require('@llamatrade/ui/tailwind-preset')],
  // No safelist needed: the marketing page's own styling is bespoke CSS
  // (marketing.css), and the shared components' token-backed classes appear
  // literally in packages/ui/src (already scanned above).
  plugins: [],
};
