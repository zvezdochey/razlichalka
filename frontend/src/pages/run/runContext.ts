import { useOutletContext } from 'react-router-dom'
import type { RunStatus } from '../../api'

/**
 * Что вкладки получают от страницы прогона. Статус опрашивает только `RunPage`:
 * иначе каждая вкладка завела бы свой цикл опроса одной и той же ручки.
 */
export type RunContext = {
  runId: string
  /** `null` — статус ещё не пришёл (первая загрузка) или запрос не удался. */
  run: RunStatus | null
  /** Перечитать статус вне расписания опроса: после отмены или повторного запуска. */
  reloadRun: () => void
}

export function useRunContext(): RunContext {
  return useOutletContext<RunContext>()
}
