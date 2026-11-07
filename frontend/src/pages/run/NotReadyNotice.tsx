import { Link } from 'react-router-dom'
import type { RunStatus } from '../../api'
import { isCancelled } from '../../api'

type NotReadyNoticeProps = {
  run: RunStatus | null
}

/**
 * Вкладки результатов до `ready` объясняют, чего ждут, и ведут в журнал.
 * Частичные результаты не показываем: до готовности витрина отвечает 409 `not_ready`
 * (так в договоре), и это не баг.
 *
 * `null` — значит прогон готов и вкладке нечего прикрывать.
 */
export function NotReadyNotice({ run }: NotReadyNoticeProps) {
  if (run === null || run.status === 'ready') return null

  const cancelled = isCancelled(run.error)
  const failed = run.status === 'error' && !cancelled

  const title = cancelled
    ? 'Запуск остановлен — результатов нет'
    : failed
      ? 'Запуск не дошёл до конца — результатов нет'
      : 'Отчёт будет доступен после завершения обработки'

  return (
    <div className="panel">
      <p>{title}</p>
      <p className="muted">
        Что происходит прямо сейчас, видно в <Link to="../log">журнале этапов</Link>.
      </p>
    </div>
  )
}
