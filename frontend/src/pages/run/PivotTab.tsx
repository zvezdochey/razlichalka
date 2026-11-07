import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { DragEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getFacts, getSummary } from '../../api'
import type { Summary } from '../../api'
import { EmptyState, ErrorBox, Spinner } from '../../components'
import { formatNumber } from '../../lib/format'
import { NotReadyNotice } from './NotReadyNotice'
import { PivotFilters } from './PivotFilters'
import { PivotGroupPanel } from './PivotGroupPanel'
import { factLabel, isPivotField, PIVOT_FIELDS, PIVOT_PRESETS, readPivotLayout, writePivotLayout } from './pivotLayout'
import type { PivotField, PivotLayout } from './pivotLayout'
import { PivotTable } from './PivotTable'
import { useFactGroup } from './useFactGroup'
import { usePivotRequest } from './usePivotRequest'
import { useRunContext } from './runContext'
import './PivotTab.css'

const PIVOT_DRAG = 'application/x-razlichalka-pivot-field'
const AXIS_SLOTS = ['primary', 'secondary', 'column'] as const
type AxisSlot = (typeof AXIS_SLOTS)[number]

function DragField({ field }: { field: PivotField }) {
  return (
    <span
      className="chip"
      draggable
      aria-hidden="true"
      data-pivot-drag-field={field}
      title={`Перетащить поле «${PIVOT_FIELDS[field]}»`}
      style={{ cursor: 'grab' }}
      onDragStart={(event) => {
        event.dataTransfer.setData(PIVOT_DRAG, field)
        event.dataTransfer.effectAllowed = 'copyMove'
      }}
    >
      ⋮⋮ {PIVOT_FIELDS[field]}
    </span>
  )
}

function dropField(onDrop: (field: PivotField) => void, effect: 'copy' | 'move' = 'move') {
  return {
    onDragOver(event: DragEvent<HTMLElement>) {
      if (!event.dataTransfer.types.includes(PIVOT_DRAG)) return
      event.preventDefault()
      event.dataTransfer.dropEffect = effect
    },
    onDrop(event: DragEvent<HTMLElement>) {
      const field = event.dataTransfer.getData(PIVOT_DRAG)
      if (!isPivotField(field)) return
      event.preventDefault()
      onDrop(field)
    },
  }
}

type AxisProps = {
  label: string
  slot: AxisSlot
  value: PivotField | null
  unavailable: (PivotField | null)[]
  allowEmpty?: boolean
  onChange: (value: PivotField | null) => void
  onDropField: (slot: AxisSlot, field: PivotField) => void
}

function Axis({ label, slot, value, unavailable, allowEmpty = false, onChange, onDropField }: AxisProps) {
  return (
    <div data-pivot-slot={slot} {...dropField((field) => onDropField(slot, field))}>
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
      {value && <DragField field={value} />}
    </div>
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
  const [filterField, setFilterField] = useState<PivotField>('DECISION_CHANGED')
  // Подсказки для фильтра: какие значения у поля есть в этом прогоне (самые частые), с понятными подписями
  const [suggestions, setSuggestions] = useState<{ field: PivotField; values: string[] } | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    getFacts(runId, { dims: [filterField], measure: 'counts_distinct_apps', limit: 100 }, { signal: controller.signal })
      .then((data) => setSuggestions({
        field: filterField,
        values: data.rows.map((row) => row[filterField]).filter((value) => value !== null && value !== undefined).map(String),
      }), () => setSuggestions(null))
    return () => controller.abort()
  }, [runId, filterField])
  const [filterReset, setFilterReset] = useState(0)
  const { group, page, setGroup, setPage } = useFactGroup()
  const trigger = useRef<HTMLButtonElement>(null)

  // Итог прогона для строки над таблицей; не загрузился — строку просто не показываем.
  const [summary, setSummary] = useState<Summary | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    getSummary(runId, { signal: controller.signal }).then(setSummary, () => setSummary(null))
    return () => controller.abort()
  }, [runId])

  const load = useCallback((signal: AbortSignal) => getFacts(runId, {
    dims: layout.column === null ? layout.rows : [...layout.rows, layout.column],
    filter: layout.filters,
    measure: layout.measure,
  }, { signal }), [runId, layout])
  const { result, retry } = usePivotRequest(load)

  const update = (next: PivotLayout, resetHistory = false) => {
    const search = writePivotLayout(params, next)
    if (resetHistory || params.toString() !== search.toString()) setParams(search, { preventScrollReset: true })
  }

  // «Сдвиг значений»: матрица «бакет до × бакет после» для одного атрибута. Атрибут — из фильтра PATH,
  // а если его нет — самый часто меняющийся в этом прогоне (спрашиваем у фактов, путь в коде не зашит).
  const [shiftBusy, setShiftBusy] = useState(false)
  const openValueShift = async () => {
    let path = layout.filters.PATH?.length === 1 ? layout.filters.PATH[0] : undefined
    if (path === undefined) {
      setShiftBusy(true)
      try {
        const top = await getFacts(runId, { dims: ['PATH'], filter: { CHANGE_TYPE: ['VALUE_CHANGED'] }, measure: 'counts_distinct_apps', limit: 1 })
        const value = top.rows[0]?.PATH
        path = value === undefined || value === null ? undefined : String(value)
      } catch {
        path = undefined
      } finally {
        setShiftBusy(false)
      }
    }
    if (path === undefined) return
    update({ rows: ['ADJUSTED_BEFORE'], column: 'ADJUSTED_AFTER', measure: 'counts_distinct_apps', filters: { PATH: [path], CHANGE_TYPE: ['VALUE_CHANGED'] } })
  }

  const [manualOpen, setManualOpen] = useState(false)
  // Коротко, что сейчас в раскладке, — видно и в свёрнутом виде
  const layoutSummary = [
    `строки: ${layout.rows.map((field) => PIVOT_FIELDS[field]).join(', ')}`,
    layout.column !== null && `колонки: ${PIVOT_FIELDS[layout.column]}`,
    Object.entries(layout.filters).length > 0 && `фильтры: ${Object.entries(layout.filters)
      .map(([field, values]) => `${isPivotField(field) ? PIVOT_FIELDS[field] : field} = ${values.map((value) => isPivotField(field) ? factLabel(field, value) : value).join(' или ')}`)
      .join('; ')}`,
  ].filter(Boolean).join(' · ')

  const close = useCallback(() => {
    const button = trigger.current?.isConnected ? trigger.current
      : document.querySelector<HTMLButtonElement>(`[data-fact-ref="${CSS.escape(group?.ref ?? '')}"]`)
    const focusTarget = button ?? document.querySelector<HTMLButtonElement>('.pivot-editor button')
    setGroup(null)
    focusTarget?.focus()
  }, [setGroup, group])

  const primaryRow = layout.rows[0]
  const secondaryRow = layout.rows[1] ?? null
  const setRows = (first: PivotField, second: PivotField | null) => {
    update({ ...layout, rows: second === null ? [first] : [first, second] })
  }

  const swapAxes = () => {
    if (layout.column === null) return
    update({ ...layout, rows: [layout.column, ...layout.rows.slice(1)], column: primaryRow })
  }

  const dropOnAxis = (slot: AxisSlot, field: PivotField) => {
    const axes = [primaryRow, secondaryRow, layout.column]
    const target = AXIS_SLOTS.indexOf(slot)
    const source = axes.indexOf(field)
    if (source === target) return
    if (source !== -1) axes[source] = axes[target]
    axes[target] = field

    const [first, second, column] = axes
    const rows = [first, second].filter((item): item is PivotField => item !== null)
    if (rows.length === 0 || (rows.join(',') === layout.rows.join(',') && column === layout.column)) return
    update({ ...layout, rows, column })
  }

  return (
    <div className="pivot">
      <section className="panel pivot-editor" aria-labelledby="pivot-title">
        <div className="pivot-editor-head">
          <h2 id="pivot-title">Сводная</h2>
          <div className="pivot-presets" role="group" aria-label="Готовые представления">
            {PIVOT_PRESETS.map(({ label, axes, filters }) => {
              const selected = axes.rows.join(',') === layout.rows.join(',') && axes.column === layout.column && axes.measure === layout.measure && JSON.stringify(filters) === JSON.stringify(layout.filters)
              return (
                <button
                  key={label}
                  type="button"
                  className="btn"
                  aria-pressed={selected}
                  onClick={() => update({ ...layout, ...axes, filters })}
                >
                  {label}
                </button>
              )
            })}
            <button
              type="button"
              className="btn"
              aria-pressed={layout.rows.join(',') === 'ADJUSTED_BEFORE' && layout.column === 'ADJUSTED_AFTER'}
              disabled={shiftBusy}
              title="Строки — значение или диапазон (бакет) до, колонки — после, для одного атрибута. Атрибут — из фильтра, иначе тот, что меняется чаще всего"
              onClick={() => void openValueShift()}
            >
              Сдвиг значений (до → после)
            </button>
          </div>
          <button type="button" className="btn" onClick={() => {
            setFilterField('DECISION_CHANGED')
            setFilterReset((value) => value + 1)
            update(readPivotLayout(new URLSearchParams()), true)
          }}>Сбросить раскладку</button>
        </div>

        <p className="pivot-note muted">
          Сводная считает заявки по двум признакам: что стоит в строках и что в колонках, в клетке — сколько заявок.
          Проще всего начать с готовых кнопок сверху; свою раскладку и фильтры можно собрать ниже.
        </p>
        {/* Ручные настройки свёрнуты: на экране ноутбука таблица должна быть видна сразу. */}
        <details className="pivot-manual" open={manualOpen} onToggle={(event) => setManualOpen(event.currentTarget.open)}>
          <summary>
            <span className="pivot-manual__title">Настроить раскладку</span>{' '}
            <span className="muted">{layoutSummary}</span>
          </summary>
        <div className="pivot-axes">
          <fieldset>
            <legend>Строки</legend>
            <Axis label="Первое поле строк" slot="primary" value={primaryRow} unavailable={[secondaryRow, layout.column]} onDropField={dropOnAxis} onChange={(value) => {
              if (value !== null) setRows(value, secondaryRow)
            }} />
            <Axis label="Второе поле строк" slot="secondary" value={secondaryRow} unavailable={[primaryRow, layout.column]} allowEmpty onDropField={dropOnAxis} onChange={(value) => setRows(primaryRow, value)} />
          </fieldset>
          <fieldset>
            <legend>Колонки</legend>
            <Axis label="Поле колонок" slot="column" value={layout.column} unavailable={layout.rows} allowEmpty onDropField={dropOnAxis} onChange={(column) => update({ ...layout, column })} />
            <button type="button" className="btn pivot-swap" disabled={layout.column === null} title="Меняет первое поле строк и поле колонок" onClick={swapAxes}>
              Поменять местами (⇄)
            </button>
          </fieldset>
          <fieldset className="pivot-measure">
            <legend>Показатель</legend>
            <label>
              <input type="radio" name="pivot-measure" checked={layout.measure === 'counts'} onChange={() => update({ ...layout, measure: 'counts' })} />
              Строк данных (у заявки их много)
            </label>
            <label>
              <input type="radio" name="pivot-measure" checked={layout.measure === 'counts_distinct_apps'} onChange={() => update({ ...layout, measure: 'counts_distinct_apps' })} />
              Заявок
            </label>
          </fieldset>
        </div>

        <fieldset className="pivot-filter-fieldset" data-pivot-slot="filter" {...dropField(setFilterField, 'copy')}>
          <legend>Фильтры</legend>
          <PivotFilters
            key={filterReset}
            filters={layout.filters}
            field={filterField}
            suggestions={suggestions?.field === filterField ? suggestions.values : []}
            onFieldChange={setFilterField}
            dragHandle={<DragField field={filterField} />}
            onChange={(filters) => update({ ...layout, filters })}
          />
        </fieldset>
        </details>
      </section>

      <div className={group ? 'pivot-results pivot-results--with-group' : 'pivot-results'}>
        <section className="panel pivot-data" aria-label="Результаты сводной" aria-busy={result.status === 'loading'}>
          {summary && (
            <p className="pivot-summary">
              Заявок с различиями: <strong>{formatNumber(summary.applications_changed)}</strong>, из них сменили решение: <strong>{formatNumber(summary.decision_changed)}</strong>.
            </p>
          )}
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
              <PivotTable key={JSON.stringify(layout)} layout={layout} data={result.data} elapsed={result.elapsed} onOpenGroup={(group, button) => {
                trigger.current = button
                setGroup(group)
              }} />
            )
          )}
        </section>
        {group && <PivotGroupPanel key={group.ref} group={group} runId={runId} page={page} onPageChange={setPage} onClose={close} />}
      </div>
    </div>
  )
}
