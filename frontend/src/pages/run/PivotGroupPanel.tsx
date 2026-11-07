import { useCallback, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { getFactApps } from '../../api'
import { EmptyState, ErrorBox, Spinner } from '../../components'
import { formatNumber } from '../../lib/format'
import type { PivotGroup } from './PivotTable'
import { usePivotRequest } from './usePivotRequest'
import './PivotTab.css'

const PAGE_SIZE = 50

type PivotGroupPanelProps = {
  runId: string
  group: PivotGroup
  onClose: () => void
  emptyHint?: string
  page: number
  onPageChange: (page: number) => void
}

export function PivotGroupPanel({
  runId, group, onClose, emptyHint = 'Выберите другую ячейку сводной.', page, onPageChange,
}: PivotGroupPanelProps) {
  const closeButton = useRef<HTMLButtonElement>(null)
  const load = useCallback(
    (signal: AbortSignal) => getFactApps(runId, group.ref, page, PAGE_SIZE, { signal }),
    [runId, group.ref, page],
  )
  const { result, retry } = usePivotRequest(load)

  useEffect(() => {
    closeButton.current?.focus()
  }, [])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !event.defaultPrevented) onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const data = result.status === 'ready' ? result.data : null
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : page
  const canGoBack = page > 1 && result.status !== 'loading'
  const canGoForward = page < pages && result.status !== 'loading'

  return (
    <aside className="panel pivot-group" aria-labelledby="pivot-group-title">
      <div className="pivot-group-head">
        <h3 id="pivot-group-title">Заявки группы</h3>
        <button ref={closeButton} type="button" className="btn" onClick={onClose} aria-label="Закрыть список заявок">×</button>
      </div>
      <p className="pivot-group-label muted">{group.label}</p>
      {result.status === 'loading' && <Spinner label="Загружаем заявки группы" />}
      {result.status === 'error' && <ErrorBox message={result.message} onRetry={retry} />}
      {data && (
        data.apps.length > 0 ? (
          <>
            <p className="muted">Всего заявок {formatNumber(data.total)}</p>
            <ul className="pivot-group-list">
              {data.apps.map((id) => (
                <li key={id}>
                  <Link className="mono" to={`/runs/${encodeURIComponent(runId)}/apps?${new URLSearchParams({ app: id })}`}>
                    {id}
                  </Link>
                </li>
              ))}
            </ul>
          </>
        ) : <EmptyState title="В этой группе нет заявок" hint={emptyHint} />
      )}
      {pages > 1 && (
        <nav className="pivot-pagination" aria-label="Страницы заявок группы">
          <button type="button" className="btn" aria-disabled={!canGoBack} onClick={() => { if (canGoBack) onPageChange(page - 1) }}>Назад</button>
          <span className="muted">Страница {page} из {pages}</span>
          <button type="button" className="btn" aria-disabled={!canGoForward} onClick={() => { if (canGoForward) onPageChange(page + 1) }}>Дальше</button>
        </nav>
      )}
    </aside>
  )
}
