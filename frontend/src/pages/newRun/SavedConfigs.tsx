import { useEffect, useState } from 'react'
import { deleteConfig, getConfig, isAbortError, listConfigs } from '../../api'
import type { Config, ConfigDetail } from '../../api'
import { formatShortDateTime } from '../../lib/format'

type SavedConfigsProps = {
  /** Меняется после сохранения или обновления — список перечитывается. */
  refreshKey: number
  /** Конфигурация, открытая в форме сейчас. */
  activeId: string | null
  /** Конфигурацию удалили на сервере. */
  onDeleted: (id: string) => void
  /** Конфигурация выбрана: форма подставляет её поля. */
  onLoad: (config: ConfigDetail) => void
}

/** Список сохранённых конфигураций пользователя: выбрал — форма заполнилась. */
export function SavedConfigs({ refreshKey, activeId, onDeleted, onLoad }: SavedConfigsProps) {
  const [configs, setConfigs] = useState<Config[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    listConfigs({ signal: controller.signal })
      .then(setConfigs)
      .catch((e: unknown) => {
        if (!isAbortError(e)) setError(e instanceof Error ? e.message : 'Запрос не удался')
      })
    return () => controller.abort()
  }, [refreshKey])

  // Пока сохранённых нет — блок не нужен, форма и так пустая.
  if (configs.length === 0 && error === null) return null

  async function handleChange(id: string) {
    if (id === '') return
    setError(null)
    setLoading(true)
    try {
      onLoad(await getConfig(id))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Запрос не удался')
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete() {
    const config = configs.find((item) => item.id === activeId)
    if (config === undefined) return
    if (!window.confirm(`Удалить конфигурацию «${config.name}»? Запуски по ней останутся.`)) return
    setError(null)
    setLoading(true)
    try {
      await deleteConfig(config.id)
      setConfigs((list) => list.filter((item) => item.id !== config.id))
      onDeleted(config.id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Запрос не удался')
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="panel section" aria-labelledby="section-saved">
      <h2 id="section-saved">Сохранённые конфигурации</h2>
      <p className="field__hint muted new-run__lead">
        Необязательно. Выберите прошлый запуск, чтобы заполнить форму его настройками; для нового сравнения пропустите.
      </p>
      <div className="field">
        <label className="field__label" htmlFor="saved-config">
          Взять за основу
        </label>
        <select
          id="saved-config"
          className="select field__control"
          value={activeId ?? ''}
          disabled={loading}
          onChange={(event) => void handleChange(event.target.value)}
        >
          <option value="">Выберите конфигурацию</option>
          {configs.map((config) => (
            <option key={config.id} value={config.id}>
              {config.name} · {config.dataset} · обновлена {formatShortDateTime(config.updated_at)}
            </option>
          ))}
        </select>
        {activeId !== null && (
          <button
            type="button"
            className="btn"
            onClick={() => void handleDelete()}
            disabled={loading}
          >
            Удалить конфигурацию
          </button>
        )}
        {error !== null && <p className="muted">{error}</p>}
      </div>
    </section>
  )
}
