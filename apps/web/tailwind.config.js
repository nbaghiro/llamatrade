/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './marketing.html', './src/**/*.{js,ts,jsx,tsx}'],
  presets: [require('./tailwind-preset.cjs')],
  theme: {
    extend: {
      keyframes: {
        rise: {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to: { opacity: '1', transform: 'none' },
        },
        bob: {
          '50%': { opacity: '0.5', transform: 'translateY(-3px)' },
        },
      },
      animation: {
        rise: 'rise 0.42s cubic-bezier(0.2, 0.7, 0.2, 1) both',
        bob: 'bob 1s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
