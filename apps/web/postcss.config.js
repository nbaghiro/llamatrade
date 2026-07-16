export default {
  plugins: {
    // Inlines @llamatrade/ui @import before Tailwind so shared @layer/@apply run in the same pass.
    'postcss-import': {},
    tailwindcss: {},
    autoprefixer: {},
  },
};
