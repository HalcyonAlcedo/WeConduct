import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'happy-dom',
    include: ['graph-runtime/src/**/*.test.ts'],
    restoreMocks: true,
  },
})
