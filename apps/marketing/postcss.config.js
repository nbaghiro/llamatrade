export default {
  plugins: {
    // Must run BEFORE tailwindcss: it inlines `@import '@llamatrade/ui/styles.css'`
    // (the shared design-system @layer file) into this app's entry CSS so the
    // shared @layer/@apply rules are processed in the same Tailwind pass as the
    // `@tailwind` directives. Without this, the imported layers are dropped.
    'postcss-import': {},
    tailwindcss: {},
    autoprefixer: {},
  },
};
