import { useCallback, useEffect, useRef, useState } from 'react'
import { getApps, getAttributes } from '../../api'
import type { AppRow, AttributeRow, ChangeType } from '../../api'
import { ErrorBox } from '../../components'
import { usePivotRequest } from './usePivotRequest'
import './AppPanel.css'

const LABELS: Record<ChangeType, string> = { VALUE_CHANGED: 'Значение изменилось', ATTRIBUTE_NEW: 'Появился', ATTRIBUTE_LOST: 'Исчез', SAME: 'Без изменений' }
const FOCUSABLE = 'button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex="0"]'
function Value({ value, bucket, same }: { value: string | null; bucket: string | null; same: boolean }) {
  return <div className="app-panel-value"><span className={value === null ? 'app-panel-absent' : undefined}>{value === null ? 'Отсутствует' : value === '' ? 'Пустая строка' : value}</span>
    {bucket !== null && <small>Диапазон: {bucket}</small>}{same && <small>В пределах того же диапазона</small>}</div>
}
export function AppPanel({ runId, appId, app, onClose }: { runId: string; appId: string; app?: AppRow; onClose: () => void }) {
  const dialog = useRef<HTMLElement>(null)
  const opener = useRef<HTMLElement | null>(null)
  const [found, setFound] = useState(app)
  const [page, setPage] = useState(1)
  const [onlyDiff, setOnlyDiff] = useState(true)
  const [draft, setDraft] = useState('')
  const [search, setSearch] = useState('')
  const [type, setType] = useState<ChangeType | ''>('')
  const [rows, setRows] = useState<AttributeRow[]>([])
  const load = useCallback((signal: AbortSignal) => getAttributes(runId, appId, { only_diff: onlyDiff, search, page, size: 100 }, { signal })
    .then((data) => { if (!signal.aborted) setRows((previous) => page === 1 ? data.attributes : [...previous, ...data.attributes]); return data }), [runId, appId, onlyDiff, search, page])
  const { result, retry } = usePivotRequest(load)
  useEffect(() => { if (draft === search) return; const timer = window.setTimeout(() => { setSearch(draft); setPage(1); setRows([]) }, 300); return () => window.clearTimeout(timer) }, [draft, search])
  useEffect(() => { if (app || found) return; const controller = new AbortController(); void getApps(runId, { search: appId, size: 50 }, { signal: controller.signal }).then((data) => setFound(data.apps.find((item) => item.app_id === appId))).catch(() => {}); return () => controller.abort() }, [runId, appId, app, found])
  useEffect(() => { opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; dialog.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus(); const overflow = document.body.style.overflow; document.body.style.overflow = 'hidden'; return () => { document.body.style.overflow = overflow; opener.current?.focus() } }, [])
  useEffect(() => { const handle = (event: KeyboardEvent) => { if (event.key === 'Escape') { event.preventDefault(); onClose(); return } if (event.key !== 'Tab' || !dialog.current) return; const items = Array.from(dialog.current.querySelectorAll<HTMLElement>(FOCUSABLE)); if (!items.length) return; if (event.shiftKey && document.activeElement === items[0]) { event.preventDefault(); items.at(-1)?.focus() } else if (!event.shiftKey && document.activeElement === items.at(-1)) { event.preventDefault(); items[0].focus() } }; document.addEventListener('keydown', handle); return () => document.removeEventListener('keydown', handle) }, [onClose])
  const visible = rows.filter((row) => !type || row.change_type === type)
  const total = result.status === 'ready' ? result.data.total : 0
  return <div className="app-panel-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}><aside ref={dialog} className="app-panel" role="dialog" aria-modal="true" aria-label={`Атрибуты заявки ${appId}`}>
    <header className="app-panel-header"><div><small>Заявка · сравнение атрибутов</small><h2 className="mono">{appId}</h2>{(app ?? found) && <p>Решение: {(app ?? found)?.decision_before ?? '—'} → {(app ?? found)?.decision_after ?? '—'} · Изменено атрибутов: {(app ?? found)?.attributes_changed}</p>}</div><button className="btn app-panel-close" aria-label="Закрыть панель заявки" onClick={onClose}>×</button></header>
    <div className="app-panel-body"><nav className="app-panel-tabs" aria-label="Разделы заявки"><span aria-current="page">Атрибуты</span></nav>
      <div className="app-panel-controls"><label>Поиск по пути<input className="input" type="search" value={draft} onChange={(event) => setDraft(event.target.value)} /></label><label><input type="checkbox" checked={onlyDiff} onChange={(event) => { setOnlyDiff(event.target.checked); setPage(1); setRows([]) }} /> Только различия</label><label>Тип изменения<select className="select" value={type} onChange={(event) => setType(event.target.value as ChangeType | '')}><option value="">Все типы</option>{Object.entries(LABELS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label></div>
      {result.status === 'error' && <ErrorBox message={result.message} onRetry={retry} />}
      {result.status === 'loading' && <p role="status">Загрузка атрибутов…</p>}
      {result.status === 'ready' && visible.length === 0 && <p role="status">{onlyDiff && total === 0 ? 'Различий нет' : 'Атрибуты не найдены. Измените фильтры.'}</p>}
      {visible.length > 0 && <div className="table-scroll app-panel-table-scroll" tabIndex={0} aria-label="Таблица атрибутов, прокручиваемая область"><table className="table app-panel-table"><thead><tr><th>Атрибут</th><th>Элемент массива</th><th>BEFORE</th><th>AFTER</th><th>Тип</th></tr></thead><tbody>{visible.map((row, index) => <tr key={`${row.path}:${row.array_key}:${index}`} className={row.diff_flag ? 'app-panel-diff' : undefined}><td className="app-panel-path mono">{row.path.replaceAll('.', '.\u200b')}</td><td>{row.array_key === null ? '—' : <span className="chip mono">{row.array_key}</span>}</td><td><Value value={row.value_before} bucket={row.adjusted_before} same={row.change_type === 'VALUE_CHANGED' && row.adjusted_before !== null && row.adjusted_before === row.adjusted_after} /></td><td><Value value={row.value_after} bucket={row.adjusted_after} same={false} /></td><td><span className="app-panel-type">{LABELS[row.change_type]}</span></td></tr>)}</tbody></table></div>}
      {result.status === 'ready' && rows.length < total && <button className="btn" onClick={() => setPage((value) => value + 1)}>Загрузить ещё</button>}
    </div></aside></div>
}
