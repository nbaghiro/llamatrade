/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './marketing.html', './src/**/*.{js,ts,jsx,tsx}'],
  presets: [require('./tailwind-preset.cjs')],
  plugins: [],
};
