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
