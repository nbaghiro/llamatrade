/** @type {import('tailwindcss').Config} */
export default {
  // Scan app source + shared @llamatrade/ui source so design-system component classes are generated here.
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
    '../../packages/ui/src/**/*.{ts,tsx}',
  ],
  // Monolith design tokens live in the shared preset (single source of truth); darkMode is inherited too.
  presets: [require('@llamatrade/ui/tailwind-preset')],
  // Safelist runtime-composed strategy-builder block classes (block-theme.ts) the content scanner can't see.
  safelist: [
    'bg-orange-500', 'bg-green-600', 'bg-blue-600', 'bg-ink', 'bg-bone', 'bg-paper',
    'bg-block-else', 'bg-block-weight',
    'bg-orange-100', 'bg-green-100', 'bg-blue-100',
    'hover:bg-orange-500', 'hover:bg-orange-600', 'hover:bg-green-600', 'hover:bg-green-700',
    'hover:bg-blue-600', 'hover:bg-ink', 'hover:bg-ink/5',
    'text-bone', 'text-ink', 'text-orange-500', 'text-orange-700', 'text-green-600',
    'text-green-700', 'text-blue-600', 'text-blue-700',
    'border-ink', 'border-orange-500', 'border-green-600', 'border-blue-600', 'border-l-blue-600',
    'ring-ink', 'ring-orange-500', 'bg-ink/25',
  ],
  plugins: [],
};
