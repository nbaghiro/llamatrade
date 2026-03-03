/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  // Safelist for dynamically-generated classes in block-theme.ts
  // Option E: Tricolor Distinct (Emerald/Blue/Violet)
  safelist: [
    // Weight block colors (green with opacity)
    'bg-green-600/80', 'dark:bg-green-600/80',
    'hover:bg-green-600/90', 'dark:hover:bg-green-700/90',
    'ring-green-300', 'ring-green-400',
    // If/Else block colors (blue)
    'bg-blue-400', 'bg-blue-500', 'bg-blue-600',
    'hover:bg-blue-500', 'hover:bg-blue-600', 'hover:bg-blue-700',
    'ring-blue-200', 'ring-blue-300', 'ring-blue-400',
    // Picker icon colors
    'bg-emerald-100', 'dark:bg-emerald-900/40', 'text-emerald-500', 'dark:text-emerald-400',
    'bg-blue-100', 'dark:bg-blue-900/40', 'text-blue-500', 'dark:text-blue-400',
    'bg-violet-100', 'dark:bg-violet-900/40', 'text-violet-500', 'dark:text-violet-400',
    'bg-gray-100', 'dark:bg-gray-800',
    // Asset block colors (emerald accents)
    'border-emerald-500', 'ring-emerald-500/20', 'dark:ring-emerald-600/20',
    // Group block colors (blue accents)
    'border-blue-500', 'ring-blue-500/20', 'dark:ring-blue-600/20',
    // Filter block colors (violet)
    'bg-violet-50', 'dark:bg-violet-900/20',
    'border-violet-200', 'dark:border-violet-800',
    'border-violet-500', 'dark:border-violet-600',
    'ring-violet-500/20', 'dark:ring-violet-600/20',
    'hover:border-violet-300', 'dark:hover:border-violet-700',
    'hover:bg-violet-100', 'dark:hover:bg-violet-800/50',
    'text-violet-500', 'dark:text-violet-400',
    'text-violet-600', 'dark:text-violet-300',
    'text-violet-900', 'dark:text-violet-100',
  ],
  theme: {
    extend: {
      colors: {
        // Primary: Green (Composer-style)
        primary: {
          50: '#f0fdf4',
          100: '#dcfce7',
          200: '#bbf7d0',
          300: '#86efac',
          400: '#4ade80',
          500: '#22c55e',
          600: '#16a34a',
          700: '#15803d',
          800: '#166534',
          900: '#14532d',
          950: '#052e16',
        },
        // Accent: Pink/Magenta (for conditionals, special elements)
        accent: {
          50: '#fdf2f8',
          100: '#fce7f3',
          200: '#fbcfe8',
          300: '#f9a8d4',
          400: '#f472b6',
          500: '#ec4899',
          600: '#db2777',
          700: '#be185d',
          800: '#9d174d',
          900: '#831843',
        },
        // Semantic
        success: {
          50: '#f0fdf4',
          500: '#22c55e',
          600: '#16a34a',
        },
        danger: {
          50: '#fef2f2',
          500: '#ef4444',
          600: '#dc2626',
        },
        warning: {
          50: '#fffbeb',
          500: '#f59e0b',
          600: '#d97706',
        },
        // Gray scale (neutral, clean)
        gray: {
          50: '#fafafa',
          100: '#f5f5f5',
          200: '#e5e5e5',
          300: '#d4d4d4',
          400: '#a3a3a3',
          500: '#737373',
          600: '#525252',
          700: '#404040',
          800: '#262626',
          900: '#171717',
          950: '#0a0a0a',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
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
      boxShadow: {
        'sm': '0 1px 2px 0 rgb(0 0 0 / 0.05)',
        'DEFAULT': '0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)',
        'md': '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
        'lg': '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
        'dropdown': '0 4px 16px rgb(0 0 0 / 0.12)',
      },
      borderRadius: {
        'DEFAULT': '6px',
        'lg': '8px',
        'xl': '12px',
      },
    },
  },
  plugins: [],
};
