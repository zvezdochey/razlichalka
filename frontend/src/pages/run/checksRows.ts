// Чистая логика вкладки «Проверки»: сортировка, разбор чисел и ошибок из журнала.
// Отдельно от разметки, чтобы её было легко прочитать и объяснить.
import type { CheckRow, StageLogEntry } from '../../api'
import { formatNumber } from '../../lib/format'

/** Вердикт строки: от него зависят цвет, подпись и место в таблице. */
export type Verdict = 'fail' | 'low' | 'pass'

export function verdictOf(row: CheckRow): Verdict {
  if (row.result === 'PASS') return 'pass'
  return row.faint ? 'low' : 'fail'
}

const VERDICT_RANK: Record<Verdict, number> = { fail: 0, low: 1, pass: 2 }

/**
 * Порядок по умолчанию: уверенные FAIL → бледные FAIL → PASS.
 * Сортировка устойчивая: внутри группы строки идут в порядке бэка (по проверкам).
 */
export function sortByVerdict(rows: CheckRow[]): CheckRow[] {
  return [...rows].sort((a, b) => VERDICT_RANK[verdictOf(a)] - VERDICT_RANK[verdictOf(b)])
}

/** `"CNT / TOTAL"` → `CNT`. Сколько заявок попало под проверку; `null`, если не число. */
export function countOf(row: CheckRow): number | null {
  if (row.numbers === null) return null
  const cnt = Number.parseFloat(row.numbers.split('/')[0])
  return Number.isFinite(cnt) ? cnt : null
}

/**
 * Ровно две формы записи, которые бэк пишет в журнал этапа `checks`, когда проверка
 * упала (`backend/app/services/stages.py` и `backend/pipeline/checks_runner.py`):
 * «Проверка «X» не выполнена: …» и «Проверка «X» не загружена: …».
 * Другие ошибки этапа сюда не попадают: это не «проверка не выполнилась».
 */
const CHECK_FAILED = /^Проверка «(.+)» не (?:выполнена|загружена):/

/**
 * Какие проверки не выполнились — имена из журнала этапа `checks`.
 * В таблицу бэк при этом пишет строку FAIL с текстом ошибки и `faint: true`.
 */
export function failedChecks(log: StageLogEntry[]): string[] {
  const names = log
    .filter((entry) => entry.level === 'error')
    .map((entry) => CHECK_FAILED.exec(entry.message)?.[1])
    .filter((name): name is string => name !== undefined)
  return [...new Set(names)]
}

/**
 * Строка ошибки выполнения, а не вердикт проверки. Такая строка всегда FAIL и бледная;
 * ищем её по названию (упала при запуске) или по id (не загрузилась — названия ещё нет).
 */
export function isErrorRow(row: CheckRow, failed: string[]): boolean {
  if (row.result !== 'FAIL' || !row.faint) return false
  return failed.includes(row.check_name) || (row.check_id !== null && failed.includes(row.check_id))
}

const METRIC = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 4 })

/** Метрика — доля, разница или значение: до четырёх знаков, с разделителями разрядов. */
export function formatMetric(value: number): string {
  return METRIC.format(value)
}

/** `"CNT / TOTAL"` → `TOTAL`: база, от которой считается доля; `null`, если не число. */
export function baseOf(row: CheckRow): number | null {
  if (row.numbers === null) return null
  const parts = row.numbers.split('/')
  if (parts.length < 2) return null
  const total = Number.parseFloat(parts[1])
  return Number.isFinite(total) ? total : null
}

/**
 * Метрика — это доля CNT / TOTAL? Так пишут встроенные проверки и шаг 7 демо
 * (`round(share, 4)`). Узнаём по совпадению с числами строки, а не по названию:
 * у других проверок метрика бывает разницей или значением, и процентом её показывать нельзя.
 */
export function isShareMetric(row: CheckRow): boolean {
  const cnt = countOf(row)
  const total = baseOf(row)
  if (row.metric === null || cnt === null || total === null || total <= 0) return false
  return row.metric >= 0 && row.metric <= 1 && Math.abs(row.metric - cnt / total) < 0.0005
}

const PERCENT = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 })

/** Доля 0,2508 → «25,08 %». */
export function formatShare(value: number): string {
  return `${PERCENT.format(value * 100)} %`
}

/** Сколько разных проверок дали строки: по id, а у строк без id — по названию. */
export function checksCount(rows: CheckRow[]): number {
  return new Set(rows.map((row) => row.check_id ?? row.check_name)).size
}

/** Русское множественное число: plural(5, ['пример', 'примера', 'примеров']) → «примеров». */
export function plural(n: number, forms: [string, string, string]): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return forms[0]
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return forms[1]
  return forms[2]
}

const EXAMPLES: [string, string, string] = ['пример', 'примера', 'примеров']

/** «20 примеров из 273» — когда проверка сохранила не все заявки, иначе просто число. */
export function examplesLabel(shown: number, count: number | null): string {
  if (count === null || shown >= count) return formatNumber(shown)
  return `${formatNumber(shown)} ${plural(shown, EXAMPLES)} из ${formatNumber(count)}`
}
