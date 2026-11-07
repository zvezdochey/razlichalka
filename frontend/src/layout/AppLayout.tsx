import { useSyncExternalStore } from 'react'
import type { MouseEvent } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { confirmLeave } from '../lib/leaveGuard'
import { getCurrentUser, subscribeUser } from '../lib/user'
import './AppLayout.css'

/** Ссылка меню не ведёт дальше, если человек отказался терять несохранённое. */
function guardLeave(event: MouseEvent<HTMLAnchorElement>) {
  if (!confirmLeave()) event.preventDefault()
}

/** Шапка 48 px + левое меню 180 px + область контента. Ориентир — ноутбук 1366×768. */
export function AppLayout() {
  const user = useSyncExternalStore(subscribeUser, getCurrentUser)

  return (
    <div className="app">
      <header className="app__header">
        <span className="app__brand">Различалка</span>
        <span className="app__user" title="Имя пользователя из localStorage">
          {user}
        </span>
      </header>

      <div className="app__body">
        <nav className="app__nav" aria-label="Разделы">
          <NavLink to="/runs" className="app__nav-item" onClick={guardLeave}>
            Прогоны
          </NavLink>
          <NavLink to="/procedures" className="app__nav-item" onClick={guardLeave}>
            Процедуры
          </NavLink>
          {/* Конфигурации как отдельный раздел — после MVP (PLAN п. 4) */}
          <span className="app__nav-item app__nav-item--disabled" aria-disabled="true">
            Конфигурации
            <span className="chip">скоро</span>
          </span>
        </nav>

        <main className="app__content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
