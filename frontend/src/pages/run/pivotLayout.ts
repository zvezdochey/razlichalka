import { formatFactsFilter } from '../../api'
import type { FactsMeasure, FactValue } from '../../api'

export const PIVOT_FIELDS = {
  PATH: 'Атрибут',
  CHANGE_TYPE: 'Тип изменения',
  ARRAY_KEY_1: 'Продукт (ключ массива)',
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

export type PivotLayout = PivotAxes & { filters: Record<string, string[]> }

export const PIVOT_PRESETS: { label: string; axes: PivotAxes }[] = [
  { label: 'По атрибутам', axes: { rows: ['PATH'], column: 'CHANGE_TYPE', measure: 'counts' } },
  { label: 'По продуктам', axes: { rows: ['ARRAY_KEY_1'], column: 'CHANGE_TYPE', measure: 'counts' } },
  { label: 'По решениям', axes: { rows: ['DECISION_BEFORE'], column: 'DECISION_AFTER', measure: 'counts_distinct_apps' } },
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

export function factLabel(field: PivotField, value: FactValue): string {
  if (value === null || value === '') return 'Пусто'
  const labels = VALUE_LABELS[field]
  const key = String(value)
  return labels && Object.hasOwn(labels, key) ? labels[key] : key
}

export function readPivotLayout(params: URLSearchParams): PivotLayout {
  const rows = [...new Set((params.get('rows') ?? 'PATH').split(',').filter(isPivotField))].slice(0, 2)
  if (rows.length === 0) rows.push('PATH')

  const column = params.get('cols') ?? 'CHANGE_TYPE'
  const filters = readFilters(params.get('f') ?? 'DIFF_FLAG:1')

  return {
    rows,
    column: isPivotField(column) && !rows.includes(column) ? column : null,
    filters,
    measure: params.get('m') === 'counts_distinct_apps' ? 'counts_distinct_apps' : 'counts',
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
