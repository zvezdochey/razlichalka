import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { factLabel, isPivotField, PIVOT_FIELDS } from './pivotLayout'
import type { PivotField } from './pivotLayout'

type PivotFiltersProps = {
  filters: Record<string, string[]>
  field: PivotField
  onFieldChange: (field: PivotField) => void
  dragHandle: ReactNode
  /** Значения поля, которые есть в прогоне: подсказки при вводе. */
  suggestions?: string[]
  onChange: (filters: Record<string, string[]>) => void
}

export function PivotFilters({ filters, field, onFieldChange, dragHandle, suggestions = [], onChange }: PivotFiltersProps) {
  const values = filters[field]
  const applied = values?.some((value) => /[;,]/.test(value))
    ? JSON.stringify(values)
    : values?.join(', ') ?? (field === 'DIFF_FLAG' || field === 'DECISION_CHANGED' ? '1' : '')
  const [draft, setDraft] = useState({ field, applied, value: applied })
  const [error, setError] = useState('')

  if (draft.field !== field || draft.applied !== applied) {
    setDraft({ field, applied, value: applied })
    setError('')
  }
  const { value } = draft

  const apply = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    let values: string[]
    if (/^\s*\[\s*"/.test(value)) {
      try {
        const parsed: unknown = JSON.parse(value)
        if (!Array.isArray(parsed) || !parsed.length || !parsed.every((item) => typeof item === 'string')) throw new Error()
        values = parsed
      } catch {
        setError('Укажите список строк в JSON, например ["a,b","c;d"].')
        return
      }
    } else {
      values = value.split(',').map((part) => part.trim())
    }
    if ((field === 'DIFF_FLAG' || field === 'DECISION_CHANGED') && values.some((item) => item !== '0' && item !== '1')) {
      setError('Для этого поля введите 0 или 1.')
      return
    }
    setError('')
    onChange({ ...filters, [field]: [...new Set(values)] })
  }

  const remove = (field: string) => {
    const next = { ...filters }
    delete next[field]
    onChange(next)
  }

  return (
    <div className="pivot-filters">
      <form className="pivot-filter-form" onSubmit={apply}>
        <label>
          <span>Поле фильтра</span>
          {dragHandle}
          <select
            className="select"
            value={field}
            onChange={(event) => {
              const next = event.target.value
              if (!isPivotField(next)) return
              onFieldChange(next)
            }}
          >
            {Object.entries(PIVOT_FIELDS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </label>
        <label>
          <span>Значения через запятую (начните вводить — появятся подсказки)</span>
          <input
            className="input"
            list="pivot-filter-values"
            value={value}
            onChange={(event) => { setDraft({ field, applied, value: event.target.value }); setError('') }}
            placeholder="Например VALUE_CHANGED"
            title={'Для значений с запятой используйте список JSON, например ["a,b"].'}
          />
        </label>
        <datalist id="pivot-filter-values">
          {/* value — то, что уйдёт в фильтр; подпись — по-человечески (0/1 → «Нет»/«Да», коды → названия) */}
          {suggestions.map((item) => <option key={item} value={item} label={factLabel(field, item)} />)}
        </datalist>
        <button className="btn" type="submit">Применить фильтр</button>
      </form>
      {error && <p className="pivot-filter-error" role="alert">{error}</p>}
      <ul className="pivot-filter-list" aria-label="Активные фильтры">
        {Object.entries(filters).map(([key, values]) => {
          if (!isPivotField(key)) return null
          const label = `${PIVOT_FIELDS[key]} · ${values.map((item) => factLabel(key, item)).join(' или ')}`
          return (
            <li key={key}>
              <button type="button" className="btn pivot-filter-chip" onClick={() => remove(key)} aria-label={`Убрать фильтр ${label}`}>
                {label} <span aria-hidden="true">×</span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
