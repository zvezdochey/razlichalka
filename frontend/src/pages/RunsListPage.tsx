import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { RunListItem } from '../api'
import { getRun, getSummary, isAbortError, listRuns } from '../api'
import { EmptyState, ErrorBox, Spinner, StatusBadge } from '../components'
import { formatDateTime } from '../lib/format'
import './RunsListPage.css'

/** Сколько запросов за итогами строк летит одновременно. */
const MAX_PARALLEL = 3
/** Сколько строк показываем: итоги грузим только для них. */
const PAGE_SIZE = 20

/** Что показываем в колонках «Сменили решение» и «FAIL»; `null` — ещё грузится, `'error'` — не вышло. */
type RowInfo = { changed: number; fail: number | null } | { reason: string } | 'error'

const ERROR_TEXT = 'Прогон не завершён — запустите повторно'
const INTERRUPTED_TEXT = 'Прерван перезапуском сервера — запустите повторно'

/** Грузит итоги для строк: ready — из summary, error — причину из статуса. Не больше MAX_PARALLEL запросов сразу. */
function useRowInfo(runs: RunListItem[] | null): Record<string, RowInfo> {
  const [info, setInfo] = useState<Record<string, RowInfo>>({})
  const started = useRef(new Set<string>())

  useEffect(() => {
    if (runs === null) return
    const controller = new AbortController()
    const startedIds = started.current
    const queue = runs
      .slice(0, PAGE_SIZE)
      .filter((run) => (run.status === 'ready' || run.status === 'error') && !startedIds.has(run.id))
    queue.forEach((run) => startedIds.add(run.id))
    // Строки этого запуска, по которым ответа ещё нет. Если эффект перезапустится
    // (StrictMode в dev, повторная загрузка списка), их надо снять с отметки сразу,
    // иначе новый запуск их пропустит и в колонках навсегда останется «…».
    const pending = new Set(queue.map((run) => run.id))

    async function load(run: RunListItem) {
      try {
        if (run.status === 'ready') {
          const summary = await getSummary(run.id, { signal: controller.signal })
          setInfo((prev) => ({
            ...prev,
            [run.id]: { changed: summary.decision_changed, fail: summary.checks_fail ?? null },
          }))
        } else {
          const status = await getRun(run.id, { signal: controller.signal })
          if (status.error?.code === 'interrupted') {
            setInfo((prev) => ({ ...prev, [run.id]: { reason: INTERRUPTED_TEXT } }))
          } else {
            setInfo((prev) => ({ ...prev, [run.id]: 'error' }))
          }
        }
        pending.delete(run.id)
      } catch (e) {
        // Отмена может прийти, пока читается тело ответа, — тогда клиент вернёт
        // не AbortError, а свою ошибку. Поэтому смотрим ещё и на сам сигнал.
        if (isAbortError(e) || controller.signal.aborted) return
        pending.delete(run.id)
        setInfo((prev) => ({ ...prev, [run.id]: 'error' }))
      }
    }

    // Простая очередь: MAX_PARALLEL «рабочих» берут строки по одной.
    async function worker() {
      for (let run = queue.shift(); run !== undefined; run = queue.shift()) await load(run)
    }
    for (let i = 0; i < MAX_PARALLEL; i++) void worker()

    return () => {
      controller.abort()
      pending.forEach((id) => startedIds.delete(id))
    }
  }, [runs])

  return info
}

/** Список прогонов: первый экран приложения. Свежие сверху. */
export function RunsListPage() {
  const [runs, setRuns] = useState<RunListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()
  const info = useRowInfo(runs)

  const load = useCallback(async () => {
    try {
      setRuns(await listRuns())
      setError(null)
    } catch (e) {
      if (isAbortError(e)) return
      setError(e instanceof Error ? e.message : 'Не удалось загрузить список прогонов')
    }
  }, [])

  // Загрузка при первом показе — ровно то, для чего эффект и нужен: синхронизация
  // с внешней системой. Правило не отличает это от setState в рендере.
  useEffect(() => {
    // eslint-disable-next-line react/set-state-in-effect -- загрузка данных эффектом и есть синхронизация с внешней системой
    void load()
  }, [load])

  return (
    <>
      <div className="page-head">
        <h1>Прогоны</h1>
        <Link to="/runs/new" className="btn btn--primary">
          Новый прогон
        </Link>
      </div>

      {error !== null && <ErrorBox message={error} onRetry={() => void load()} />}

      {error === null && runs === null && (
        <div className="panel">
          <Spinner label="Загружаем прогоны" />
        </div>
      )}

      {runs !== null && runs.length === 0 && (
        <EmptyState
          title="Прогонов пока нет"
          hint="Нажмите «Новый прогон», чтобы сравнить решения двух версий СПР."
          action={
            <Link to="/runs/new" className="btn btn--primary">
              Новый прогон
            </Link>
          }
        />
      )}

      {runs !== null && runs.length > 0 && (
        <div className="table-scroll runs-table">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Прогон</th>
                <th scope="col">Статус</th>
                <th scope="col">Конфигурация</th>
                <th scope="col">Датасет</th>
                <th scope="col">Создан</th>
                <th scope="col">Сменили решение</th>
                <th scope="col">FAIL</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run, index) => {
                const row = info[run.id]
                const interrupted = typeof row === 'object' && 'reason' in row
                const loaded = typeof row === 'object' && 'changed' in row
                // Для ready ждём ответ — «…», при ошибке — «—». Для остальных статусов итогов нет.
                const loading = run.status === 'ready' && row === undefined
                const placeholder = loading ? '…' : '—'
                return (
                <tr
                  key={run.id}
                  className={index === 0 ? 'runs-table__row runs-table__row--latest' : 'runs-table__row'}
                  title={interrupted ? row.reason : run.status === 'error' ? ERROR_TEXT : undefined}
                  onClick={() => navigate(`/runs/${encodeURIComponent(run.id)}`)}
                >
                  <td>
                    {/* Ссылка, а не только клик по строке: так работает клавиатура и «открыть в новой вкладке». */}
                    <Link
                      className="mono runs-table__link"
                      to={`/runs/${encodeURIComponent(run.id)}`}
                      onClick={(event) => event.stopPropagation()}
                    >
                      {run.id}
                    </Link>
                  </td>
                  <td>
                    {/* В списке поля `error` нет, поэтому отмену от падения не отличить. */}
                    <StatusBadge status={run.status} errorKnown={false} />
                    {interrupted && <div className="muted runs-table__reason">{row.reason}</div>}
                  </td>
                  <td>{run.name}</td>
                  <td className="mono runs-table__dataset" title={run.dataset}>{run.dataset}</td>
                  <td className="runs-table__date">{formatDateTime(run.created_at)}</td>
                  <td className="num">{loaded ? row.changed.toLocaleString('ru-RU') : placeholder}</td>
                  <td className="num">{loaded ? row.fail === null ? '—' : row.fail.toLocaleString('ru-RU') : placeholder}</td>
                </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
