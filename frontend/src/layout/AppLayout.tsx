import { useState, useSyncExternalStore } from 'react'
import type { FormEvent, MouseEvent } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { confirmLeave } from '../lib/leaveGuard'
import { getCurrentUser, isValidUser, setCurrentUser, subscribeUser } from '../lib/user'
import './AppLayout.css'

/** Ссылка меню не ведёт дальше, если человек отказался терять несохранённое. */
function guardLeave(event: MouseEvent<HTMLAnchorElement>) {
  if (!confirmLeave()) event.preventDefault()
}

/**
 * Имя в шапке: щёлкнул — поле ввода, сохранил — бэк видит другого `X-User`.
 * Запуски и конфигурации у каждого имени свои, поэтому без смены имени чужой
 * прогон открывается как «не найден».
 */
function UserSwitcher({ user }: { user: string }) {
  const [draft, setDraft] = useState<string | null>(null)
  const [invalid, setInvalid] = useState(false)

  function close() {
    setDraft(null)
    setInvalid(false)
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const next = (draft ?? '').trim()
    if (next === '' || next === user) {
      close()
      return
    }
    // Кириллица в заголовке X-User роняет запросы — не даём сохранить, а объясняем почему.
    if (!isValidUser(next)) {
      setInvalid(true)
      return
    }
    close()
    // Смена имени перерисует страницу заново — несохранённое на ней пропадёт.
    if (!confirmLeave()) return
    setCurrentUser(next)
  }

  if (draft === null) {
    return (
      <button
        type="button"
        className="app__user"
        title="Сменить пользователя"
        onClick={() => setDraft(user)}
      >
        {user} ▾
      </button>
    )
  }

  return (
    <form className="app__user-form" onSubmit={save}>
      <label className="visually-hidden" htmlFor="app-user">
        Имя пользователя
      </label>
      <input
        id="app-user"
        className="input app__user-input"
        value={draft}
        autoFocus
        maxLength={64}
        aria-invalid={invalid}
        aria-describedby="app-user-hint"
        onChange={(event) => {
          setDraft(event.target.value)
          setInvalid(false)
        }}
        onKeyDown={(event) => {
          if (event.key === 'Escape') close()
        }}
      />
      <span id="app-user-hint" className="app__user-hint">
        Только латиница, цифры и _ - . ; у каждого имени свои прогоны и конфигурации
      </span>
      <button type="submit" className="btn app__user-btn">
        Сохранить
      </button>
      <button type="button" className="btn app__user-btn" onClick={close}>
        Отмена
      </button>
    </form>
  )
}

/** Шапка 48 px + левое меню 180 px + область контента. Ориентир — ноутбук 1366×768. */
export function AppLayout() {
  const user = useSyncExternalStore(subscribeUser, getCurrentUser)

  return (
    <div className="app">
      <header className="app__header">
        <span className="app__brand">Различалка</span>
        <UserSwitcher user={user} />
      </header>

      <div className="app__body">
        <nav className="app__nav" aria-label="Разделы">
          <NavLink to="/runs" className="app__nav-item" onClick={guardLeave}>
            Прогоны
          </NavLink>
          <NavLink to="/procedures" className="app__nav-item" onClick={guardLeave}>
            Процедуры
          </NavLink>
          <NavLink to="/configurations" className="app__nav-item" onClick={guardLeave}>
            Конфигурации
          </NavLink>
        </nav>

        <main className="app__content">
          {/* key по имени: после смены пользователя страница грузит свои данные заново
              (список прогонов, открытый прогон), а не показывает чужие. */}
          <Outlet key={user} />
        </main>
      </div>
    </div>
  )
}
