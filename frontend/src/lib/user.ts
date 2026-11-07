// Имя пользователя. Авторизации нет: бэк различает людей по заголовку X-User (его
// отправляет клиент API в F2), а здесь мы только храним и отдаём выбранное имя.
const STORAGE_KEY = 'razlichalka_user'
const DEFAULT_USER = 'demo'
const CHANGE_EVENT = 'razlichalka:user-change'

/**
 * Имя уходит в заголовок X-User, а `Headers.set` бросает ошибку на символах вне
 * Latin-1 («Семён» уронил бы все запросы). Поэтому только латиница, цифры и `._-`.
 */
const USER_PATTERN = /^[A-Za-z0-9._-]{1,64}$/

export function isValidUser(name: string): boolean {
  return USER_PATTERN.test(name)
}

export function getCurrentUser(): string {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    // Негодное имя (например, записанное руками в localStorage) не должно ломать все запросы.
    return stored !== null && isValidUser(stored) ? stored : DEFAULT_USER
  } catch {
    // Приватный режим браузера может запретить localStorage — это не повод падать.
    return DEFAULT_USER
  }
}

export function setCurrentUser(user: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, user)
  } catch {
    // Молча живём дальше с именем по умолчанию.
  }
  // Сообщаем шапке, что имя сменилось: storage-событие в этой же вкладке не приходит.
  window.dispatchEvent(new Event(CHANGE_EVENT))
}

/** Подписка для useSyncExternalStore: имя сменили в этой вкладке или в другой. */
export function subscribeUser(onChange: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, onChange)
  window.addEventListener('storage', onChange)
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange)
    window.removeEventListener('storage', onChange)
  }
}
