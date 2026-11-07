import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { RunListItem } from '../api'
import { isAbortError, listRuns } from '../api'
import { EmptyState, ErrorBox, Spinner, StatusBadge } from '../components'
import { formatDateTime } from '../lib/format'
import './RunsListPage.css'

/** Список прогонов: первый экран приложения. Свежие сверху. */
export function RunsListPage() {
  const [runs, setRuns] = useState<RunListItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

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
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr
                  key={run.id}
                  className="runs-table__row"
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
                  </td>
                  <td>{run.name}</td>
                  <td className="mono">{run.dataset}</td>
                  <td>{formatDateTime(run.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
