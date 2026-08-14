import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  build: {
    lib: {
      entry: 'src/index.tsx',
      fileName: 'assistant-ui',
      formats: ['es'],
      name: 'VerityMeshAssistantUi',
    },
    rollupOptions: {
      external: ['react', 'react-dom', 'react-dom/client'],
    },
  },
})
