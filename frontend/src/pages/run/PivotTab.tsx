import { useCallback, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getFacts } from '../../api'
import { EmptyState, ErrorBox, Spinner } from '../../components'
import { NotReadyNotice } from './NotReadyNotice'
import { PivotFilters } from './PivotFilters'
import { PivotGroupPanel } from './PivotGroupPanel'
import { isPivotField, PIVOT_FIELDS, PIVOT_PRESETS, readPivotLayout, writePivotLayout } from './pivotLayout'
import type { PivotField, PivotLayout } from './pivotLayout'
import { PivotTable } from './PivotTable'
import type { PivotGroup } from './PivotTable'
import { usePivotRequest } from './usePivotRequest'
import { useRunContext } from './runContext'
import './PivotTab.css'

type AxisProps = {
  label: string
  value: PivotField | null
  unavailable: (PivotField | null)[]
  allowEmpty?: boolean
  onChange: (value: PivotField | null) => void
}

function Axis({ label, value, unavailable, allowEmpty = false, onChange }: AxisProps) {
  return (
    <label>
      <span>{label}</span>
      <select
        className="select"
        value={value ?? ''}
        onChange={(event) => onChange(isPivotField(event.target.value) ? event.target.value : null)}
      >
        {allowEmpty && <option value="">Без поля</option>}
        {Object.entries(PIVOT_FIELDS).map(([key, text]) => (
          <option key={key} value={key} disabled={unavailable.some((field) => field === key)}>{text}</option>
        ))}
      </select>
    </label>
  )
}

export function PivotTab() {
  const { runId, run } = useRunContext()
  if (run?.status !== 'ready') return <NotReadyNotice run={run} />

  return <ReadyPivot key={runId} runId={runId} />
}

function ReadyPivot({ runId }: { runId: string }) {
  const [params, setParams] = useSearchParams()
  const layout = useMemo(() => readPivotLayout(params), [params])
  const [selection, setSelection] = useState<{ layout: PivotLayout; group: PivotGroup; trigger: HTMLButtonElement } | null>(null)
  const group = selection?.layout === layout ? selection.group : null

  const load = useCallback((signal: AbortSignal) => getFacts(runId, {
    dims: layout.column === null ? layout.rows : [...layout.rows, layout.column],
    filter: layout.filters,
    measure: layout.measure,
  }, { signal }), [runId, layout])
  const { result, retry } = usePivotRequest(load)

  const update = (next: PivotLayout) => {
    const search = writePivotLayout(params, next)
    if (params.toString() !== search.toString()) setParams(search, { preventScrollReset: true })
  }

  const close = useCallback(() => {
    setSelection(null)
    selection?.trigger.focus()
  }, [selection])

  const primaryRow = layout.rows[0]
  const secondaryRow = layout.rows[1] ?? null
  const setRows = (first: PivotField, second: PivotField | null) => {
    update({ ...layout, rows: second === null ? [first] : [first, second] })
  }

  const swapAxes = () => {
    if (layout.column === null) return
    update({ ...layout, rows: [layout.column, ...layout.rows.slice(1)], column: primaryRow })
  }

  return (
    <div className="pivot">
      <section className="panel pivot-editor" aria-labelledby="pivot-title">
        <div className="pivot-editor-head">
          <h2 id="pivot-title">Сводная</h2>
          <div className="pivot-presets" role="group" aria-label="Готовые представления">
            {PIVOT_PRESETS.map(({ label, axes }) => {
              const selected = axes.rows.join(',') === layout.rows.join(',') && axes.column === layout.column && axes.measure === layout.measure
              return (
                <button
                  key={label}
                  type="button"
                  className="btn"
                  aria-pressed={selected}
                  onClick={() => update({ ...layout, ...axes })}
                >
                  {label}
                </button>
              )
            })}
          </div>
          <button type="button" className="btn" onClick={() => update(readPivotLayout(new URLSearchParams()))}>Сбросить раскладку</button>
        </div>

        <div className="pivot-axes">
          <fieldset>
            <legend>Строки</legend>
            <Axis label="Первое поле строк" value={primaryRow} unavailable={[secondaryRow, layout.column]} onChange={(value) => {
              if (value !== null) setRows(value, secondaryRow)
            }} />
            <Axis label="Второе поле строк" value={secondaryRow} unavailable={[primaryRow, layout.column]} allowEmpty onChange={(value) => setRows(primaryRow, value)} />
          </fieldset>
          <fieldset>
            <legend>Колонки</legend>
            <Axis label="Поле колонок" value={layout.column} unavailable={layout.rows} allowEmpty onChange={(column) => update({ ...layout, column })} />
            <button type="button" className="btn pivot-swap" disabled={layout.column === null} title="Меняет первое поле строк и поле колонок" onClick={swapAxes}>
              Поменять строки и колонки местами
            </button>
          </fieldset>
          <fieldset className="pivot-measure">
            <legend>Показатель</legend>
            <label>
              <input type="radio" name="pivot-measure" checked={layout.measure === 'counts'} onChange={() => update({ ...layout, measure: 'counts' })} />
              Строк витрины
            </label>
            <label>
              <input type="radio" name="pivot-measure" checked={layout.measure === 'counts_distinct_apps'} onChange={() => update({ ...layout, measure: 'counts_distinct_apps' })} />
              Заявок
            </label>
          </fieldset>
        </div>

        <fieldset className="pivot-filter-fieldset">
          <legend>Фильтры</legend>
          <PivotFilters filters={layout.filters} onChange={(filters) => update({ ...layout, filters })} />
        </fieldset>
      </section>

      <div className={group ? 'pivot-results pivot-results--with-group' : 'pivot-results'}>
        <section className="panel pivot-data" aria-label="Результаты сводной" aria-busy={result.status === 'loading'}>
          {result.status === 'loading' && <Spinner label="Загружаем сводную" />}
          {result.status === 'error' && <ErrorBox message={result.message} onRetry={retry} />}
          {result.status === 'ready' && (
            result.data.rows.length === 0 ? (
              <EmptyState
                title="В этой раскладке нет различий"
                hint="Измените поля раскладки или снимите фильтры."
                action={Object.keys(layout.filters).length > 0 && (
                  <button className="btn" type="button" onClick={() => update({ ...layout, filters: {} })}>Снять фильтры</button>
                )}
              />
            ) : (
              <PivotTable layout={layout} data={result.data} elapsed={result.elapsed} onOpenGroup={(group, trigger) => setSelection({ layout, group, trigger })} />
            )
          )}
        </section>
        {group && <PivotGroupPanel key={group.ref} group={group} runId={runId} onClose={close} />}
      </div>
    </div>
  )
}
