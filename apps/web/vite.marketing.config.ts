import { fileURLToPath } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

/**
 * Standalone marketing build (`npm run build:marketing` → dist-marketing/),
 * deployed as its own static site (the marketing Render service points here).
 * The same <MarketingPage/> also renders at "/" inside the app (src/App.tsx);
 * this config bundles just the marketing page (entry: marketing.html →
 * src/marketing/main.tsx), so no router/store/gRPC code ships. Tailwind +
 * PostCSS resolve via the shared tailwind.config.js / postcss.config.js.
 */
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist-marketing',
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      input: fileURLToPath(new URL('./marketing.html', import.meta.url)),
    },
  },
});
