import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const server = {
  host: '0.0.0.0',
  port: 5173,
  // Vite 6+ exposes `allowedHosts` in its types; the value is harmless on Vite 5.
  allowedHosts: true,
  proxy: {
    '/api': {
      target: 'http://127.0.0.1:8000',
      changeOrigin: false,
    },
  },
} as Record<string, unknown>;

export default defineConfig({
  plugins: [react()],
  server,
  build: { outDir: 'dist', sourcemap: false },
});
