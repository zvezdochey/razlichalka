/// <reference types="vite/client" />
/// <reference types="msw/vite/client" />

/** Переменные окружения проекта. Все они перечислены в `.env.example`. */
interface ImportMetaEnv {
  /** `0` — выключить моки и пойти на настоящий бэк. Работает только в деве. */
  readonly VITE_USE_MOCKS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
