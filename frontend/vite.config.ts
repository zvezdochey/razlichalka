import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Во фронте всегда пишем относительные адреса (/api/...), а dev-сервер
// перебрасывает их на локальный бэк. В прод-сборке /api раздаёт тот же хост.
const BACKEND_URL = 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: BACKEND_URL,
        changeOrigin: true,
      },
    },
  },
})
