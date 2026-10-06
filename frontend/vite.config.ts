import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: Vite on :5173 proxies /api to FastAPI on :8000.
// Prod: `npm run build` -> dist/, served by FastAPI itself on :8000.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { events: 'events' }, // Ketcher needs the npm "events" polyfill in the browser
  },
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  build: {
    chunkSizeWarningLimit: 32000, // Ketcher + Indigo WASM is large; loaded lazily
    commonjsOptions: { transformMixedEsModules: true }, // ketcher-core calls require('raphael') inside ESM
  },
  define: {
    'process.env': {},
    global: 'globalThis', // Ketcher/Indigo expect Node's global
  },
})
