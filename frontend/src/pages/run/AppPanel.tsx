import { useCallback, useEffect, useRef, useState } from 'react'
import { getApps, getAttributes } from '../../api'
import type { AppRow, AttributeRow, ChangeType } from '../../api'
import { ErrorBox } from '../../components'
import { decisionLabel } from '../../lib/decisions'
import { AppWhy } from './AppWhy'
import { useDialogFocus } from './useDialogFocus'
import { usePivotRequest } from './usePivotRequest'
import './AppPanel.css'

const PAGE_SIZE = 100
const SEARCH_DELAY_MS = 300

const CHANGE_LABELS: Record<ChangeType, string> = {
  VALUE_CHANGED: 'Значение изменилось',
  ATTRIBUTE_NEW: 'Атрибут появился',
  ATTRIBUTE_LOST: 'Атрибут исчез',
  SAME: 'Без изменений',
}

type ValueProps = {
  value: string | null
  bucket: string | null
  /** Значение поменялось, а бакет остался тем же — подпишем, чтобы изменение не терялось. */
  sameBucket: boolean
}

/** Атрибут решения (путь кончается на `.decision`) — его значение показываем словами. */
const isDecisionPath = (path: string) => /(^|\.)decision$/i.test(path)

/** Путь с мягкими переносами после точек: длинный путь рвётся по точкам, а не посреди слова. */
function PathText({ path }: { path: string }) {
  const parts = path.split('.')
  return <>{parts.map((part, i) => <span key={i}>{part}{i < parts.length - 1 && <>.<wbr /></>}</span>)}</>
}

/** Значение атрибута: null — это «нет значения», а не пустая строка и не ноль. */
function Value({ value, bucket, sameBucket, isDecision }: ValueProps & { isDecision: boolean }) {
  const shown = isDecision ? decisionLabel(value) : value
  const text = shown === null ? 'нет значения' : shown === '' ? 'Пустая строка' : shown
  // Для нечисловых атрибутов (даты, ID, массивы) бэк отдаёт adjusted_* равным самому значению —
  // это не бакет, а отсутствие бакетинга для этого пути. Подпись «Диапазон» тут только путает.
  const showBucket = bucket !== null && bucket !== value
  return (
    <div className="app-panel-value">
      <span className={value === null ? 'app-panel-absent' : undefined} title={isDecision && value !== null ? value : undefined}>{text}</span>
      {showBucket && <small>Диапазон: {bucket}</small>}
      {sameBucket && <small>В пределах того же диапазона</small>}
    </div>
  )
}

/** Текст, когда строк нет: объясняем, почему именно пусто. */
function emptyMessage(total: number, onlyDiff: boolean, search: string, type: ChangeType | ''): string {
  if (type !== '' && total > 0) return 'Среди загруженных строк такого типа нет. Нажмите «Загрузить ещё» или выберите другой тип.'
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
  const [section, setSection] = useState<'attributes' | 'why'>('attributes')

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

  // Фильтра по типу в API нет: он работает по уже загруженным строкам (подгружаются кнопкой «Загрузить ещё»)
  const visible = rows.filter((row) => type === '' || row.change_type === type)
  const total = result.status === 'ready' ? result.data.total : 0
  const hasMore = result.status === 'ready' && rows.length < total

  return (
    <div className="app-panel-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <aside ref={dialog} className="app-panel" role="dialog" aria-modal="true" aria-label={`Заявка ${appId}`}>
        <header className="app-panel-header">
          <div>
            <small>Заявка</small>
            <h2 className="mono">{appId}</h2>
            {header && (
              <p>
                Решение:{' '}
                <span title={header.decision_before ?? undefined}>{decisionLabel(header.decision_before) ?? '—'}</span>
                {' → '}
                <span title={header.decision_after ?? undefined}>{decisionLabel(header.decision_after) ?? '—'}</span>
                {' '}· Изменено атрибутов: {header.attributes_changed}
              </p>
            )}
          </div>
          <button className="btn app-panel-close" aria-label="Закрыть панель заявки" onClick={onClose}>×</button>
        </header>

        <div className="app-panel-body">
          <div className="app-panel-tabs" role="group" aria-label="Разделы заявки">
            <button type="button" className="btn" aria-pressed={section === 'attributes'} onClick={() => setSection('attributes')}>
              Атрибуты
            </button>
            <button type="button" className="btn" aria-pressed={section === 'why'} onClick={() => setSection('why')}>
              Почему изменилось решение
            </button>
          </div>

          {section === 'why' ? <AppWhy runId={runId} appId={appId} /> : <>
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
              Показать: все / только изменённые
              <select className="select" value={type} onChange={(event) => setType(event.target.value as ChangeType | '')}>
                <option value="">Все</option>
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
                  <tr><th>Атрибут</th><th>Элемент массива (продукт / оффер)</th><th>До</th><th>После</th><th>Тип</th></tr>
                </thead>
                <tbody>
                  {visible.map((row, index) => (
                    <tr key={`${row.path}:${row.array_key}:${index}`} className={row.diff_flag ? 'app-panel-diff' : undefined}>
                      <td className="app-panel-path mono" data-label="Атрибут"><PathText path={row.path} /></td>
                      <td data-label="Элемент массива (продукт / оффер)">{row.array_key === null ? '—' : <span className="chip mono">{row.array_key}</span>}</td>
                      <td data-label="До">
                        <Value
                          value={row.value_before}
                          bucket={row.adjusted_before}
                          sameBucket={row.change_type === 'VALUE_CHANGED' && row.adjusted_before !== null && row.adjusted_before === row.adjusted_after}
                          isDecision={isDecisionPath(row.path)}
                        />
                      </td>
                      <td data-label="После"><Value value={row.value_after} bucket={row.adjusted_after} sameBucket={false} isDecision={isDecisionPath(row.path)} /></td>
                      <td data-label="Тип"><span className="app-panel-type">{CHANGE_LABELS[row.change_type]}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {hasMore && <button className="btn" onClick={() => setPage((value) => value + 1)}>Загрузить ещё</button>}
          </>}
        </div>
      </aside>
    </div>
  )
}
