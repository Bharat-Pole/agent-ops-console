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
      '/v1': 'http://localhost:8787',
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Split the heavy charting + routing vendors into their own chunks.
        manualChunks: {
          recharts: ['recharts'],
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
        },
      },
    },
  },
});
