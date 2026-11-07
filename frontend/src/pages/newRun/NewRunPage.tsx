import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { createConfig, createRun, getDatasets, isAbortError } from '../../api'
import type { Config, ConfigInput, Dataset, UploadResponse } from '../../api'
import { ErrorBox, Spinner } from '../../components'
import { DataSection } from './DataSection'
import { PipelinePreview } from './PipelinePreview'
import {
  BUILTIN_AGGREGATE,
  BUILTIN_NORMALIZE,
  DEFAULT_ARRAY_MODES,
  DEFAULT_BUCKETS,
  defaultConfigName,
} from './defaults'
import './NewRunPage.css'

/**
 * Что страница делает сейчас. «Запустить» — это две ручки подряд
 * (`POST /api/configs`, потом `POST /api/runs`), поэтому фаз две, а не одна.
 */
type Phase = 'idle' | 'saving' | 'starting'

const PHASE_LABEL: Record<Phase, string> = {
  idle: '',
  saving: 'Сохраняем конфигурацию',
  starting: 'Запускаем прогон',
}

/** `message` у ошибки API уже человеческий и русский — показываем как есть. */
function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Запрос не удался'
}

/** Настройка прогона: выбрать датасет, сохранить конфигурацию, запустить. */
export function NewRunPage() {
  const navigate = useNavigate()

  /**
   * Пользователь ещё на этой странице. Запросы на создание не отменяем: сервер
   * мог их уже выполнить, и оборвать POST на полпути — значит не знать, создалось
   * оно или нет. Вместо этого смотрим после ответа, здесь ли ещё человек.
   */
  const onPage = useRef(true)
  useEffect(() => {
    // В StrictMode эффект проходит дважды, поэтому флаг взводим заново, а не только гасим.
    onPage.current = true
    return () => {
      onPage.current = false
    }
  }, [])

  // ─── Загрузка списка датасетов ────────────────────────────────────────────
  const [datasets, setDatasets] = useState<Dataset[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  // Смена значения перезапускает эффект — так работает «Повторить».
  const [reloadKey, setReloadKey] = useState(0)

  /** Повторная попытка: сбрасываем состояние здесь, а не внутри эффекта. */
  function reloadDatasets() {
    setDatasets(null)
    setLoadError(null)
    setReloadKey((key) => key + 1)
  }

  useEffect(() => {
    const controller = new AbortController()

    getDatasets({ signal: controller.signal })
      .then(setDatasets)
      .catch((error: unknown) => {
        // Отменённый запрос — штатная ситуация, показывать нечего.
        if (isAbortError(error)) return
        setLoadError(errorMessage(error))
      })

    return () => controller.abort()
  }, [reloadKey])

  // ─── Поля формы ───────────────────────────────────────────────────────────
  const [name, setName] = useState(defaultConfigName)
  const [datasetId, setDatasetId] = useState('')
  const [ignorePaths, setIgnorePaths] = useState<string[]>([])

  // ─── Отправка ─────────────────────────────────────────────────────────────
  const [phase, setPhase] = useState<Phase>('idle')
  const [submitError, setSubmitError] = useState<string | null>(null)
  /** Конфигурация упала не на сохранении, а на запуске: это промежуточное состояние. */
  const [runNotStarted, setRunNotStarted] = useState(false)
  /** Последняя сохранённая конфигурация — чтобы при повторном нажатии не плодить дубли. */
  const [savedConfig, setSavedConfig] = useState<Config | null>(null)
  /** Форму меняли после сохранения, значит сохранённая конфигурация устарела. */
  const [changedSinceSave, setChangedSinceSave] = useState(false)

  const busy = phase !== 'idle'
  const canSubmit = datasetId !== '' && !busy
  const savedAndUnchanged = savedConfig !== null && !changedSinceSave
  /**
   * Прошлый запуск упал на втором шаге и форму с тех пор не меняли — значит
   * повторное нажатие переиспользует конфигурацию. Если форму поправили,
   * обещать «вторая не создастся» уже нельзя: следующий запуск создаст новую.
   */
  const willReuseConfig = runNotStarted && !changedSinceSave

  function handleNameChange(value: string) {
    setName(value)
    setChangedSinceSave(true)
  }

  function selectDataset(id: string, technicalFields: string[]) {
    setDatasetId(id)
    // Технические поля различаются у всех заявок — предзаполняем ими «Не сравнивать» (п. 2.1).
    // Смена датасета список перезаписывает: пути прежнего датасета к новому отношения не имеют.
    setIgnorePaths(technicalFields)
    setChangedSinceSave(true)
  }

  function handleDatasetChange(id: string) {
    selectDataset(id, datasets?.find((dataset) => dataset.id === id)?.technical_fields ?? [])
  }

  /** Данные загружены: новый датасет попадает в список и сразу выбран. */
  function handleUploaded({ dataset }: UploadResponse) {
    setDatasets((list) =>
      list === null || list.some((item) => item.id === dataset.id) ? list : [...list, dataset],
    )
    selectDataset(dataset.id, dataset.technical_fields)
  }

  function handleIgnorePathsChange(paths: string[]) {
    setIgnorePaths(paths)
    setChangedSinceSave(true)
  }

  function buildInput(): ConfigInput {
    return {
      name: name.trim() === '' ? defaultConfigName() : name.trim(),
      dataset: datasetId,
      normalize: BUILTIN_NORMALIZE,
      aggregate: BUILTIN_AGGREGATE,
      checks: [], // проверки в MVP не подключаем
      ignore_paths: ignorePaths,
      array_modes: { ...DEFAULT_ARRAY_MODES },
      buckets: { ...DEFAULT_BUCKETS },
    }
  }

  /**
   * Отдаёт конфигурацию, по которой запускать прогон. Если её уже сохранили
   * и форму с тех пор не меняли — переиспользует, а не создаёт вторую.
   */
  async function ensureConfig(): Promise<Config> {
    if (savedConfig !== null && !changedSinceSave) return savedConfig
    const config = await createConfig(buildInput())
    setSavedConfig(config)
    setChangedSinceSave(false)
    return config
  }

  async function handleSave() {
    if (!canSubmit) return
    setSubmitError(null)
    setRunNotStarted(false)
    setPhase('saving')
    try {
      await ensureConfig()
    } catch (error) {
      if (onPage.current) setSubmitError(errorMessage(error))
    } finally {
      setPhase('idle')
    }
  }

  /** Отправка формы (в том числе Enter) — основное действие, «Запустить». */
  async function handleStart(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    // Защита от двойного нажатия: кнопки уже заблокированы, но Enter быстрее клика.
    if (!canSubmit) return

    setSubmitError(null)
    setRunNotStarted(false)

    let config: Config
    setPhase('saving')
    try {
      config = await ensureConfig()
    } catch (error) {
      if (onPage.current) setSubmitError(errorMessage(error))
      setPhase('idle')
      return
    }

    // Пока сохранялась конфигурация, человек мог уйти со страницы — запускать не его дело.
    if (!onPage.current) {
      setPhase('idle')
      return
    }

    setPhase('starting')
    try {
      const run = await createRun(config.id)
      // Человек успел уйти в другой раздел — утаскивать его оттуда нельзя.
      // Прогон не потеряется: он виден в списке «Прогоны».
      if (!onPage.current) return
      navigate(`/runs/${run.id}`)
    } catch (error) {
      if (onPage.current) {
        setSubmitError(errorMessage(error))
        // Конфигурация уже на сервере — об этом надо сказать прямо,
        // иначе человек нажмёт второй раз и будет думать, что создал дубль.
        setRunNotStarted(true)
      }
      setPhase('idle')
    }
  }

  if (loadError !== null) {
    return (
      <>
        <PageHead />
        <ErrorBox message={loadError} onRetry={reloadDatasets} />
      </>
    )
  }

  if (datasets === null) {
    return (
      <>
        <PageHead />
        <Spinner label="Загружаем датасеты" />
      </>
    )
  }

  return (
    <form className="new-run" onSubmit={handleStart}>
      <PageHead />

      {/* Пока идут запросы, форму целиком блокирует fieldset — руками поля не отключаем. */}
      <fieldset className="new-run__fields" disabled={busy}>
        <DataSection
          name={name}
          onNameChange={handleNameChange}
          datasets={datasets}
          selectedId={datasetId}
          onSelect={handleDatasetChange}
          onUploaded={handleUploaded}
          onReload={reloadDatasets}
          ignorePaths={ignorePaths}
          onIgnorePathsChange={handleIgnorePathsChange}
        />
        <PipelinePreview />
      </fieldset>

      {submitError !== null && (
        <div className="new-run__error">
          <ErrorBox message={submitError} />
          {willReuseConfig && (
            <p className="muted new-run__error-note">
              Конфигурация сохранена, запуск не стартовал. Нажмите «Запустить» ещё раз — вторая
              конфигурация не создастся.
            </p>
          )}
        </div>
      )}

      <div className="new-run__actions">
        <div className="new-run__status" aria-live="polite">
          {busy && <Spinner label={PHASE_LABEL[phase]} />}
          {!busy && savedAndUnchanged && (
            <span className="muted">Конфигурация «{savedConfig.name}» сохранена</span>
          )}
        </div>

        <button type="button" className="btn" onClick={handleSave} disabled={!canSubmit}>
          Сохранить конфигурацию
        </button>
        <button type="submit" className="btn btn--primary" disabled={!canSubmit}>
          {willReuseConfig ? 'Запустить ещё раз' : 'Запустить'}
        </button>
      </div>
    </form>
  )
}

function PageHead() {
  return (
    <div className="page-head">
      <h1>Новый прогон</h1>
    </div>
  )
}
