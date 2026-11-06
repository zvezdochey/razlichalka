import { NotReadyNotice } from './NotReadyNotice'
import { useRunContext } from './runContext'

/** Обзор результата. Числа появятся в F5; до готовности прогона — объяснение ожидания. */
export function OverviewTab() {
  const { run } = useRunContext()
  if (run === null || run.status !== 'ready') return <NotReadyNotice run={run} />

  return <div className="panel muted">Итоговые показатели появятся в F5.</div>
}
