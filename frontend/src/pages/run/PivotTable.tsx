import type { FactsResponse, FactsRow, FactValue } from '../../api'
import { useLocation, useNavigate } from 'react-router-dom'
import { DASH, formatNumber } from '../../lib/format'
import { factLabel, isOneGroupLayout, PIVOT_FIELDS } from './pivotLayout'
import type { PivotField, PivotLayout } from './pivotLayout'

export type PivotGroup = { ref: string; label: string }

type PivotTableProps = {
  layout: PivotLayout
  data: FactsResponse
  elapsed: number
  onOpenGroup: (group: PivotGroup, trigger: HTMLButtonElement) => void
}

type MatrixRow = { values: FactValue[]; cells: Map<string, FactsRow>; total: number }
type MatrixColumn = { value: FactValue; total: number }

const RESPONSE_TIME = new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const ROW_PAGE_SIZE = 50
const COLUMN_PAGE_SIZE = 20

function makeMatrix(groups: FactsRow[], rowFields: PivotField[], columnField: PivotField | null) {
  const rows = new Map<string, MatrixRow>()
  const columns = new Map<string, MatrixColumn>()
  let total = 0

  for (const group of groups) {
    const values = rowFields.map((field) => group[field] ?? null)
    const rowKey = JSON.stringify(values)
    const value = columnField === null ? null : group[columnField] ?? null
    const columnKey = JSON.stringify(value)
    const row = rows.get(rowKey) ?? { values, cells: new Map<string, FactsRow>(), total: 0 }
    const column = columns.get(columnKey) ?? { value, total: 0 }

    row.cells.set(columnKey, group)
    row.total += group.counts
    column.total += group.counts
    total += group.counts
    rows.set(rowKey, row)
    columns.set(columnKey, column)
  }

  return { rows, columns, total }
}

/** Длинный путь атрибута: даём переносу место после каждой точки и скобок, чтобы слово не рвалось посередине. */
function PathText({ path }: { path: string }) {
  const parts = path.split(/(?<=[.\]])/)
  return <>{parts.map((part, index) => <span key={index}>{part}<wbr /></span>)}</>
}

export function PivotTable({ layout, data, elapsed, onOpenGroup }: PivotTableProps) {
  const { rows, columns, total } = makeMatrix(data.rows, layout.rows, layout.column)
  const location = useLocation()
  const navigate = useNavigate()
  const rowPage: number = location.state?.pivotRowPage ?? 0
  const columnPage: number = location.state?.pivotColumnPage ?? 0
  const setPage = (key: 'pivotRowPage' | 'pivotColumnPage', value: number) => navigate(location.pathname + location.search, {
    replace: true, preventScrollReset: true, state: { ...location.state, [key]: value },
  })
  const visibleRows = [...rows].slice(rowPage * ROW_PAGE_SIZE, (rowPage + 1) * ROW_PAGE_SIZE)
  const visibleColumns = [...columns].slice(columnPage * COLUMN_PAGE_SIZE, (columnPage + 1) * COLUMN_PAGE_SIZE)
  // Итоги суммируем, если показатель — строки витрины или заявка попадает ровно в одну группу.
  const additive = layout.measure === 'counts' || isOneGroupLayout([...layout.rows, layout.column])
  const truncated = data.total_groups > data.rows.length
  const metric = layout.measure === 'counts' ? 'Строк витрины' : 'Заявок'
  const totalLabel = truncated ? 'Итого по показанным группам' : 'Итого'

  return (
    <>
      <div className="pivot-table-meta">
        <span>{metric}</span>
        <span className="muted">Ответ за {RESPONSE_TIME.format(elapsed / 1000)} с</span>
      </div>
      {truncated && (
        <p className="pivot-note" role="status">
          Показаны первые {formatNumber(data.rows.length)} групп из {formatNumber(data.total_groups)}, сузьте фильтр.
        </p>
      )}
      {(rows.size > ROW_PAGE_SIZE || columns.size > COLUMN_PAGE_SIZE) && (
        <nav className="pivot-pagination" aria-label="Страницы сводной">
          <span>Строки {rowPage + 1} / {Math.ceil(rows.size / ROW_PAGE_SIZE)}</span>
          <button type="button" className="btn" disabled={rowPage === 0} onClick={() => setPage('pivotRowPage', rowPage - 1)}>Предыдущие строки</button>
          <button type="button" className="btn" disabled={(rowPage + 1) * ROW_PAGE_SIZE >= rows.size} onClick={() => setPage('pivotRowPage', rowPage + 1)}>Следующие строки</button>
          <span>Колонки {columnPage + 1} / {Math.ceil(columns.size / COLUMN_PAGE_SIZE)}</span>
          <button type="button" className="btn" disabled={columnPage === 0} onClick={() => setPage('pivotColumnPage', columnPage - 1)}>Предыдущие колонки</button>
          <button type="button" className="btn" disabled={(columnPage + 1) * COLUMN_PAGE_SIZE >= columns.size} onClick={() => setPage('pivotColumnPage', columnPage + 1)}>Следующие колонки</button>
          <span className="muted">Итоги учитывают все загруженные группы.</span>
        </nav>
      )}
      <div className="table-scroll pivot-table-scroll" tabIndex={0} role="region" aria-label="Сводная таблица">
        <table className="table pivot-table">
          <caption className="visually-hidden">Сводная таблица. Показатель — {metric}</caption>
          <thead>
            <tr>
              {layout.rows.map((field) => <th key={field} scope="col">{PIVOT_FIELDS[field]}</th>)}
              {visibleColumns.map(([key, column]) => (
                <th key={key} scope="col" className="num">
                  {layout.column === null ? metric : factLabel(layout.column, column.value)}
                </th>
              ))}
              {layout.column !== null && <th scope="col" className="num">{totalLabel}</th>}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map(([rowKey, row]) => {
              const rowLabels = layout.rows.map((field, index) => factLabel(field, row.values[index]))
              return (
                <tr key={rowKey}>
                  {layout.rows.map((field, index) => (
                    <th key={field} scope="row" className={field === 'PATH' ? 'mono' : undefined} title={rowLabels[index]}>
                      {field === 'PATH' ? <PathText path={rowLabels[index]} /> : rowLabels[index]}
                    </th>
                  ))}
                  {visibleColumns.map(([key, column]) => {
                    const cell = row.cells.get(key)
                    const label = layout.column === null
                      ? rowLabels.join(' · ')
                      : [...rowLabels, factLabel(layout.column, column.value)].join(' · ')
                    return (
                      <td key={key} className="num">
                        {cell ? (
                          <button
                            className="pivot-cell"
                            type="button"
                            data-fact-ref={cell.app_ids_ref}
                            aria-label={`Заявки группы ${label}, ${metric.toLowerCase()}: ${formatNumber(cell.counts)}`}
                            onClick={(event) => onOpenGroup({ ref: cell.app_ids_ref, label }, event.currentTarget)}
                          >
                            {formatNumber(cell.counts)}
                          </button>
                        ) : truncated ? DASH : <span className="pivot-zero">0</span>}
                      </td>
                    )
                  })}
                  {layout.column !== null && <td className="num">{additive ? formatNumber(row.total) : DASH}</td>}
                </tr>
              )
            })}
          </tbody>
          <tfoot>
            <tr>
              <th scope="row" colSpan={layout.rows.length}>{totalLabel}</th>
              {visibleColumns.map(([key, column]) => (
                <td key={key} className="num">{additive ? formatNumber(column.total) : DASH}</td>
              ))}
              {layout.column !== null && <td className="num">{additive ? formatNumber(total) : DASH}</td>}
            </tr>
          </tfoot>
        </table>
      </div>
      {!additive && <p className="pivot-note muted">Итого по заявкам не показываем: одна заявка может попасть в несколько групп.</p>}
    </>
  )
}
