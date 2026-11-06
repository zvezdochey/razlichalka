import { Link } from 'react-router-dom'
import { EmptyState } from '../components'

/** Неизвестный адрес. Нужен и для прямых ссылок из HTML-отчёта. */
export function NotFoundPage() {
  return (
    <EmptyState
      title="Такой страницы нет"
      hint="Проверьте адрес или вернитесь к списку прогонов."
      action={
        <Link to="/runs" className="btn">
          К списку прогонов
        </Link>
      }
    />
  )
}
