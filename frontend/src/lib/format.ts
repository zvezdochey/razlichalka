// Форматирование дат, длительностей и чисел. Форматтеры создаём один раз на модуль:
// их построение дороже самого вызова, а зовём мы их на каждый кадр опроса.

const DATE_TIME = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

const TIME = new Intl.DateTimeFormat('ru-RU', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})

const NUMBER = new Intl.NumberFormat('ru-RU')

/** Прочерк вместо пустого места: в таблице это читается как «значения нет». */
export const DASH = '—'

function parse(iso: string | null): Date | null {
  if (iso === null || iso === '') return null
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? null : date
}

/** «6 нояб., 12:00» — для шапки прогона и колонки «Создан». */
export function formatDateTime(iso: string | null): string {
  const date = parse(iso)
  return date === null ? DASH : DATE_TIME.format(date)
}

/** «12:00:35» — для строк журнала, где важны секунды, а не день. */
export function formatTime(iso: string | null): string {
  const date = parse(iso)
  return date === null ? DASH : TIME.format(date)
}

/** «1 234» — числа в интерфейсе всегда с разделителями разрядов. */
export function formatNumber(value: number): string {
  return NUMBER.format(value)
}

const MS_IN_SECOND = 1000
const SECONDS_IN_MINUTE = 60
const MINUTES_IN_HOUR = 60

/**
 * Длительность этапа: от `from` до `to`, а если этап ещё идёт (`to === null`) —
 * до `now`. Вызывающий передаёт `now` сам, чтобы значение пересчитывалось
 * на каждом опросе и не зависело от момента рендера.
 */
export function formatDuration(from: string | null, to: string | null, now: number): string {
  const start = parse(from)
  if (start === null) return DASH

  const end = parse(to)?.getTime() ?? now
  const totalSeconds = Math.max(0, Math.round((end - start.getTime()) / MS_IN_SECOND))

  const seconds = totalSeconds % SECONDS_IN_MINUTE
  const minutes = Math.floor(totalSeconds / SECONDS_IN_MINUTE) % MINUTES_IN_HOUR
  const hours = Math.floor(totalSeconds / (SECONDS_IN_MINUTE * MINUTES_IN_HOUR))

  if (hours > 0) return `${hours} ч ${minutes} мин`
  if (minutes > 0) return `${minutes} мин ${seconds} с`
  return `${seconds} с`
}

/** «07.11 10:06» — короткая дата для списков, где важно отличить версии друг от друга. */
export function formatShortDateTime(iso: string | null): string {
  const date = parse(iso)
  if (date === null) return DASH
  const two = (n: number) => String(n).padStart(2, '0')
  return `${two(date.getDate())}.${two(date.getMonth() + 1)} ${two(date.getHours())}:${two(date.getMinutes())}`
}

/**
 * Время загрузки из id вида `UP-20261107-052820-ab12` → «07.11 05:28».
 * Не разобралось — `null`, и вызывающий покажет id как есть.
 */
export function uploadTimeFromId(id: string): string | null {
  const m = /^UP-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})\d{2}/.exec(id)
  if (m === null) return null
  // Цифры из id показываем как есть (время сервера), но только если это настоящие дата и время
  const [month, day, hour, minute] = [m[2], m[3], m[4], m[5]].map(Number)
  if (month < 1 || month > 12 || day < 1 || day > 31 || hour > 23 || minute > 59) return null
  return `${m[3]}.${m[2]} ${m[4]}:${m[5]}`
}
