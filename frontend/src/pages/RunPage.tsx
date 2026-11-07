import { useCallback, useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import type { RunStatus } from '../api'
import { ApiRequestError, cancelRun, downloadReport, getRun, isAbortError, openReport } from '../api'
import { ErrorBox, Spinner, StatusBadge } from '../components'
import { usePolling } from '../hooks/usePolling'
import { DASH, formatDateTime } from '../lib/format'
import './RunPage.css'
import { RetryRunButton } from './run/RetryRunButton'
import { ProgressBar } from './run/ProgressBar'
import type { RunContext } from './run/runContext'
import { STAGE_ACTIVE_TEXT } from './run/stages'

/** Раз в секунду, пока запуск идёт — как договорились в api.md п. 5.2. */
const POLL_INTERVAL_MS = 1000

function isFinished(run: RunStatus | null): boolean {
  return run !== null && (run.status === 'ready' || run.status === 'error')
}

/**
 * Прогон: контекст сверху, вкладки — вложенные маршруты, чтобы ссылкой можно было
 * поделиться. Состояние ничего не помнит между перезагрузками: всё берётся по `id`
 * из URL, поэтому F5 не теряет запуск.
 */
export function RunPage() {
  const { id = '' } = useParams<{ id: string }>()
  const [run, setRun] = useState<RunStatus | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  // Прогон не нашли: чаще всего он создан под другим именем пользователя (у каждого имени свои прогоны).
  const [loadNotFound, setLoadNotFound] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [cancelling, setCancelling] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [opening, setOpening] = useState(false)

  const navigate = useNavigate()
  const { pathname } = useLocation()

  // Какой прогон сейчас открыт. Ответ для прежнего id мог прийти уже после перехода
  // на другой прогон — его выбрасываем, иначе на экране застрянет чужой статус.
  const currentId = useRef(id)
  useEffect(() => {
    currentId.current = id
  }, [id])

  const load = useCallback(async () => {
    try {
      const next = await getRun(id)
      if (currentId.current !== id) return
      setRun(next)
      setLoadError(null)
      setLoadNotFound(false)
    } catch (e) {
      if (isAbortError(e) || currentId.current !== id) return
      setLoadError(e instanceof Error ? e.message : 'Не удалось получить статус запуска')
      setLoadNotFound(e instanceof ApiRequestError && e.status === 404)
    }
  }, [id])

  // Сменился прогон в URL — показываем не чужой статус, а чистое ожидание.
  // Правка состояния прямо в рендере — штатный приём React для «props изменились»,
  // эффект здесь дал бы лишний кадр с данными предыдущего прогона.
  const [shownRunId, setShownRunId] = useState(id)
  if (shownRunId !== id) {
    setShownRunId(id)
    setRun(null)
    setLoadError(null)
    setLoadNotFound(false)
    setActionError(null)
  }

  // Загрузка статуса при первом показе и после смены прогона.
  useEffect(() => {
    // eslint-disable-next-line react/set-state-in-effect -- загрузка данных эффектом и есть синхронизация с внешней системой
    void load()
  }, [load])

  usePolling(load, POLL_INTERVAL_MS, isFinished(run))

  // Расчёт закончился, а человек смотрит журнал — открываем «Обзор» сами.
  // Только на переходе статуса: если он сам зашёл в журнал готового прогона,
  // выкидывать его оттуда нельзя.
  const previousStatus = useRef<RunStatus['status'] | null>(null)
  useEffect(() => {
    if (run === null) return
    const previous = previousStatus.current
    previousStatus.current = run.status
    if (previous === null || previous === 'ready') return
    if (run.status !== 'ready') return
    if (!pathname.endsWith('/log')) return
    navigate(`/runs/${encodeURIComponent(run.id)}/overview`, { replace: true })
  }, [run, pathname, navigate])

  const onCancel = async () => {
    setCancelling(true)
    setActionError(null)
    try {
      await cancelRun(id)
      await load()
    } catch (e) {
      if (!isAbortError(e)) {
        setActionError(e instanceof Error ? e.message : 'Не удалось остановить запуск')
      }
    } finally {
      setCancelling(false)
    }
  }

  const onDownload = async () => {
    setDownloading(true)
    setActionError(null)
    try {
      await downloadReport(id)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Не удалось скачать отчёт')
    } finally {
      setDownloading(false)
    }
  }

  const onOpenReport = async () => {
    setOpening(true)
    setActionError(null)
    try {
      await openReport(id)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Не удалось открыть отчёт')
    } finally {
      setOpening(false)
    }
  }

  const running = run !== null && (run.status === 'pending' || run.status === 'running')
  const currentStage = run?.current_stage ?? null
  // Текст «что сейчас происходит» виден на любой вкладке, не только в журнале:
  // требование ТЗ — «понятно, что происходит», пока идёт долгий этап.
  const activeText = currentStage === null ? null : STAGE_ACTIVE_TEXT[currentStage]

  return (
    <>
      <div className="page-head run-head">
        <div>
          <div className="overline">Прогон</div>
          <h1 className="mono">{id}</h1>
          <dl className="run-meta">
            <div>
              <dt>Датасет</dt>
              <dd className="mono">{run?.dataset ?? DASH}</dd>
            </div>
            <div>
              <dt>Конфигурация</dt>
              <dd className="mono">{run?.config_id ?? DASH}</dd>
            </div>
            <div>
              <dt>Запущен</dt>
              <dd>{formatDateTime(run?.created_at ?? null)}</dd>
            </div>
            <div>
              <dt>Статус</dt>
              <dd>
                {run === null ? DASH : <StatusBadge status={run.status} error={run.error} />}
              </dd>
            </div>
          </dl>
        </div>

        <div className="run-actions">
          {running && (
            <button type="button" className="btn" onClick={onCancel} disabled={cancelling}>
              {cancelling ? 'Останавливаем…' : 'Остановить'}
            </button>
          )}
          {run?.status === 'ready' && (
            <>
              <button type="button" className="btn" onClick={onOpenReport} disabled={opening}>
                {opening ? 'Открываем…' : 'Открыть отчёт в новой вкладке'}
              </button>
              <button type="button" className="btn btn--primary" onClick={onDownload} disabled={downloading}>
                {downloading ? 'Готовим файл…' : 'Скачать HTML'}
              </button>
            </>
          )}
        </div>
      </div>

      {running && (
        <div className="run-progress">
          {activeText !== null && <div className="run-progress__text">{activeText}</div>}
          <ProgressBar done={run.progress.done} total={run.progress.total} />
        </div>
      )}

      {/* Сервер перезапустили посреди расчёта: причина и «Повторить». В журнале то же самое
          уже рисует LogTab, поэтому там верхний блок не показываем. */}
      {run?.error?.code === 'interrupted' && !pathname.endsWith('/log') && (
        <div className="run-notice">
          <p>{run.error.message}</p>
          <RetryRunButton configId={run.config_id} />
        </div>
      )}
      {loadError !== null && (
        <div className="run-notice">
          <ErrorBox message={loadError} onRetry={() => void load()} />
          {loadNotFound && (
            <p className="muted">
              Возможно, запуск создан под другим пользователем — имя в правом верхнем углу
              можно сменить (у каждого имени свои прогоны).
            </p>
          )}
        </div>
      )}
      {actionError !== null && (
        <div className="run-notice">
          <ErrorBox message={actionError} />
        </div>
      )}

      <nav className="tabs" aria-label="Разделы прогона">
        <NavLink to="overview" className="tabs__item">
          Обзор
        </NavLink>
        <NavLink to="pivot" className="tabs__item">Сводная</NavLink>
        <NavLink to="apps" className="tabs__item">
          Заявки
        </NavLink>
        <NavLink to="checks" className="tabs__item">
          Проверки
        </NavLink>
        <NavLink to="log" className="tabs__item">
          Журнал
        </NavLink>
      </nav>

      {run === null && loadError === null ? (
        <div className="panel">
          <Spinner label="Читаем статус запуска" />
        </div>
      ) : (
        <Outlet context={{ runId: id, run, reloadRun: () => void load() } satisfies RunContext} />
      )}
    </>
  )
}
