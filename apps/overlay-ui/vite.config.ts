import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  base: './',
  plugins: [vue()],
  build: { modulePreload: false, rollupOptions: { output: { inlineDynamicImports: true } } },
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.ts'],
  },
})
