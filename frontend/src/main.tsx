import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

// Шрифты ставим локально, а не с CDN: на защите может не быть интернета.
import '@fontsource/ibm-plex-sans/cyrillic-400.css'
import '@fontsource/ibm-plex-sans/cyrillic-500.css'
import '@fontsource/ibm-plex-sans/cyrillic-600.css'
import '@fontsource/ibm-plex-sans/latin-400.css'
import '@fontsource/ibm-plex-sans/latin-500.css'
import '@fontsource/ibm-plex-sans/latin-600.css'
import '@fontsource/ibm-plex-mono/cyrillic-400.css'
import '@fontsource/ibm-plex-mono/latin-400.css'

import './styles/tokens.css'
import './styles/base.css'
import './styles/pages.css'
import { App } from './App'

const container = document.getElementById('root')
if (!container) throw new Error('Не найден элемент #root — проверьте index.html')

/** Моки поднимаем до первого рендера, иначе первые запросы уйдут в пустой бэк. */
async function startMocksIfNeeded(): Promise<void> {
  if (!import.meta.env.DEV) return
  const { MOCKS_ENABLED, startMocks } = await import('./mocks/start')
  if (MOCKS_ENABLED) await startMocks()
}

startMocksIfNeeded()
  .catch(() => {
    // Воркер не поднялся (например приватный режим браузера запретил service worker).
    // Это не повод не показать приложение: запросы просто уйдут на настоящий бэк.
  })
  .finally(() => {
    createRoot(container).render(
      <StrictMode>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </StrictMode>,
    )
  })
