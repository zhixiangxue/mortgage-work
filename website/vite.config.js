import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  base: './',
  build: {
    target: 'safari15',
    // Multi-page build: dist/index.html + dist/readme.html are both emitted,
    // so no manual copy into dist/ is needed.
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        readme: fileURLToPath(new URL('./readme.html', import.meta.url)),
      },
    },
  },
  server: {
    port: 5280,
    strictPort: true,
  },
})
