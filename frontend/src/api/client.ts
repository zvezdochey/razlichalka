// Единственное место, где фронт делает fetch. Все ручки из endpoints.ts идут через
// request(): он сам подставляет заголовок X-User и приводит любую ошибку к одному виду.
import { getCurrentUser } from '../lib/user'
import type { ApiError, ApiErrorResponse, ErrorCode } from './types'

/** Все адреса относительные: в деве их проксирует vite.config.ts, в проде раздаёт тот же хост. */
const API_BASE = '/api'

/** Сеть не ответила вообще: бэк не поднят, нет интернета, запрос заблокировали. */
const NETWORK_ERROR_MESSAGE = 'Нет связи с сервером'

/**
 * Коды шлюза: так отвечает прокси, когда за ним никого нет. Проверено —
 * dev-сервер Vite при неподнятом бэке отдаёт ровно 502 с пустым телом.
 */
const GATEWAY_STATUSES = new Set([502, 503, 504])

/** Ответ пришёл, но прочитать тело ошибки не удалось — показываем хотя бы код. */
function fallbackMessage(status: number): string {
  if (GATEWAY_STATUSES.has(status)) return NETWORK_ERROR_MESSAGE
  return `Сервер ответил ошибкой ${status}`
}

/**
 * Ошибка запроса к API. `message` — текст из тела ответа, его показываем
 * пользователю как есть (`ErrorBox` ждёт именно так). `code` — для логики:
 * например отмену запуска отличаем от падения по `code === 'cancelled'`.
 */
export class ApiRequestError extends Error {
  readonly code: ErrorCode
  /** HTTP-код ответа. `0`, если ответа не было вообще (сетевая ошибка). */
  readonly status: number

  constructor(code: ErrorCode, message: string, status = 0) {
    super(message)
    this.name = 'ApiRequestError'
    this.code = code
    this.status = status
  }
}

/** Отмена запроса через AbortController — не ошибка, а штатная ситуация. */
export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

/** Достаём `{ error: { code, message } }` из тела. Тело может быть и не JSON. */
async function readError(res: Response): Promise<ApiRequestError> {
  let body: unknown
  try {
    body = await res.json()
  } catch {
    return new ApiRequestError('internal', fallbackMessage(res.status), res.status)
  }

  const error = (body as Partial<ApiErrorResponse>)?.error as Partial<ApiError> | undefined
  if (typeof error?.message === 'string' && error.message !== '') {
    const code = typeof error.code === 'string' ? (error.code as ErrorCode) : 'internal'
    return new ApiRequestError(code, error.message, res.status)
  }

  return new ApiRequestError('internal', fallbackMessage(res.status), res.status)
}

/**
 * Сам запрос: подставляет X-User и превращает неуспешный ответ в `ApiRequestError`.
 * Отмену (`AbortError`) пробрасывает как есть, чтобы вызывающий мог её не показывать.
 */
async function send(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers)
  // Авторизации нет: бэк различает людей по этому заголовку.
  headers.set('X-User', getCurrentUser())
  // У FormData заголовок с границей частей ставит сам браузер: свой JSON-заголовок его сломает.
  if (init?.body !== undefined && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers })
  } catch (cause) {
    if (isAbortError(cause)) throw cause
    throw new ApiRequestError('internal', NETWORK_ERROR_MESSAGE)
  }

  if (!res.ok) throw await readError(res)
  return res
}

/**
 * Запрос к API. `T` — тип ожидаемого тела ответа.
 *
 * Бросает `ApiRequestError` на любой неуспешный ответ и на сетевую ошибку.
 */
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await send(path, init)

  // 204 (например удаление) — тела нет, парсить нечего.
  if (res.status === 204) return undefined as T

  try {
    return (await res.json()) as T
  } catch {
    throw new ApiRequestError('internal', 'Сервер вернул не JSON')
  }
}

/**
 * Скачать файл (отчёт, CSV). Обычная ссылка `<a href download>` не годится:
 * браузер не пришлёт X-User, и бэк ответит «не найдено» — запуск чужой.
 * Поэтому забираем файл через fetch и отдаём браузеру как blob.
 */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const res = await send(path)
  const url = URL.createObjectURL(await res.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  link.remove()
  // Даём браузеру начать скачивание, потом освобождаем память.
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/**
 * Запуск остановил пользователь, а не сломался. В договоре это тот же `status: 'error'`
 * (п. 5.4), отличается только кодом — и показывать это надо нейтрально, не как аварию.
 */
export function isCancelled(error: ApiError | null | undefined): boolean {
  return error?.code === 'cancelled'
}
