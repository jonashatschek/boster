import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Boster is a static site: the Python backend runs in the browser (src/python/worker.ts),
// which bundles the files in ../backend at build time.
export default defineConfig({
  plugins: [react()],
  // Relative paths, so the site works from any folder (e.g. https://<user>.github.io/boster/).
  base: './',
  worker: { format: 'es' },
  server: {
    fs: { allow: ['..'] },
  },
})
