import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:40419',
      '/v1': 'http://localhost:40419',
      '/health': 'http://localhost:40419',
    },
  },
  root: '.',
  build: {
    outDir: '../iflycode_proxy/static',
    emptyOutDir: true,
  },
});
