import { NotReadyNotice } from './NotReadyNotice'
import { useRunContext } from './runContext'

/** Таблица заявок. Наполняется в F6, панель заявки — в F7. */
export function AppsTab() {
  const { run } = useRunContext()
  if (run === null || run.status !== 'ready') return <NotReadyNotice run={run} />

  return <div className="panel muted">Таблица заявок появится в F6.</div>
}
