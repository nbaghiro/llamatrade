export default {
  plugins: {
    // Inlines the theme/@layer @import before Tailwind so shared @layer/@apply run in the same pass.
    'postcss-import': {},
    tailwindcss: {},
    autoprefixer: {},
  },
};
