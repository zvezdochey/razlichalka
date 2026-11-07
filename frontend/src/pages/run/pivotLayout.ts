import { formatFactsFilter } from '../../api'
import { decisionLabel } from '../../lib/decisions'
import type { FactsMeasure, FactValue } from '../../api'

export const PIVOT_FIELDS = {
  PATH: 'Атрибут',
  CHANGE_TYPE: 'Тип изменения',
  ARRAY_KEY_1: 'Элемент массива',
  VALUE_BEFORE: 'Значение до',
  VALUE_AFTER: 'Значение после',
  ADJUSTED_BEFORE: 'Диапазон (бакет) до',
  ADJUSTED_AFTER: 'Диапазон (бакет) после',
  // Поля вертикальной витрины (union.csv): строки BEFORE и AFTER одна под другой. Сочетаются с атрибутом,
  // типом изменения и разрезами заявки, но не с полями «до/после» выше.
  SOURCE: 'Срез (до / после)',
  VALUE: 'Значение (в своём срезе)',
  ADJUSTED_VALUE: 'Диапазон (бакет, в своём срезе)',
  DECISION_CHANGED: 'Решение изменилось',
  DECISION_BEFORE: 'Решение до',
  DECISION_AFTER: 'Решение после',
  PD_MODEL_BEFORE: 'Модель PD до',
  PD_MODEL_AFTER: 'Модель PD после',
  PARTNER_TYPE: 'Тип партнёра',
  ROUTING_METHOD: 'Маршрутизация',
  CHANGE_SOURCE: 'Источник изменения',
  DIFF_FLAG: 'Атрибут изменился',
} as const

export type PivotField = keyof typeof PIVOT_FIELDS
type PivotAxes = { rows: PivotField[]; column: PivotField | null; measure: FactsMeasure }

/** Пояснение к названию поля — показываем в title. */
export const PIVOT_FIELD_HINTS: Partial<Record<PivotField, string>> = {
  ARRAY_KEY_1: 'Элемент массива: продукт, оффер или модель',
  VALUE_BEFORE: 'Точное значение атрибута в старой версии. Удобно с фильтром по одному атрибуту',
  VALUE_AFTER: 'Точное значение атрибута в новой версии. Удобно с фильтром по одному атрибуту',
  ADJUSTED_BEFORE: 'Значение, сведённое к диапазону (бакеты задаются в конфигурации). Без бакетов — само значение',
  ADJUSTED_AFTER: 'Значение, сведённое к диапазону (бакеты задаются в конфигурации). Без бакетов — само значение',
  SOURCE: 'Срез: BEFORE — старая версия СПР, AFTER — новая. Считается по вертикальной витрине (union.csv)',
  VALUE: 'Значение атрибута в срезе из поля «Срез». Нельзя сочетать с полями «до/после»',
  ADJUSTED_VALUE: 'Диапазон значения в срезе из поля «Срез». Нельзя сочетать с полями «до/после»',
}

/** Поля, у которых одна заявка попадает ровно в одну группу — по ним итоги можно суммировать. */
const ONE_GROUP_FIELDS: PivotField[] = ['DECISION_BEFORE', 'DECISION_AFTER', 'DECISION_CHANGED', 'CHANGE_SOURCE',
  // Поля разреза: в витрине segments одна строка на заявку (backend/pipeline), поэтому она попадает ровно в одну ячейку.
  'PD_MODEL_BEFORE', 'PD_MODEL_AFTER', 'PARTNER_TYPE', 'ROUTING_METHOD',
]

export function isOneGroupLayout(fields: (PivotField | null)[]): boolean {
  return fields.every((field) => field === null || ONE_GROUP_FIELDS.includes(field))
}

const DEFAULT_FILTERS: Record<string, string[]> = { DECISION_CHANGED: ['1'] }

export type PivotLayout = PivotAxes & { filters: Record<string, string[]> }

export const PIVOT_PRESETS: { label: string; axes: PivotAxes; filters: Record<string, string[]> }[] = [
  { label: 'Что изменилось (атрибуты)', axes: { rows: ['PATH'], column: 'CHANGE_TYPE', measure: 'counts_distinct_apps' }, filters: { DIFF_FLAG: ['1'] } },
  { label: 'Где изменилось (продукты и офферы)', axes: { rows: ['ARRAY_KEY_1'], column: 'CHANGE_TYPE', measure: 'counts_distinct_apps' }, filters: { DIFF_FLAG: ['1'] } },
  { label: 'Кто сменил решение', axes: { rows: ['DECISION_BEFORE'], column: 'DECISION_AFTER', measure: 'counts_distinct_apps' }, filters: DEFAULT_FILTERS },
]

const VALUE_LABELS: Partial<Record<PivotField, Record<string, string>>> = {
  CHANGE_TYPE: {
    VALUE_CHANGED: 'Значение изменилось',
    ATTRIBUTE_NEW: 'Атрибут появился',
    ATTRIBUTE_LOST: 'Атрибут исчез',
    SAME: 'Без изменений',
  },
  CHANGE_SOURCE: { logic: 'Логика', data: 'Входные данные', both: 'Логика и данные', none: 'Без смены решения' },
  DIFF_FLAG: { '0': 'Нет', '1': 'Да' },
  SOURCE: { BEFORE: 'До (BEFORE)', AFTER: 'После (AFTER)' },
  DECISION_CHANGED: { '0': 'Нет', '1': 'Да' },
}

export function isPivotField(value: string): value is PivotField {
  return Object.hasOwn(PIVOT_FIELDS, value)
}

/** Человеческая подпись элемента массива. Тип угадываем по виду ключа; не уверены — оставляем как есть. */
function arrayKeyLabel(value: FactValue): string {
  const key = value === null ? '' : String(value).trim()
  if (key === '' || key.toLowerCase() === 'none') return NOT_ARRAY_LABEL
  if (/^\d+$/.test(key)) return `Продукт ${key}`
  const offer = /^(\d+):(.+)$/.exec(key)
  if (offer) return `Оффер ${offer[2]}, продукт ${offer[1]}`
  if (/^ML_.+_V\d+$/i.test(key)) return `модель ${key}`
  if (/^score_/i.test(key)) return `внешний источник ${key}`
  return key
}

export function factLabel(field: PivotField, value: FactValue): string {
  if (field === 'ARRAY_KEY_1') return arrayKeyLabel(value)
  if (value === null || value === '') return 'Пусто'
  if (field === 'DECISION_BEFORE' || field === 'DECISION_AFTER') return decisionLabel(String(value)) ?? 'Пусто'
  const labels = VALUE_LABELS[field]
  const key = String(value)
  return labels && Object.hasOwn(labels, key) ? labels[key] : key
}

const NOT_ARRAY_LABEL = 'Не относится к массиву'

/** Порядок значений: решения — «Одобрено», «Отказ», прочие; типы изменения — в фиксированном порядке. */
const CHANGE_TYPE_ORDER = ['VALUE_CHANGED', 'ATTRIBUTE_NEW', 'ATTRIBUTE_LOST']

function valueRank(field: PivotField, value: FactValue): number {
  if (field === 'DECISION_BEFORE' || field === 'DECISION_AFTER') {
    const key = value === null ? '' : String(value).trim().toLowerCase()
    if (key === 'approve') return 0
    if (key === 'reject') return 1
    return value === null || value === '' ? 3 : 2
  }
  if (field === 'CHANGE_TYPE') {
    const index = CHANGE_TYPE_ORDER.indexOf(String(value))
    return index < 0 ? CHANGE_TYPE_ORDER.length : index
  }
  if (field === 'ARRAY_KEY_1') return arrayKeyLabel(value) === NOT_ARRAY_LABEL ? 0 : 1
  return 0
}

/** Сравнение двух наборов значений полей; 0 — порядок не задан, остаётся как пришёл от бэка. */
export function compareFactValues(fields: PivotField[], a: FactValue[], b: FactValue[]): number {
  for (let i = 0; i < fields.length; i++) {
    const diff = valueRank(fields[i], a[i]) - valueRank(fields[i], b[i])
    if (diff !== 0) return diff
  }
  return 0
}

/** Заголовок группы для панели «Заявки группы»: решение пишем как «до → после». */
export function groupLabel(fields: PivotField[], values: FactValue[]): string {
  const at = (field: PivotField) => fields.indexOf(field)
  const before = at('DECISION_BEFORE')
  const after = at('DECISION_AFTER')
  const parts: string[] = []
  fields.forEach((field, i) => {
    if (field === 'DECISION_BEFORE' || field === 'DECISION_AFTER') return
    parts.push(factLabel(field, values[i]))
  })
  const decision = before >= 0 && after >= 0
    ? `Решение до: ${factLabel('DECISION_BEFORE', values[before])} → после: ${factLabel('DECISION_AFTER', values[after])}`
    : before >= 0 ? `Решение до: ${factLabel('DECISION_BEFORE', values[before])}`
    : after >= 0 ? `Решение после: ${factLabel('DECISION_AFTER', values[after])}` : null
  return (decision ? [decision, ...parts] : parts).join(' · ')
}

export function readPivotLayout(params: URLSearchParams): PivotLayout {
  const rows = [...new Set((params.get('rows') ?? 'DECISION_BEFORE').split(',').filter(isPivotField))].slice(0, 2)
  if (rows.length === 0) rows.push('DECISION_BEFORE')

  const column = params.get('cols') ?? 'DECISION_AFTER'
  const filters = readFilters(params.get('f') ?? 'DECISION_CHANGED:1')

  return {
    rows,
    column: isPivotField(column) && !rows.includes(column) ? column : null,
    filters,
    measure: params.get('m') === 'counts' ? 'counts' : 'counts_distinct_apps',
  }
}

function readFilters(raw: string): Record<string, string[]> {
  const filters: Record<string, string[]> = {}
  if (raw.trimStart().startsWith('{')) {
    try {
      const parsed: unknown = JSON.parse(raw)
      if (parsed && typeof parsed === 'object') {
        for (const [field, values] of Object.entries(parsed)) {
          if (isPivotField(field) && Array.isArray(values) && values.length && values.every((value) => typeof value === 'string')) {
            filters[field] = values
          }
        }
      }
    } catch {
      // Повреждённая ссылка открывается без фильтра.
    }
    return filters
  }
  for (const condition of raw.split(';')) {
    const colon = condition.indexOf(':')
    if (colon < 0) continue
    const field = condition.slice(0, colon)
    if (isPivotField(field)) filters[field] = condition.slice(colon + 1).split(',')
  }

  return filters
}

export function writePivotLayout(params: URLSearchParams, layout: PivotLayout): URLSearchParams {
  const next = new URLSearchParams(params)
  next.set('rows', layout.rows.join(','))
  next.set('cols', layout.column ?? '')
  next.set('f', formatFactsFilter(layout.filters))
  next.set('m', layout.measure)
  return next
}
