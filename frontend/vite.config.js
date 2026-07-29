import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// base './' so the built index.html works when served by pywebview's
// bundled HTTP server (relative asset paths, no leading slash)
export default defineConfig({
  plugins: [vue()],
  base: './',
  build: {
    // The app runs inside WKWebView, which lags Safari on older macOS.
    // Pin the target so esbuild lowers any too-new syntax in dependencies
    // (a single unparseable chunk would white-screen the whole app).
    target: 'safari15',
  },
  server: {
    port: 5273,
    strictPort: true,
  },
})
