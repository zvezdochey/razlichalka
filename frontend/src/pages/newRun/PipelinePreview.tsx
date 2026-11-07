import { Link } from 'react-router-dom'
import type { Procedure, ProcedureKind } from '../../api'
import { ErrorBox, Spinner } from '../../components'

/** Выбор процедур и проверок прогона — то, что уходит в `normalize`, `compare`, `aggregate`, `checks` (п. 4.2). */
export type PipelineChoice = {
  normalize: string
  compare: string
  aggregate: string
  checks: string[]
  /** Параметры проверок, изменённые в форме (только отличия от значений по умолчанию). */
  checkParams: Record<string, Record<string, unknown>>
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

/** Подписи известных параметров проверок организаторов; остальные показываем по имени. */
const PARAM_HINTS: Record<string, string> = {
  low_confidence_cnt: 'меньше стольких заявок — строка с низкой уверенностью',
  max_drop_rel: 'на сколько (доля) может упасть Approval Rate',
  min_share: 'минимальная доля заявок, с которой изменение считается',
}

/**
 * Параметры проверки на этот прогон (`check_params`): по умолчанию — из CHECK["params"] в коде проверки.
 * В конфигурацию уходят только отличия от умолчаний.
 */
function CheckParams({
  defaults,
  value,
  onChange,
}: {
  defaults: Record<string, unknown>
  value: Record<string, unknown>
  onChange: (params: Record<string, unknown>) => void
}) {
  const set = (key: string, raw: string) => {
    const base = defaults[key]
    let parsed: unknown = raw
    if (typeof base === 'number') {
      const number = Number(raw.replace(',', '.'))
      if (raw.trim() === '' || Number.isNaN(number)) return
      parsed = number
    }
    const next = { ...value }
    if (parsed === base) delete next[key]
    else next[key] = parsed
    onChange(next)
  }
  // app_ids_limit прогон ставит сам: в строку проверки попадают все её заявки
  const fields = Object.entries(defaults).filter(
    ([key, base]) => key !== 'app_ids_limit' && (typeof base === 'number' || typeof base === 'string'),
  )
  if (fields.length === 0) return null
  return (
    <details className="check-params">
      <summary>
        Параметры{Object.keys(value).length > 0 && <span className="chip chip--info">изменены</span>}
      </summary>
      <div className="check-params__grid">
        {fields.map(([key, base]) => (
            <label key={`${key}:${String(value[key] ?? base)}`} className="check-params__field">
              <span className="mono">{key}</span>
              <input
                className="input"
                inputMode={typeof base === 'number' ? 'decimal' : undefined}
                defaultValue={String(value[key] ?? base)}
                onBlur={(event) => set(key, event.target.value)}
              />
              {PARAM_HINTS[key] && <span className="faint">{PARAM_HINTS[key]}</span>}
            </label>
          ))}
      </div>
    </details>
  )
}

/** Откуда код процедуры: рабочая область или файл на сервере. */
const SOURCE_LABEL = { inline: 'Рабочая область', file: 'Файл .py' } as const

/** «встроенная» / «своя» и источник кода — чтобы было видно, что именно запустится. */
function ProcedureChips({ procedure }: { procedure: Procedure }) {
  return (
    <>
      {/* Источник кода («Файл .py», «встроенная») скрыт из текста, остался в подсказке. */}
      {!procedure.builtin && <span className="chip chip--info">своя</span>}
      <span className="visually-hidden">{SOURCE_LABEL[procedure.source]}</span>
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
        <h2 id="section-pipeline">Как считаем (можно не менять)</h2>
        <p className="section__note muted">
          Приведение ответов — разбирает ответ СПР на отдельные атрибуты; Сравнение — сопоставляет
          до и после; Факты (подсчёты) — считает итоги для Обзора и Сводной. Свою процедуру можно
          написать на странице <Link to="/procedures">«Процедуры»</Link>.
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
          <StepSelect
            kind="compare"
            title="Сравнение"
            description="Сводит срезы BEFORE и AFTER и помечает различия."
            procedures={procedures}
            selected={value.compare}
            onSelect={(id) => onChange({ ...value, compare: id })}
          />
          <StepSelect
            kind="aggregate"
            title="Факты (подсчёты)"
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
        {value.checks.length - missing.length === 0 && (
          // Пустой выбор допустим, но без предупреждения «Запустить» молча даст 0 FAIL.
          <p className="section__note" role="status">
            <span className="chip chip--low">Проверки не выбраны</span> Прогон посчитает различия,
            но отчёт PASS / FAIL будет пустым.
          </p>
        )}

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
              {selected.has(proc.id) && proc.params && Object.keys(proc.params).length > 0 && (
                <CheckParams
                  defaults={proc.params}
                  value={value.checkParams[proc.id] ?? {}}
                  onChange={(params) => onChange({ ...value, checkParams: { ...value.checkParams, [proc.id]: params } })}
                />
              )}
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
