// Имя пользователя. Авторизации нет: бэк различает людей по заголовку X-User (его
// отправляет клиент API в F2), а здесь мы только храним и отдаём выбранное имя.
const STORAGE_KEY = 'razlichalka_user'
const DEFAULT_USER = 'demo'

export function getCurrentUser(): string {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored && stored.trim() !== '' ? stored : DEFAULT_USER
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
}
