import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// During development, API calls are forwarded to the FastAPI backend.
// Set BOSTER_API_URL to use a backend on another address.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': process.env.BOSTER_API_URL ?? 'http://127.0.0.1:8000',
    },
  },
})
