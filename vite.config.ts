import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      // Same-origin API in dev: the httpOnly session cookie rides along with
      // SameSite=Lax and no CORS setup. Compose overrides the target to the
      // backend service; bare `npm run dev` hits a locally-run backend.
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Split the heavy charting + routing vendors into their own chunks.
        manualChunks: {
          recharts: ['recharts'],
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          xyflow: ['@xyflow/react'],
        },
      },
    },
  },
});
