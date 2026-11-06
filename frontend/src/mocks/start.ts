// Включение моков. Весь этот файл и всё, что он тянет, живёт только в деве:
// обращение к нему в main.tsx спрятано за import.meta.env.DEV, поэтому в прод-сборку
// ни msw, ни выдуманные данные не попадают.

/**
 * Моки включены, пока бэка нет. Чтобы пойти на настоящий бэк, положите рядом
 * `.env.development.local` со строкой `VITE_USE_MOCKS=0` (см. `.env.example`).
 * В прод-сборке моков нет никогда, какое бы значение ни стояло.
 */
export const MOCKS_ENABLED = import.meta.env.DEV && import.meta.env.VITE_USE_MOCKS !== '0'

export async function startMocks(): Promise<void> {
  const { setupWorker } = await import('msw/browser')
  const { handlers } = await import('./handlers')

  const worker = setupWorker(...handlers)
  await worker.start({
    // Скрипт воркера раздаёт плагин msw из vite.config.ts — в public/ его класть не надо.
    serviceWorker: { url: '/mockServiceWorker.js' },
    // Что не замокано (файлы Vite, шрифты, незнакомые ручки) — пропускаем в сеть молча.
    // Иначе консоль забивается предупреждениями, а её смотрят на защите.
    onUnhandledFrame: 'bypass',
    quiet: true,
  })
}
