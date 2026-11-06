import type { ReactNode } from 'react'
import './EmptyState.css'

type EmptyStateProps = {
  title: string
  /** Что сделать дальше. Писать это обязательно: «нет данных» — не сообщение. */
  hint?: string
  /** Кнопка или ссылка на нужное действие. */
  action?: ReactNode
}

/** Пустое состояние: говорит, что сделать, а не что данных нет. */
export function EmptyState({ title, hint, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="empty-state__title">{title}</div>
      {hint && <div className="muted">{hint}</div>}
      {action && <div className="empty-state__action">{action}</div>}
    </div>
  )
}
