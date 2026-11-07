import type { Dataset, UploadResponse } from '../../api'
import { uploadTimeFromId } from '../../lib/format'
import { IgnorePathsField } from './IgnorePathsField'
import { UploadDataset } from './UploadDataset'

/** «1 заявка», «2 заявки», «5 заявок» — склонение по последним цифрам числа. */
function applicationsWord(count: number): string {
  const lastTwo = count % 100
  const last = count % 10
  if (lastTwo >= 11 && lastTwo <= 14) return 'заявок'
  if (last === 1) return 'заявка'
  if (last >= 2 && last <= 4) return 'заявки'
  return 'заявок'
}

type DataSectionProps = {
  name: string
  onNameChange: (name: string) => void
  datasets: Dataset[]
  selectedId: string
  onSelect: (datasetId: string) => void
  onUploaded: (result: UploadResponse) => void
  onReload: () => void
  ignorePaths: string[]
  onIgnorePathsChange: (paths: string[]) => void
}

/** Подпись датасета: загруженные — по времени из id, остальные — по id как есть. */
function datasetLabel(dataset: Dataset): string {
  const time = uploadTimeFromId(dataset.id)
  const count = `${dataset.applications.toLocaleString('ru-RU')} ${applicationsWord(dataset.applications)}`
  const sources = `${dataset.sources.BEFORE} → ${dataset.sources.AFTER}`
  return time === null
    ? `${dataset.id} — ${count}, ${sources}`
    : `Загруженный ${time} (время сервера) — ${count}, ${sources}`
}

/** Секция «Данные» — единственная, которая в MVP работает. */
export function DataSection({
  name,
  onNameChange,
  datasets,
  selectedId,
  onSelect,
  onUploaded,
  onReload,
  ignorePaths,
  onIgnorePathsChange,
}: DataSectionProps) {
  const selected = datasets.find((dataset) => dataset.id === selectedId)

  return (
    <section className="panel section" aria-labelledby="section-data">
      <h2 id="section-data">Данные</h2>

      <div className="field">
        <label className="field__label" htmlFor="config-name">
          Название конфигурации
        </label>
        <input
          id="config-name"
          type="text"
          className="input field__control"
          value={name}
          onChange={(event) => onNameChange(event.target.value)}
        />
      </div>

      <div className="field">
        <label className="field__label" htmlFor="dataset">
          Датасет
        </label>
        {/* Список и кнопка — в одной строке с зазором; на узком экране кнопка уходит вниз. */}
        <div className="field__row">
          <select
            id="dataset"
            className="select field__control"
            value={selectedId}
            onChange={(event) => onSelect(event.target.value)}
          >
            <option value="">Выберите датасет</option>
            {datasets.map((dataset) => (
              <option key={dataset.id} value={dataset.id}>
                {datasetLabel(dataset)}
              </option>
            ))}
          </select>
          <button type="button" className="btn field__reload" onClick={onReload}>
            Обновить список
          </button>
        </div>
        {selectedId === '' && (
          <p className="field__hint muted">
            {datasets.length === 0
              ? 'На сервере датасетов нет — загрузите свои данные ниже.'
              : 'Без датасета прогон не запустить.'}
          </p>
        )}
      </div>

      <UploadDataset onUploaded={onUploaded} />

      {selected && <DatasetFacts dataset={selected} />}

      {selected && <IgnorePathsField paths={ignorePaths} onChange={onIgnorePathsChange} />}
    </section>
  )
}

/** Что известно про выбранный датасет: объём, срезы и технические поля. */
function DatasetFacts({ dataset }: { dataset: Dataset }) {
  return (
    <dl className="facts">
      <div className="facts__item">
        <dt className="facts__label">Заявок</dt>
        <dd className="facts__value num">{dataset.applications.toLocaleString('ru-RU')}</dd>
      </div>
      <div className="facts__item">
        <dt className="facts__label">Срезы</dt>
        <dd className="facts__value">
          <span>
            BEFORE <span className="muted">({dataset.sources.BEFORE})</span>
          </span>
          <span className="axis">
            AFTER <span className="muted">({dataset.sources.AFTER})</span>
          </span>
        </dd>
      </div>
      <div className="facts__item">
        <dt className="facts__label">Технические поля</dt>
        <dd className="facts__value mono facts__value--paths">
          {dataset.technical_fields.length === 0
            ? '—'
            : dataset.technical_fields.join(', ')}
        </dd>
      </div>
    </dl>
  )
}
