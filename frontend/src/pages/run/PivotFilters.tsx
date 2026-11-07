import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { factLabel, isPivotField, PIVOT_FIELDS } from './pivotLayout'
import type { PivotField } from './pivotLayout'

type PivotFiltersProps = {
  filters: Record<string, string[]>
  field: PivotField
  onFieldChange: (field: PivotField) => void
  dragHandle: ReactNode
  onChange: (filters: Record<string, string[]>) => void
}

export function PivotFilters({ filters, field, onFieldChange, dragHandle, onChange }: PivotFiltersProps) {
  const applied = filters[field]?.join(', ') ?? (field === 'DIFF_FLAG' ? '1' : '')
  const [draft, setDraft] = useState({ field, applied, value: applied })
  const [error, setError] = useState('')

  if (draft.field !== field || draft.applied !== applied) {
    setDraft({ field, applied, value: applied })
    setError('')
  }
  const { value } = draft

  const apply = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const values = [...new Set(value.split(',').map((part) => part.trim()))]
    if (value.includes(';')) {
      setError('Точка с запятой разделяет фильтры и не может входить в значение.')
      return
    }
    if (field === 'DIFF_FLAG' && values.some((item) => item !== '0' && item !== '1')) {
      setError('Для этого поля введите 0 или 1.')
      return
    }
    setError('')
    onChange({ ...filters, [field]: values })
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
          <span>Значения через запятую</span>
          <input
            className="input"
            value={value}
            onChange={(event) => { setDraft({ field, applied, value: event.target.value }); setError('') }}
            placeholder="Например VALUE_CHANGED"
          />
        </label>
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
