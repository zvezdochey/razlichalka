import { Link } from 'react-router-dom'
import type { Procedure, ProcedureKind } from '../../api'
import { ErrorBox, Spinner } from '../../components'

/** Выбор процедур и проверок прогона — то, что уходит в `normalize`, `aggregate`, `checks` (п. 4.2). */
export type PipelineChoice = {
  normalize: string
  aggregate: string
  checks: string[]
}

type PipelineSectionProps = {
  /** Все процедуры из `GET /api/procedures`; `null` — ещё грузятся. */
  procedures: Procedure[] | null
  /** Список процедур не загрузился. */
  error: string | null
  onReload: () => void
  value: PipelineChoice
  onChange: (value: PipelineChoice) => void
}

/** Откуда код процедуры: рабочая область или файл на сервере. */
const SOURCE_LABEL = { inline: 'Рабочая область', file: 'Файл .py' } as const

/** «встроенная» / «своя» и источник кода — чтобы было видно, что именно запустится. */
function ProcedureChips({ procedure }: { procedure: Procedure }) {
  return (
    <>
      <span className={procedure.builtin ? 'chip' : 'chip chip--info'}>
        {procedure.builtin ? 'встроенная' : 'своя'}
      </span>
      <span className="chip">{SOURCE_LABEL[procedure.source]}</span>
    </>
  )
}

/** Этап с выбором одной процедуры нужного вида. */
function StepSelect({
  kind,
  title,
  description,
  procedures,
  selected,
  onSelect,
}: {
  kind: ProcedureKind
  title: string
  description: string
  procedures: Procedure[]
  selected: string
  onSelect: (id: string) => void
}) {
  const options = procedures.filter((proc) => proc.kind === kind)
  const current = options.find((proc) => proc.id === selected)
  const selectId = `step-${kind}`
  return (
    <li className="steps__item">
      <div className="steps__main">
        <label className="steps__title" htmlFor={selectId}>
          {title}
        </label>
        <span className="muted">{description}</span>
      </div>
      <div className="steps__right">
        {current !== undefined && <ProcedureChips procedure={current} />}
        <select
          id={selectId}
          className="select"
          value={selected}
          onChange={(event) => onSelect(event.target.value)}
        >
          {/* Процедуру из сохранённой конфигурации могли удалить — показываем это честно. */}
          {current === undefined && <option value={selected}>{selected} (не найдена)</option>}
          {options.map((proc) => (
            <option key={proc.id} value={proc.id}>
              {proc.name}
            </option>
          ))}
        </select>
      </div>
    </li>
  )
}

/**
 * Секции «Обработка» и «Проверки»: какие процедуры приводят ответы и считают
 * факты, какие проверки прогнать. По умолчанию отмечены все встроенные
 * проверки — «просто запустить» даёт полный отчёт PASS / FAIL.
 */
export function PipelinePreview({ procedures, error, onReload, value, onChange }: PipelineSectionProps) {
  if (error !== null) {
    return (
      <section className="panel section" aria-labelledby="section-pipeline">
        <h2 id="section-pipeline">Обработка и проверки</h2>
        <ErrorBox message={`Не загрузили список процедур: ${error}`} onRetry={onReload} />
      </section>
    )
  }

  if (procedures === null) {
    return (
      <section className="panel section" aria-labelledby="section-pipeline">
        <h2 id="section-pipeline">Обработка и проверки</h2>
        <Spinner label="Загружаем процедуры" />
      </section>
    )
  }

  const checks = procedures.filter((proc) => proc.kind === 'check')
  const builtinChecks = checks.filter((proc) => proc.builtin).map((proc) => proc.id)
  const selected = new Set(value.checks)
  // Проверки из сохранённой конфигурации, которых на сервере уже нет: показываем, чтобы их можно было снять.
  const missing = value.checks.filter((id) => !checks.some((proc) => proc.id === id))

  function toggleCheck(id: string) {
    const next = selected.has(id) ? value.checks.filter((item) => item !== id) : [...value.checks, id]
    onChange({ ...value, checks: next })
  }

  return (
    <>
      <section className="panel section" aria-labelledby="section-pipeline">
        <h2 id="section-pipeline">Обработка</h2>
        <p className="section__note muted">
          Процедура этапа — встроенная или своя. Свою можно написать в рабочей области или
          подключить файлом <code>.py</code> на странице <Link to="/procedures">«Процедуры»</Link>.
        </p>

        <ul className="steps">
          <StepSelect
            kind="normalize"
            title="Приведение ответов"
            description="Разворачивает JSON ответа СПР в плоские строки витрины."
            procedures={procedures}
            selected={value.normalize}
            onSelect={(id) => onChange({ ...value, normalize: id })}
          />
          <li className="steps__item">
            <div className="steps__main">
              <span className="steps__title">Сравнение</span>
              <span className="muted">Сводит срезы BEFORE и AFTER и помечает различия.</span>
            </div>
            <div className="steps__right">
              <span className="chip">встроенное, не меняется</span>
            </div>
          </li>
          <StepSelect
            kind="aggregate"
            title="Факты"
            description="Считает агрегаты для обзора и сводной."
            procedures={procedures}
            selected={value.aggregate}
            onSelect={(id) => onChange({ ...value, aggregate: id })}
          />
        </ul>
      </section>

      <section className="panel section" aria-labelledby="section-checks">
        <h2 id="section-checks">Проверки</h2>
        <p className="section__note muted">
          Выбрано {value.checks.length - missing.length} из {checks.length}. Каждая проверка даёт строки PASS / FAIL
          во вкладке «Проверки» прогона.
        </p>

        <ul className="steps">
          {checks.map((proc) => (
            <li key={proc.id} className="steps__item">
              <label className="checks-pick">
                <input
                  type="checkbox"
                  checked={selected.has(proc.id)}
                  onChange={() => toggleCheck(proc.id)}
                />
                <span>{proc.name}</span>
              </label>
              <div className="steps__right">
                <ProcedureChips procedure={proc} />
              </div>
            </li>
          ))}
          {missing.map((id) => (
            <li key={id} className="steps__item">
              <label className="checks-pick">
                <input type="checkbox" checked onChange={() => toggleCheck(id)} />
                <span>{id}</span>
              </label>
              <div className="steps__right">
                <span className="chip chip--low">не найдена — снимите галочку</span>
              </div>
            </li>
          ))}
        </ul>

        <div className="checks-pick__actions">
          <button
            type="button"
            className="btn"
            onClick={() => onChange({ ...value, checks: builtinChecks })}
          >
            Только встроенные
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => onChange({ ...value, checks: checks.map((proc) => proc.id) })}
          >
            Отметить все
          </button>
          <button type="button" className="btn" onClick={() => onChange({ ...value, checks: [] })}>
            Снять все
          </button>
          <Link className="btn" to="/procedures?new=check">
            Добавить свою проверку
          </Link>
        </div>
      </section>
    </>
  )
}
