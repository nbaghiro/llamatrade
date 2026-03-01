import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 8800,
    strictPort: true,
    // No proxy needed - frontend connects directly to services via Connect protocol
    // Services handle CORS themselves
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
