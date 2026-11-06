import { Link } from 'react-router-dom'
import { EmptyState } from '../components'

/** Список прогонов. Наполняется в F4. */
export function RunsListPage() {
  return (
    <>
      <div className="page-head">
        <h1>Прогоны</h1>
        <Link to="/runs/new" className="btn btn--primary">
          Новый прогон
        </Link>
      </div>
      <EmptyState
        title="Прогонов пока нет"
        hint="Нажмите «Новый прогон», чтобы сравнить решения двух версий СПР."
      />
    </>
  )
}
