import { fileURLToPath } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

/**
 * Standalone marketing build (`npm run build:marketing` → dist-marketing/),
 * deployed as its own static site (the marketing Render service points here).
 * It bundles just the public site (entry: site-next.html → src/site-next/main.tsx),
 * so no router/store/gRPC code ships. The older <MarketingPage/> still renders at
 * "/" inside the app (src/App.tsx). Tailwind +
 * PostCSS resolve via the shared tailwind.config.js / postcss.config.js.
 */
export default defineConfig({
  plugins: [react()],
  define: {
    'import.meta.env.VITE_MARKETING_STANDALONE': JSON.stringify('1'),
  },
  build: {
    outDir: 'dist-marketing',
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      input: fileURLToPath(new URL('./site-next.html', import.meta.url)),
    },
  },
});
