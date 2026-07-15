import { resolve } from 'node:path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  define: {
    'process.env.NODE_ENV': JSON.stringify('production'),
  },
  build: {
    outDir: resolve(__dirname, 'docs/assets/graph-runtime'),
    emptyOutDir: true,
    cssCodeSplit: false,
    lib: {
      entry: resolve(__dirname, 'graph-runtime/src/index.ts'),
      name: 'WeConductGraphRuntime',
      formats: ['iife'],
      fileName: () => 'weconduct-graph.js',
      cssFileName: 'weconduct-graph',
    },
  },
})
