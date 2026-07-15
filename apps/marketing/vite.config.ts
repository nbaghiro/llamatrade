import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  // Namespaced under "/m/" so the marketing assets never collide with the web
  // app's "/assets/*" on the shared single origin. The Caddy reverse proxy
  // rewrites the origin root "/" to "/m/", so this still renders at "/". See
  // infrastructure/docker/Caddyfile.
  //
  // For a truly STANDALONE static deploy at a domain root (no proxy), override
  // the base at build time: `npm run -w apps/marketing build -- --base=/`.
  base: '/m/',
  server: {
    // `host: true` binds 0.0.0.0 so the dev container (docker-compose
    // `marketing` service) is reachable through the proxy and on the host.
    host: true,
    port: 8811,
    strictPort: true,
    // Behind the proxy the browser sends Host: localhost:8800; allow it (plus
    // the in-network service name) so Vite's host check doesn't 403.
    allowedHosts: ['localhost', 'marketing'],
    // HMR reaches this dev server THROUGH the proxy on :8800. The client's ws
    // path is the base ("/m/"), which the proxy routes to this dev server.
    hmr: {
      clientPort: 8800,
    },
  },
  build: {
    // Self-contained static site — the whole `dist/` deploys behind the proxy
    // under "/m/" (or at a root with `--base=/`, see above).
    outDir: 'dist',
    sourcemap: true,
  },
});
