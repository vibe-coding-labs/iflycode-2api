import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:9090',
      '/v1': 'http://localhost:9090',
      '/health': 'http://localhost:9090',
    },
  },
  root: '.',
  build: {
    outDir: '../iflycode_proxy/static',
    emptyOutDir: true,
  },
});
