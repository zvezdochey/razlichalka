import { useCallback, useEffect, useRef, useState } from 'react'
import { getApps, getAttributes } from '../../api'
import type { AppRow, AttributeRow, ChangeType } from '../../api'
import { ErrorBox } from '../../components'
import { useDialogFocus } from './useDialogFocus'
import { usePivotRequest } from './usePivotRequest'
import './AppPanel.css'

const PAGE_SIZE = 100
const SEARCH_DELAY_MS = 300

const CHANGE_LABELS: Record<ChangeType, string> = {
  VALUE_CHANGED: 'Значение изменилось',
  ATTRIBUTE_NEW: 'Появился',
  ATTRIBUTE_LOST: 'Исчез',
  SAME: 'Без изменений',
}

type ValueProps = {
  value: string | null
  bucket: string | null
  /** Значение поменялось, а бакет остался тем же — подпишем, чтобы изменение не терялось. */
  sameBucket: boolean
}

/** Значение атрибута: null — это «Отсутствует», а не пустая строка и не ноль. */
function Value({ value, bucket, sameBucket }: ValueProps) {
  const text = value === null ? 'Отсутствует' : value === '' ? 'Пустая строка' : value
  return (
    <div className="app-panel-value">
      <span className={value === null ? 'app-panel-absent' : undefined}>{text}</span>
      {bucket !== null && <small>Диапазон: {bucket}</small>}
      {sameBucket && <small>В пределах того же диапазона</small>}
    </div>
  )
}

/** Текст, когда строк нет: объясняем, почему именно пусто. */
function emptyMessage(total: number, onlyDiff: boolean, search: string, type: ChangeType | ''): string {
  if (type !== '' && total > 0) return 'Среди загруженных строк такого типа нет. Нажмите «Загрузить ещё» или смените фильтр.'
  if (search !== '') return 'Атрибуты не найдены. Измените поиск или фильтры.'
  if (onlyDiff) return 'Различий нет'
  return 'У заявки нет атрибутов.'
}

type Props = {
  runId: string
  appId: string
  /** Строка заявки из таблицы. Если её там нет (прямая ссылка), панель найдёт её сама. */
  app?: AppRow
  onClose: () => void
}

export function AppPanel({ runId, appId, app, onClose }: Props) {
  const dialog = useRef<HTMLElement>(null)
  useDialogFocus(dialog, onClose)

  // Заявка для шапки: из таблицы или найденная запросом /apps?search=<id>
  const [found, setFound] = useState<AppRow | undefined>(app)
  const header = app ?? found

  // Фильтры. `draft` — то, что набрано в поле, `search` — то, что уже ушло в запрос.
  const [onlyDiff, setOnlyDiff] = useState(true)
  const [draft, setDraft] = useState('')
  const [search, setSearch] = useState('')
  const [type, setType] = useState<ChangeType | ''>('')

  // Страницы копятся в `rows`, пока не сменился фильтр.
  const [page, setPage] = useState(1)
  const [rows, setRows] = useState<AttributeRow[]>([])

  const resetRows = () => {
    setPage(1)
    setRows([])
  }

  const load = useCallback(
    (signal: AbortSignal) =>
      getAttributes(runId, appId, { only_diff: onlyDiff, search, page, size: PAGE_SIZE }, { signal }).then((data) => {
        if (!signal.aborted) {
          setRows((previous) => (page === 1 ? data.attributes : [...previous, ...data.attributes]))
        }
        return data
      }),
    [runId, appId, onlyDiff, search, page],
  )
  const { result, retry } = usePivotRequest(load)

  // Поиск отправляем с задержкой, чтобы не слать запрос на каждую букву
  useEffect(() => {
    if (draft === search) return
    const timer = window.setTimeout(() => {
      setSearch(draft)
      resetRows()
    }, SEARCH_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [draft, search])

  // Прямая ссылка: заявки нет в загруженной странице таблицы — ищем её отдельно
  useEffect(() => {
    if (header) return
    const controller = new AbortController()
    getApps(runId, { search: appId, size: 50 }, { signal: controller.signal })
      .then((data) => setFound(data.apps.find((item) => item.app_id === appId)))
      .catch(() => {})
    return () => controller.abort()
  }, [runId, appId, header])

  // Фильтр по типу в API нет, поэтому он работает только по уже загруженным строкам
  const visible = rows.filter((row) => type === '' || row.change_type === type)
  const total = result.status === 'ready' ? result.data.total : 0
  const hasMore = result.status === 'ready' && rows.length < total

  return (
    <div className="app-panel-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <aside ref={dialog} className="app-panel" role="dialog" aria-modal="true" aria-label={`Атрибуты заявки ${appId}`}>
        <header className="app-panel-header">
          <div>
            <small>Заявка · сравнение атрибутов</small>
            <h2 className="mono">{appId}</h2>
            {header && (
              <p>
                Решение: {header.decision_before ?? '—'} → {header.decision_after ?? '—'} · Изменено атрибутов: {header.attributes_changed}
              </p>
            )}
          </div>
          <button className="btn app-panel-close" aria-label="Закрыть панель заявки" onClick={onClose}>×</button>
        </header>

        <div className="app-panel-body">
          {/* Место под вкладку «Почему» (задача I4) */}
          <nav className="app-panel-tabs" aria-label="Разделы заявки">
            <span aria-current="page">Атрибуты</span>
          </nav>

          <div className="app-panel-controls">
            <label>
              Поиск по пути
              <input className="input" type="search" value={draft} onChange={(event) => setDraft(event.target.value)} />
            </label>
            <label>
              <input
                type="checkbox"
                checked={onlyDiff}
                onChange={(event) => { setOnlyDiff(event.target.checked); resetRows() }}
              />
              {' '}Только различия
            </label>
            <label>
              Тип изменения (в загруженных строках)
              <select className="select" value={type} onChange={(event) => setType(event.target.value as ChangeType | '')}>
                <option value="">Все типы</option>
                {Object.entries(CHANGE_LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
              </select>
            </label>
          </div>

          {result.status === 'error' && <ErrorBox message={result.message} onRetry={retry} />}
          {result.status === 'loading' && <p role="status">Загрузка атрибутов…</p>}
          {result.status === 'ready' && visible.length === 0 && <p role="status">{emptyMessage(total, onlyDiff, search, type)}</p>}

          {visible.length > 0 && (
            <div className="table-scroll app-panel-table-scroll" tabIndex={0} aria-label="Таблица атрибутов, прокручиваемая область">
              <table className="table app-panel-table">
                <thead>
                  <tr><th>Атрибут</th><th>Элемент массива</th><th>BEFORE</th><th>AFTER</th><th>Тип</th></tr>
                </thead>
                <tbody>
                  {visible.map((row, index) => (
                    <tr key={`${row.path}:${row.array_key}:${index}`} className={row.diff_flag ? 'app-panel-diff' : undefined}>
                      <td className="app-panel-path mono" data-label="Атрибут">{row.path}</td>
                      <td data-label="Элемент массива">{row.array_key === null ? '—' : <span className="chip mono">{row.array_key}</span>}</td>
                      <td data-label="BEFORE">
                        <Value
                          value={row.value_before}
                          bucket={row.adjusted_before}
                          sameBucket={row.change_type === 'VALUE_CHANGED' && row.adjusted_before !== null && row.adjusted_before === row.adjusted_after}
                        />
                      </td>
                      <td data-label="AFTER"><Value value={row.value_after} bucket={row.adjusted_after} sameBucket={false} /></td>
                      <td data-label="Тип"><span className="app-panel-type">{CHANGE_LABELS[row.change_type]}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {hasMore && <button className="btn" onClick={() => setPage((value) => value + 1)}>Загрузить ещё</button>}
        </div>
      </aside>
    </div>
  )
}
