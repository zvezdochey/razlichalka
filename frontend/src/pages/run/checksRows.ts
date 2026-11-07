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

const PERCENT = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 })

/** Доля 0,2508 → «25,1 %». */
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

/** «20 из 130» — когда проверка сохранила не все заявки, иначе просто число. */
export function examplesLabel(shown: number, count: number | null): string {
  if (count === null || shown >= count) return formatNumber(shown)
  return `${formatNumber(shown)} из ${formatNumber(count)}`
}

/** Текст ссылки в колонке «Заявки»: «Все 130» или «Примеры: 20 из 130». */
export function appsLinkLabel(shown: number | undefined, count: number | null): string {
  if (shown === undefined) return count === null ? 'Показать заявки' : `Заявки: ${formatNumber(count)}`
  if (count === null || shown >= count) return `Все ${formatNumber(shown)}`
  return `Примеры: ${formatNumber(shown)} из ${formatNumber(count)}`
}

/** Проверка падения доли одобрений по продукту: её метрика — относительное падение, а не доля CNT / TOTAL. */
export const AR_DROP_CHECK = 'builtin_ar_drop_by_product'

export function isArDrop(row: CheckRow): boolean {
  return row.check_id === AR_DROP_CHECK
}

/** «Что проверяли» для человека: стрелки и «!=» словами, у падения доли — «Продукт 12412». Только отображение. */
export function displayArgument(row: CheckRow): string | null {
  if (row.argument === null) return null
  if (isArDrop(row) && /^\d+$/.test(row.argument)) return `Продукт ${row.argument}`
  // «предиктор != источник» — сравнение двух имён, поэтому знак ≠, а не фраза (иначе ломается падеж)
  return row.argument.replaceAll(' -> ', ' → ').replaceAll(' != ', ' ≠ ')
}

/**
 * Как называются случаи у встроенных проверок, которые пишут несколько строк с одним аргументом.
 * Стоп-фактор (checks/check_stop_factor_disappeared.py) выдаёт по правилу сначала строку «удалено из стратегии»,
 * потом «перестало срабатывать», а сам случай в строку не пишет — подписываем его по порядку.
 */
const VARIANT_NAMES: Record<string, string[]> = {
  builtin_stop_factor_disappeared: ['правило удалено из стратегии', 'правило перестало срабатывать'],
}

/** Подпись варианта строки: название случая, если оно известно, иначе «вариант N». */
export function variantLabel(row: CheckRow, variant: number): string {
  return VARIANT_NAMES[row.check_id ?? '']?.[variant - 1] ?? `вариант ${variant}`
}

/**
 * Номера вариантов для строк с одинаковыми (проверка, версия, аргумент, числа, метрика).
 * Бэк отдаёт их как два случая под одним названием, но с разными заявками, поэтому не склеиваем.
 * Строки без дублей в карту не попадают.
 */
export function variantsOf(rows: CheckRow[]): Map<CheckRow, number> {
  const key = (r: CheckRow) => JSON.stringify([r.check_id, r.check_name, r.source, r.argument, r.numbers, r.metric])
  const counts = new Map<string, number>()
  for (const row of rows) counts.set(key(row), (counts.get(key(row)) ?? 0) + 1)
  const seen = new Map<string, number>()
  const result = new Map<CheckRow, number>()
  for (const row of rows) {
    const k = key(row)
    if ((counts.get(k) ?? 0) < 2) continue
    const n = (seen.get(k) ?? 0) + 1
    seen.set(k, n)
    result.set(row, n)
  }
  return result
}

/** Версия данных простыми словами: AFTER → «после (новая)». Незнакомое значение оставляем как есть. */
export function sourceLabel(source: string | null): string | null {
  if (source === null) return null
  const key = source.toUpperCase()
  if (key === 'AFTER') return 'после (новая)'
  if (key === 'BEFORE') return 'до (старая)'
  return source
}

/** Длинный путь вида a.b.c.d показываем хвостом «…c.d»; полный путь уходит в подсказку. */
export function shortPath(text: string): string {
  if (/\s/.test(text)) return text
  const parts = text.split(/[./]/).filter(Boolean)
  if (parts.length <= 2) return text
  return `…${text.slice(text.length - (parts[parts.length - 2].length + parts[parts.length - 1].length + 1))}`
}

/** Порог, с которого строки одной проверки сворачиваем в группу. */
export const GROUP_MIN_ROWS = 6

/** Либо одна строка, либо группа строк одной проверки. */
export type TableItem =
  | { kind: 'row'; row: CheckRow }
  | { kind: 'group'; key: string; title: string; rows: CheckRow[]; fails: number }

/** Группируем по проверке; группа встаёт на место своей первой строки. Мелкие проверки остаются строками. */
export function groupRows(rows: CheckRow[]): TableItem[] {
  const byKey = new Map<string, CheckRow[]>()
  for (const row of rows) {
    const key = row.check_id ?? row.check_name
    byKey.set(key, [...(byKey.get(key) ?? []), row])
  }
  const items: TableItem[] = []
  const done = new Set<string>()
  for (const row of rows) {
    const key = row.check_id ?? row.check_name
    const group = byKey.get(key) ?? []
    if (group.length < GROUP_MIN_ROWS) {
      items.push({ kind: 'row', row })
    } else if (!done.has(key)) {
      done.add(key)
      items.push({
        kind: 'group',
        key,
        title: row.check_name,
        rows: group,
        fails: group.filter((r) => r.result === 'FAIL').length,
      })
    }
  }
  return items
}
