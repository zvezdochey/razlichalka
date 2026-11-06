import react from '@vitejs/plugin-react'
import { msw } from 'msw/vite'
import { defineConfig } from 'vite'

// Во фронте всегда пишем относительные адреса (/api/...), а dev-сервер
// перебрасывает их на локальный бэк. В прод-сборке /api раздаёт тот же хост.
const BACKEND_URL = 'http://localhost:8000'

export default defineConfig({
  plugins: [
    react(),
    // Раздаёт скрипт service worker'а для моков. apply: 'serve' — только дев-сервер,
    // иначе плагин кладёт скрипт воркера ещё и в прод-сборку, где он мёртвый груз.
    // worker-only: обёртку вокруг msw пишем сами в src/mocks/start.ts.
    { ...msw({ mode: 'worker-only' }), apply: 'serve' },
  ],
  server: {
    proxy: {
      '/api': {
        target: BACKEND_URL,
        changeOrigin: true,
      },
    },
  },
})
