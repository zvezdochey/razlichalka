import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { createRun, getConfig, isAbortError, listConfigs, updateConfig } from '../../api'
import type { Config, ConfigDetail, ConfigUpdate } from '../../api'
import { ErrorBox, Spinner } from '../../components'
import { formatDateTime } from '../../lib/format'
import { confirmLeave } from '../../lib/leaveGuard'

type Phase = 'idle' | 'adding' | 'starting'

const PHASE_LABEL: Record<Phase, string> = {
  idle: '',
  adding: 'Добавляем проверку в конфигурацию',
  starting: 'Запускаем прогон',
}

/** Тело PUT — то, что пришло в GET, без `id` и `updated_at`. Всё остальное
 *  (пути-исключения, правила массивов, бакеты) возвращаем как было. */
function toUpdate(config: ConfigDetail, checks: string[]): ConfigUpdate {
  const { id: _id, updated_at: _updatedAt, ...body } = config
  return { ...body, checks }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Запрос не удался'
}

type RunWithCheckProps = {
  procedureId: string
  /** Почему кнопку сейчас нажать нельзя (например, есть несохранённые правки). */
  blockedReason: string | null
}

/**
 * Шаг 7 демо одной кнопкой: выбрать конфигурацию → дописать в неё проверку
 * (`PUT /configs/{id}`) → `POST /runs` → страница нового прогона.
 */
export function RunWithCheck({ procedureId, blockedReason }: RunWithCheckProps) {
  const navigate = useNavigate()
  const [configs, setConfigs] = useState<Config[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [configId, setConfigId] = useState('')
  const [phase, setPhase] = useState<Phase>('idle')
  const [error, setError] = useState<string | null>(null)
  // Проверку уже дописали, упал только запуск: повторное нажатие не трогает конфигурацию.
  const [addedTo, setAddedTo] = useState<string | null>(null)

  // Запросы на изменение не отменяем при уходе (как на «Новом прогоне»): оборванный
  // POST мог выполниться на сервере. Просто не переходим, если человек уже ушёл.
  const onPage = useRef(true)
  useEffect(() => {
    onPage.current = true
    return () => {
      onPage.current = false
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    listConfigs({ signal: controller.signal })
      .then((list) => {
        setConfigs(list)
        // Бэк отдаёт свежие первыми — их и предлагаем.
        setConfigId((current) => current || (list[0]?.id ?? ''))
      })
      .catch((e: unknown) => {
        if (isAbortError(e)) return
        setLoadError(errorMessage(e))
      })
    return () => controller.abort()
  }, [reloadKey])

  // Другая проверка или другая конфигурация — прошлая неудача к ним не относится.
  useEffect(() => {
    // eslint-disable-next-line react/set-state-in-effect -- сброс при смене входных данных
    setAddedTo(null)
    setError(null)
  }, [procedureId, configId])

  async function handleRun() {
    if (phase !== 'idle' || configId === '') return
    setError(null)
    try {
      if (addedTo !== configId) {
        setPhase('adding')
        const config = await getConfig(configId)
        if (!config.checks.includes(procedureId)) {
          await updateConfig(configId, toUpdate(config, [...config.checks, procedureId]))
        }
        setAddedTo(configId)
      }
      setPhase('starting')
      const run = await createRun(configId)
      if (onPage.current) navigate(`/runs/${encodeURIComponent(run.id)}`)
    } catch (e) {
      if (onPage.current) setError(errorMessage(e))
    } finally {
      if (onPage.current) setPhase('idle')
    }
  }

  if (loadError !== null) {
    return (
      <section className="proc-run panel">
        <h2>Подключить к прогону</h2>
        <ErrorBox
          message={loadError}
          onRetry={() => {
            setLoadError(null)
            setReloadKey((key) => key + 1)
          }}
        />
      </section>
    )
  }

  return (
    <section className="proc-run panel" aria-labelledby="proc-run-title">
      <h2 id="proc-run-title">Подключить к прогону</h2>
      <p className="muted">
        Проверка добавится в выбранную конфигурацию, и по ней сразу стартует новый прогон. Её
        строки появятся во вкладке «Проверки» вместе с остальными.
      </p>

      {configs === null && <Spinner label="Читаем конфигурации" />}

      {configs !== null && configs.length === 0 && (
        <p>
          Конфигураций пока нет. Создайте прогон на странице{' '}
          <Link to="/runs/new" onClick={(event) => !confirmLeave() && event.preventDefault()}>
            «Новый прогон»
          </Link> — конфигурация сохранится вместе с ним.
        </p>
      )}

      {configs !== null && configs.length > 0 && (
        <div className="proc-run__row">
          <label className="proc-run__field">
            <span className="overline">Конфигурация</span>
            <select
              className="select"
              value={configId}
              disabled={phase !== 'idle'}
              onChange={(event) => setConfigId(event.target.value)}
            >
              {configs.map((config) => (
                <option key={config.id} value={config.id}>
                  {config.name} · {config.dataset} · {formatDateTime(config.updated_at)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn btn--primary"
            disabled={phase !== 'idle' || blockedReason !== null}
            onClick={() => void handleRun()}
          >
            {addedTo === configId ? 'Запустить ещё раз' : 'Добавить в конфигурацию и запустить'}
          </button>
          <span className="muted" aria-live="polite">
            {phase !== 'idle' ? `${PHASE_LABEL[phase]}…` : (blockedReason ?? '')}
          </span>
        </div>
      )}

      {error !== null && (
        <div className="proc-run__error">
          <ErrorBox message={error} />
          {addedTo === configId && (
            <p className="muted">Проверка добавлена в конфигурацию, запуск не стартовал.</p>
          )}
        </div>
      )}
    </section>
  )
}
