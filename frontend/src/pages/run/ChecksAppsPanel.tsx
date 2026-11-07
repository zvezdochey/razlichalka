import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { CheckRow, FactAppsResponse } from '../../api'
import { getFactApps, isAbortError } from '../../api'
import { EmptyState, ErrorBox, Spinner } from '../../components'
import { formatNumber } from '../../lib/format'
import { countOf, displayArgument, examplesLabel } from './checksRows'

const PAGE_SIZE = 50

type ChecksAppsPanelProps = {
  runId: string
  row: CheckRow
  appsRef: string
  onClose: () => void
}

type LoadState =
  | { status: 'loading' }
  | { status: 'ready'; data: FactAppsResponse }
  | { status: 'error'; message: string }

/**
 * Справа от таблицы — заявки строки проверки (`/facts/{ref}/apps`, п. 7.3).
 * Клик по заявке открывает её панель во вкладке «Заявки» (F7) параметром `?app=`.
 */
export function ChecksAppsPanel({ runId, row, appsRef, onClose }: ChecksAppsPanelProps) {
  const [page, setPage] = useState(1)
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  // Сколько всего заявок — помним между страницами, чтобы листалка не пропадала на загрузке.
  const [total, setTotal] = useState<number | null>(null)
  const closeButton = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const controller = new AbortController()
    const load = async () => {
      setState({ status: 'loading' })
      try {
        const data = await getFactApps(runId, appsRef, page, PAGE_SIZE, {
          signal: controller.signal,
        })
        setState({ status: 'ready', data })
        setTotal(data.total)
      } catch (e) {
        if (isAbortError(e) || controller.signal.aborted) return
        setState({
          status: 'error',
          message: e instanceof Error ? e.message : 'Не удалось загрузить заявки проверки',
        })
      }
    }
    // eslint-disable-next-line react/set-state-in-effect -- загрузка данных эффектом и есть синхронизация с внешней системой
    void load()
    return () => controller.abort()
  }, [runId, appsRef, page, attempt])

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

  const data = state.status === 'ready' ? state.data : null
  const pages = total === null ? 1 : Math.max(1, Math.ceil(total / PAGE_SIZE))
  // aria-disabled, а не disabled: у отключённой кнопки пропадает фокус на время загрузки.
  const canGoBack = page > 1 && state.status !== 'loading'
  const canGoForward = page < pages && state.status !== 'loading'
  const count = countOf(row)
  // Проверка отдаёт не больше `app_ids_limit` заявок: если их меньше, чем CNT,
  // говорим об этом прямо, а не обещаем полный список (DESIGN.md п. 9).
  const limited = data !== null && count !== null && data.total < count

  return (
    <aside className="panel checks-apps" aria-labelledby="checks-apps-title">
      <div className="checks-apps-head">
        <h3 id="checks-apps-title">
          {limited ? `Заявки проверки: ${examplesLabel(data.total, count)}` : 'Заявки проверки'}
        </h3>
        <button
          ref={closeButton}
          type="button"
          className="btn"
          onClick={onClose}
          aria-label="Закрыть список заявок"
        >
          ×
        </button>
      </div>
      <p className="checks-apps-label muted">
        {row.check_name}
        {displayArgument(row) !== null && ` · ${displayArgument(row)}`}
      </p>

      {state.status === 'loading' && <Spinner label="Загружаем заявки" />}
      {state.status === 'error' && (
        <ErrorBox message={state.message} onRetry={() => setAttempt((n) => n + 1)} />
      )}
      {data !== null &&
        (data.apps.length === 0 ? (
          <EmptyState title="Заявок нет" hint="Проверка не вернула идентификаторов заявок." />
        ) : (
          <>
            <p className="muted">
              {limited
                ? `Показано ${examplesLabel(data.total, count)} — проверка сохраняет только часть заявок`
                : `Всего заявок ${formatNumber(data.total)}`}
            </p>
            <ul className="checks-apps-list">
              {data.apps.map((id) => (
                <li key={id}>
                  <Link
                    className="mono"
                    to={`/runs/${encodeURIComponent(runId)}/apps?${new URLSearchParams({ app: id })}`}
                  >
                    {id}
                  </Link>
                </li>
              ))}
            </ul>
          </>
        ))}

      {pages > 1 && (
        <nav className="checks-apps-pages" aria-label="Страницы заявок проверки">
          <button
            type="button"
            className="btn"
            aria-disabled={!canGoBack}
            onClick={() => {
              if (canGoBack) setPage(page - 1)
            }}
          >
            Назад
          </button>
          <span className="muted">
            Страница {page} из {pages}
          </span>
          <button
            type="button"
            className="btn"
            aria-disabled={!canGoForward}
            onClick={() => {
              if (canGoForward) setPage(page + 1)
            }}
          >
            Дальше
          </button>
        </nav>
      )}
    </aside>
  )
}
