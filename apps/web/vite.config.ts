import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // Base "/": the app is the catch-all behind the Caddy proxy. See infrastructure/docker/Caddyfile.
  server: {
    host: true,
    port: 8802,
    strictPort: true,
    // Allow the proxy Host (localhost:8800) and the in-network name so Vite's host check doesn't 403.
    allowedHosts: ['localhost', 'web'],
    // HMR runs through the proxy on :8800 (ws upgrades on "/").
    hmr: {
      clientPort: 8800,
    },
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
