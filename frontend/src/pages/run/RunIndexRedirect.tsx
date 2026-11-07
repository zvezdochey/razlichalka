import { Navigate } from 'react-router-dom'
import { Spinner } from '../../components'
import { useRunContext } from './runContext'

/**
 * Куда вести со страницы прогона без вкладки (`/runs/:id`). Готовый прогон —
 * сразу «Обзор», идущий или упавший — «Журнал»: после запуска человек должен
 * видеть, что происходит, а не заглушку «отчёт будет позже».
 */
export function RunIndexRedirect() {
  const { run, runId } = useRunContext()

  if (run === null) {
    return (
      <div className="panel">
        <Spinner label="Открываем прогон" />
      </div>
    )
  }

  // Путь абсолютный: у index-маршрута «..» ведёт на уровень выше самого прогона.
  const tab = run.status === 'ready' ? 'overview' : 'log'
  return <Navigate to={`/runs/${encodeURIComponent(runId)}/${tab}`} replace />
}
