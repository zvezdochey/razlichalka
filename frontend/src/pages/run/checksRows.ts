// Чистая логика вкладки «Проверки»: сортировка, разбор чисел и ошибок из журнала.
// Отдельно от разметки, чтобы её было легко прочитать и объяснить.
import type { CheckRow, StageLogEntry } from '../../api'

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
