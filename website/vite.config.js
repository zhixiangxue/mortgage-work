import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: './',
  build: {
    target: 'safari15',
  },
  server: {
    port: 5280,
    strictPort: true,
  },
})
