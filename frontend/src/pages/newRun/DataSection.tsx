import type { Dataset } from '../../api'
import { IgnorePathsField } from './IgnorePathsField'

type DataSectionProps = {
  name: string
  onNameChange: (name: string) => void
  datasets: Dataset[]
  selectedId: string
  onSelect: (datasetId: string) => void
  ignorePaths: string[]
  onIgnorePathsChange: (paths: string[]) => void
}

/** Секция «Данные» — единственная, которая в MVP работает. */
export function DataSection({
  name,
  onNameChange,
  datasets,
  selectedId,
  onSelect,
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
        <select
          id="dataset"
          className="select field__control"
          value={selectedId}
          onChange={(event) => onSelect(event.target.value)}
        >
          <option value="">Выберите датасет</option>
          {datasets.map((dataset) => (
            <option key={dataset.id} value={dataset.id}>
              {dataset.id}
            </option>
          ))}
        </select>
        {selectedId === '' && (
          <p className="field__hint muted">Без датасета прогон не запустить.</p>
        )}
      </div>

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
