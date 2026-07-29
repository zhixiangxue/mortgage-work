import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// base './' so the built index.html works when served by pywebview's
// bundled HTTP server (relative asset paths, no leading slash)
export default defineConfig({
  plugins: [vue()],
  base: './',
  server: {
    port: 5273,
    strictPort: true,
  },
})
