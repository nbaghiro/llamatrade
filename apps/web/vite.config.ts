import { existsSync } from 'node:fs';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// Behind the Caddy proxy (Docker) the HMR socket goes through :8800; a bare host run on :8802 uses its own port.
const hmrClientPort = process.env.HMR_CLIENT_PORT
  ? Number(process.env.HMR_CLIENT_PORT)
  : existsSync('/.dockerenv')
    ? 8800
    : undefined;

export default defineConfig({
  plugins: [react()],
  test: {
    // Explicit environment + include so an empty collection is a config bug,
    // not a silent pass (CI runs without --passWithNoTests).
    environment: 'node',
    include: ['src/**/__tests__/**/*.test.{ts,tsx}'],
  },
  // Base "/": the app is the catch-all behind the Caddy proxy. See infrastructure/docker/Caddyfile.
  server: {
    host: true,
    port: 8802,
    strictPort: true,
    // Allow the proxy Host (localhost:8800) and the in-network name so Vite's host check doesn't 403.
    allowedHosts: ['localhost', 'web'],
    hmr: hmrClientPort ? { clientPort: hmrClientPort } : undefined,
    // Poll: the bind-mounted app source (macOS→Linux Docker) emits no native fs events.
    watch: {
      usePolling: true,
      interval: 120,
    },
    // No proxy: the frontend connects directly to services via Connect (they handle CORS).
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
