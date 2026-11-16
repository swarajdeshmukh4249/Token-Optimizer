import { defineConfig } from 'vite';

// The Python engine (web/server.py) keeps serving the live API on :8420.
export default defineConfig({
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8420' },
  },
  preview: {
    port: 4173,
    proxy: { '/api': 'http://localhost:8420' },
  },
  build: { target: 'es2022', chunkSizeWarningLimit: 1200 },
});
