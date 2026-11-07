import { formatFactsFilter } from '../../api'
import { decisionLabel } from '../../lib/decisions'
import type { FactsMeasure, FactValue } from '../../api'

export const PIVOT_FIELDS = {
  PATH: 'Атрибут',
  CHANGE_TYPE: 'Тип изменения',
  ARRAY_KEY_1: 'Элемент массива (продукт / оффер / модель)',
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

/** Поля, у которых одна заявка попадает ровно в одну группу — по ним итоги можно суммировать. */
const ONE_GROUP_FIELDS: PivotField[] = ['DECISION_BEFORE', 'DECISION_AFTER', 'DECISION_CHANGED', 'CHANGE_SOURCE']

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
  DECISION_CHANGED: { '0': 'Нет', '1': 'Да' },
}

export function isPivotField(value: string): value is PivotField {
  return Object.hasOwn(PIVOT_FIELDS, value)
}

/** Человеческая подпись элемента массива. Тип угадываем по виду ключа; не уверены — оставляем как есть. */
function arrayKeyLabel(value: FactValue): string {
  const key = value === null ? '' : String(value).trim()
  if (key === '' || key.toLowerCase() === 'none') return 'Не относится к массиву'
  if (/^\d+$/.test(key)) return `${key} — продукт`
  const offer = /^(\d+):(.+)$/.exec(key)
  if (offer) return `${offer[1]} · оффер ${offer[2]}`
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
