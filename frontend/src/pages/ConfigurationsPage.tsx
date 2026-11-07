import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { Config } from '../api'
import { createRun, deleteConfig, isAbortError, listConfigs } from '../api'
import { EmptyState, ErrorBox, Spinner } from '../components'
import { formatDateTime } from '../lib/format'
import './ConfigurationsPage.css'

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Запрос не удался'
}

/** Сохранённые конфигурации пользователя: запустить, открыть в форме или удалить. */
export function ConfigurationsPage() {
  const navigate = useNavigate()
  const [configs, setConfigs] = useState<Config[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  /** id конфигурации, по которой сейчас идёт запрос; пока он идёт, кнопки во всех строках отключены. */
  const [busyId, setBusyId] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setConfigs(await listConfigs())
      setError(null)
    } catch (e) {
      if (isAbortError(e)) return
      setError(errorMessage(e))
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react/set-state-in-effect -- загрузка данных эффектом и есть синхронизация с внешней системой
    void load()
  }, [load])

  async function handleRun(config: Config) {
    setActionError(null)
    setBusyId(config.id)
    try {
      const run = await createRun(config.id)
      navigate(`/runs/${encodeURIComponent(run.id)}`)
    } catch (e) {
      setActionError(errorMessage(e))
      setBusyId(null)
    }
  }

  async function handleDelete(config: Config) {
    if (!window.confirm(`Удалить конфигурацию «${config.name}»? Запуски по ней останутся.`)) return
    setActionError(null)
    setBusyId(config.id)
    try {
      await deleteConfig(config.id)
      setConfigs((list) => (list ?? []).filter((item) => item.id !== config.id))
    } catch (e) {
      setActionError(errorMessage(e))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>Конфигурации</h1>
        <Link to="/runs/new" className="btn btn--primary">
          Новый прогон
        </Link>
      </div>

      <p className="muted">
        Конфигурация — сохранённый набор настроек прогона: датасет, этапы и проверки. «Запустить»
        создаёт новый прогон с этими настройками.
      </p>

      {error !== null && <ErrorBox message={error} onRetry={() => void load()} />}
      {actionError !== null && <ErrorBox message={actionError} />}

      {error === null && configs === null && (
        <div className="panel">
          <Spinner label="Загружаем конфигурации" />
        </div>
      )}

      {configs !== null && configs.length === 0 && (
        <EmptyState
          title="Сохранённых конфигураций нет"
          hint="Конфигурация сохраняется на странице «Новый прогон»."
          action={
            <Link to="/runs/new" className="btn btn--primary">
              Новый прогон
            </Link>
          }
        />
      )}

      {configs !== null && configs.length > 0 && (
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Название</th>
                <th scope="col">Датасет</th>
                <th scope="col">Обновлена</th>
                <th scope="col">
                  <span className="visually-hidden">Действия</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {configs.map((config) => (
                <tr key={config.id}>
                  <td>{config.name}</td>
                  <td className="mono">{config.dataset}</td>
                  <td>{formatDateTime(config.updated_at)}</td>
                  <td>
                    <div className="row-actions">
                      <button
                        type="button"
                        className="btn btn--primary"
                        disabled={busyId !== null}
                        onClick={() => void handleRun(config)}
                      >
                        Запустить
                      </button>
                      <Link
                        className="btn"
                        to={`/runs/new?config=${encodeURIComponent(config.id)}`}
                      >
                        Открыть в форме
                      </Link>
                      <button
                        type="button"
                        className="btn btn--danger"
                        disabled={busyId !== null}
                        onClick={() => void handleDelete(config)}
                      >
                        Удалить
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
