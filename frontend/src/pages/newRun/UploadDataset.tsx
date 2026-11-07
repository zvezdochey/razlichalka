import { useEffect, useId, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { isAbortError, uploadDataset } from '../../api'
import type { UploadResponse } from '../../api'
import { ErrorBox, Spinner } from '../../components'

type UploadDatasetProps = {
  /** Датасет создан: страница добавляет его в список и выбирает. */
  onUploaded: (result: UploadResponse) => void
}

const ACCEPT = '.json,.xml,.csv,.zip'

/** «3 файла», «1 файл», «5 файлов» — для подписи под выбором. */
function filesLabel(count: number): string {
  const last = count % 10
  const lastTwo = count % 100
  if (last === 1 && lastTwo !== 11) return `${count} файл`
  if (last >= 2 && last <= 4 && (lastTwo < 12 || lastTwo > 14)) return `${count} файла`
  return `${count} файлов`
}

/** Короткая сводка принятого: сколько заявок и из каких форматов. */
function receivedLine(result: UploadResponse): string {
  const parts = (['BEFORE', 'AFTER'] as const).map((source) => {
    const r = result.received[source]
    const formats = (['json', 'xml', 'csv'] as const)
      .filter((format) => r[format] > 0)
      .map((format) => `${format.toUpperCase()} ${r[format]}`)
    const label = result.dataset.sources[source]
    const name = label === source ? source : `${source} (${label})`
    const count = r.applications.toLocaleString('ru-RU')
    return formats.length === 0 ? `${name}: ${count}` : `${name}: ${count} (${formats.join(', ')})`
  })
  return parts.join(' · ')
}

/**
 * Загрузка своих данных (docs/api.md п. 2.2). Принимает JSON, XML, CSV и ZIP, бэк приводит всё
 * к одному виду. Это не `<form>`: блок лежит внутри формы прогона, а Enter здесь запускать прогон не должен.
 */
export function UploadDataset({ onUploaded }: UploadDatasetProps) {
  const id = useId()
  const [before, setBefore] = useState<File[]>([])
  const [after, setAfter] = useState<File[]>([])
  const [beforeLabel, setBeforeLabel] = useState('')
  const [afterLabel, setAfterLabel] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<UploadResponse | null>(null)
  const controller = useRef<AbortController | null>(null)
  const beforeInput = useRef<HTMLInputElement>(null)
  const afterInput = useRef<HTMLInputElement>(null)

  // Ушли со страницы — загрузку обрываем, иначе она потом молча сменит выбранный датасет.
  useEffect(() => () => controller.current?.abort(), [])

  function chooseFiles(set: (files: File[]) => void) {
    return (files: File[]) => {
      set(files)
      setDone(null) // сообщение про прошлую загрузку устарело
    }
  }

  const canUpload = before.length > 0 && after.length > 0 && !busy

  async function handleUpload() {
    if (!canUpload) return
    setBusy(true)
    setError(null)
    setDone(null)
    const own = new AbortController()
    controller.current = own
    try {
      const result = await uploadDataset({ before, after, beforeLabel, afterLabel }, { signal: own.signal })
      setDone(result)
      // Файлы больше не нужны: освобождаем и поля выбора.
      setBefore([])
      setAfter([])
      if (beforeInput.current) beforeInput.current.value = ''
      if (afterInput.current) afterInput.current.value = ''
      onUploaded(result)
    } catch (cause) {
      if (!isAbortError(cause)) setError(cause instanceof Error ? cause.message : 'Загрузка не удалась')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="upload" role="group" aria-labelledby={`${id}-title`}>
      <h3 className="upload__title" id={`${id}-title`}>
        Загрузить свои данные
      </h3>
      <p className="field__hint muted">
        Принимаем JSON, XML и CSV (по файлу на заявку) или .zip с такими файлами. Можно выбрать сразу
        все файлы. До 20 МБ на файл и до 150 МБ за раз. Сервер приведёт их к одному виду, форматы срезов могут отличаться.
      </p>

      <div className="upload__grid">
        <SourcePicker
          idBase={`${id}-before`}
          title="Срез «до» (BEFORE)"
          placeholder="MASTER"
          files={before}
          label={beforeLabel}
          inputRef={beforeInput}
          onFiles={chooseFiles(setBefore)}
          onLabel={setBeforeLabel}
          disabled={busy}
        />
        <SourcePicker
          idBase={`${id}-after`}
          title="Срез «после» (AFTER)"
          placeholder="BETA"
          files={after}
          label={afterLabel}
          inputRef={afterInput}
          onFiles={chooseFiles(setAfter)}
          onLabel={setAfterLabel}
          disabled={busy}
        />
      </div>

      <div className="upload__actions">
        <button type="button" className="btn" onClick={handleUpload} disabled={!canUpload}>
          Загрузить
        </button>
        <div>
          {busy && <Spinner label="Загружаем и приводим к одному виду" />}
          {done !== null && !busy && (
            <span className="muted" role="status">
              Готово: датасет {done.dataset.id}. {receivedLine(done)}
            </span>
          )}
        </div>
      </div>

      {done !== null && (done.applications_only_before > 0 || done.applications_only_after > 0) && (
        <p className="field__hint muted">
          Только в «до»: {done.applications_only_before}, только в «после»: {done.applications_only_after}.
          Такие заявки в сравнение не попадут: сравниваем пары.
        </p>
      )}

      {error !== null && <ErrorBox message={error} />}
    </div>
  )
}

type SourcePickerProps = {
  idBase: string
  title: string
  placeholder: string
  files: File[]
  label: string
  inputRef: RefObject<HTMLInputElement | null>
  onFiles: (files: File[]) => void
  onLabel: (label: string) => void
  disabled: boolean
}

function SourcePicker({
  idBase,
  title,
  placeholder,
  files,
  label,
  inputRef,
  onFiles,
  onLabel,
  disabled,
}: SourcePickerProps) {
  return (
    <div className="upload__source">
      <label className="field__label" htmlFor={`${idBase}-files`}>
        {title}
      </label>
      <input
        id={`${idBase}-files`}
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT}
        className="input upload__file"
        aria-describedby={`${idBase}-count`}
        disabled={disabled}
        onChange={(event) => onFiles(Array.from(event.target.files ?? []))}
      />
      <p className="field__hint muted" id={`${idBase}-count`}>{files.length === 0 ? 'Файлы не выбраны' : filesLabel(files.length)}</p>

      <label className="field__label upload__label-gap" htmlFor={`${idBase}-label`}>
        Название среза (необязательно)
      </label>
      <input
        id={`${idBase}-label`}
        type="text"
        className="input"
        value={label}
        placeholder={placeholder}
        maxLength={40}
        disabled={disabled}
        onChange={(event) => onLabel(event.target.value)}
        // Enter в этом поле не должен отправлять форму прогона.
        onKeyDown={(event) => {
          if (event.key === 'Enter') event.preventDefault()
        }}
      />
    </div>
  )
}
