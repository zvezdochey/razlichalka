import { useState } from 'react'
import type { FormEvent } from 'react'
import { factLabel, isPivotField, PIVOT_FIELDS } from './pivotLayout'
import type { PivotField } from './pivotLayout'

type PivotFiltersProps = {
  filters: Record<string, string[]>
  onChange: (filters: Record<string, string[]>) => void
}

export function PivotFilters({ filters, onChange }: PivotFiltersProps) {
  const [field, setField] = useState<PivotField>('DIFF_FLAG')
  const applied = filters[field]?.join(', ') ?? (field === 'DIFF_FLAG' ? '1' : '')
  const [draft, setDraft] = useState({ applied, value: applied })
  const [error, setError] = useState('')

  if (draft.applied !== applied) {
    setDraft({ applied, value: applied })
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
          <select
            className="select"
            value={field}
            onChange={(event) => {
              const next = event.target.value
              if (!isPivotField(next)) return
              setField(next)
              const nextValue = filters[next]?.join(', ') ?? (next === 'DIFF_FLAG' ? '1' : '')
              setDraft({ applied: nextValue, value: nextValue })
              setError('')
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
            onChange={(event) => { setDraft({ applied, value: event.target.value }); setError('') }}
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
