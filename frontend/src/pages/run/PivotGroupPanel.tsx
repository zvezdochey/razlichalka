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
  const panel = useRef<HTMLElement>(null)
  const title = useRef<HTMLHeadingElement>(null)
  const load = useCallback(
    (signal: AbortSignal) => getFactApps(runId, group.ref, page, PAGE_SIZE, { signal }),
    [runId, group.ref, page],
  )
  const { result, retry } = usePivotRequest(load)

  useEffect(() => {
    // Панель может открыться за пределами экрана: показываем её и переводим фокус на заголовок.
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    panel.current?.scrollIntoView({ block: 'nearest', behavior: reduce ? 'auto' : 'smooth' })
    title.current?.focus({ preventScroll: true })
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
    <aside ref={panel} className="panel pivot-group" aria-labelledby="pivot-group-title">
      <div className="pivot-group-head">
        <h3 id="pivot-group-title" ref={title} tabIndex={-1}>Заявки группы</h3>
        <button type="button" className="btn" onClick={onClose} aria-label="Закрыть список заявок">×</button>
      </div>
      <p className="pivot-group-label muted">{group.label}</p>
      {group.measure === 'counts' && group.cellCount !== undefined && data && (
        <p className="muted">В ячейке {formatNumber(group.cellCount)} строк витрины в {formatNumber(data.total)} заявках</p>
      )}
      {result.status === 'loading' && <Spinner label="Загружаем заявки группы" />}
      {result.status === 'error' && <ErrorBox message={result.message} onRetry={retry} />}
      {data && (
        data.apps.length > 0 ? (
          <>
            <p className="muted">Всего заявок {formatNumber(data.total)}</p>
            <ul className="pivot-group-list">
              {data.apps.map((id) => (
                <li key={id}>
                  <Link className="mono" to={`/runs/${encodeURIComponent(runId)}/apps?${new URLSearchParams({
                    // список под карточкой — эта же группа (все её заявки, без фильтра «Только с различиями»)
                    ref: group.ref, group: group.label, has_attr_change: '0', app: id, ...(group.path ? { attr: group.path } : {}),
                  })}`}>
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
