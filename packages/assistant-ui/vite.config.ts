import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [vue()],
  build: {
    lib: {
      entry: 'src/index.ts',
      fileName: 'assistant-ui',
      formats: ['es'],
      name: 'VerityMeshAssistantUi',
    },
    rollupOptions: {
      external: ['vue'],
    },
  },
})
