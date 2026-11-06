import { isCancelled } from '../api'
import type { ApiError, Status } from '../api/types'
import './StatusBadge.css'

type StatusBadgeProps = {
  status: Status
  /**
   * Объект ошибки запуска, если он известен (п. 5.2). По `code: 'cancelled'`
   * отличаем остановку пользователем от настоящего падения.
   */
  error?: ApiError | null
  /**
   * `false` — поля `error` в этом ответе нет вообще (так в списке запусков, п. 5.3),
   * значит про причину мы ничего не знаем и не имеем права называть её аварией.
   */
  errorKnown?: boolean
}

type Look = {
  label: string
  /** Значок — только довесок к подписи, читать статус можно и без него. */
  icon: string
  /** Красным красим исключительно настоящее падение: цвет здесь не оценка данных. */
  tone: 'neutral' | 'running' | 'done' | 'danger'
  title?: string
}

const BY_STATUS: Record<Exclude<Status, 'error'>, Look> = {
  pending: { label: 'В очереди', icon: '·', tone: 'neutral' },
  running: { label: 'Идёт расчёт', icon: '•', tone: 'running' },
  ready: { label: 'Готов', icon: '✓', tone: 'done' },
}

const CANCELLED: Look = { label: 'Остановлен', icon: '■', tone: 'neutral' }
const FAILED: Look = { label: 'Ошибка', icon: '!', tone: 'danger' }
const UNFINISHED: Look = {
  label: 'Не завершён',
  icon: '!',
  tone: 'neutral',
  title: 'Остановлен или упал — причина видна на странице прогона',
}

/** Как выглядит этот статус. Вынесено, чтобы решение «что красное» жило в одном месте. */
function statusLook(status: Status, error?: ApiError | null, errorKnown = true): Look {
  if (status !== 'error') return BY_STATUS[status]
  if (!errorKnown) return UNFINISHED
  return isCancelled(error) ? CANCELLED : FAILED
}

/** Статус запуска или этапа: значок плюс подпись, без «цвет вместо текста». */
export function StatusBadge({ status, error = null, errorKnown = true }: StatusBadgeProps) {
  const look = statusLook(status, error, errorKnown)

  return (
    <span className={`status status--${look.tone}`} title={look.title}>
      <span className="status__icon" aria-hidden="true">
        {look.icon}
      </span>
      {look.label}
    </span>
  )
}
