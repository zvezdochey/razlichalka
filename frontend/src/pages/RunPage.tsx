import { NavLink, Outlet, useParams } from 'react-router-dom'
import './RunPage.css'

/** Прогон: контекст сверху, вкладки — вложенные маршруты, чтобы ссылкой можно было поделиться. */
export function RunPage() {
  const { id } = useParams<{ id: string }>()

  return (
    <>
      <div className="page-head">
        <div>
          <div className="overline">Прогон</div>
          <h1 className="mono">{id}</h1>
        </div>
      </div>

      <nav className="tabs" aria-label="Разделы прогона">
        <NavLink to="overview" className="tabs__item">
          Обзор
        </NavLink>
        <NavLink to="apps" className="tabs__item">
          Заявки
        </NavLink>
        <NavLink to="log" className="tabs__item">
          Журнал
        </NavLink>
      </nav>

      <Outlet />
    </>
  )
}
