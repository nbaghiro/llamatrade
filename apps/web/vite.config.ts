import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 47300,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:47800',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:47800',
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
