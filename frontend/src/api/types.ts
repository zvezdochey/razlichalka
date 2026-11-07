// Типы ответов API — один к одному с `docs/api.md` (версия 2 от 6 ноября).
// Правило: здесь только то, что есть в договоре. Не хватает поля — это расхождение,
// его пишем в «Расхождения» в PLAN.md, а не придумываем поле тут.
//
// Покрыт MVP: датасеты (2), конфигурации (4), запуски (5), этапы (6),
// итоги (7.1), список заявок (7.4), атрибуты заявки (8.1), отчёт (11).

// ─── Общие словари ───────────────────────────────────────────────────────────

/** Срез данных: прод и изменение. */
export type Source = 'BEFORE' | 'AFTER'

/** Решение по заявке. Бэк сам приводит APPROVE/REJECT из данных к этим значениям. */
export type Decision = 'approve' | 'reject' | 'other'

/** Как изменилось решение между срезами. */
export type DecisionChange =
  | 'same'
  | 'approve_to_reject'
  | 'reject_to_approve'
  | 'decision_other'

/** Как изменился атрибут. Ровно четыре значения из ТЗ. */
export type ChangeType = 'SAME' | 'VALUE_CHANGED' | 'ATTRIBUTE_NEW' | 'ATTRIBUTE_LOST'

/** Статус датасета, этапа и запуска. */
export type Status = 'pending' | 'running' | 'ready' | 'error'

/** Коды ошибок из раздела «Ошибки». */
export type ErrorCode =
  | 'bad_file'
  | 'bad_code'
  | 'no_id_column'
  | 'not_found'
  | 'not_ready'
  | 'conflict'
  | 'cancelled'
  | 'internal'

// ─── Ошибки ──────────────────────────────────────────────────────────────────

/** Тело ошибки. Лежит и в ответе с плохим кодом, и в поле `error` у запуска. */
export type ApiError = {
  code: ErrorCode
  /** Показываем пользователю как есть, без «Ошибка: » и прочих украшений. */
  message: string
}

/** Любой неуспешный ответ API завёрнут в этот объект. */
export type ApiErrorResponse = {
  error: ApiError
}

// ─── 1. Здоровье бэка ────────────────────────────────────────────────────────

export type HealthResponse = {
  status: 'ok'
}

// ─── 2. Датасеты ─────────────────────────────────────────────────────────────

export type Dataset = {
  id: string
  /** Сколько заявок в датасете (в выданном — 2002). */
  applications: number
  /** Что чем называется в данных: { BEFORE: 'MASTER', AFTER: 'BETA' }. */
  sources: Record<Source, string>
  /** Поля, которые различаются у всех заявок. F3 предзаполняет ими `ignore_paths`. */
  technical_fields: string[]
}

export type DatasetsResponse = {
  datasets: Dataset[]
}

// ─── 4. Конфигурации ─────────────────────────────────────────────────────────

/** Режим сравнения массива: по ключу, по значению или по позиции. */
export type ArrayMode = 'key' | 'value' | 'index'

/** Тело запроса на создание/изменение конфигурации (п. 4.2). */
export type ConfigInput = {
  name: string
  /** id датасета. */
  dataset: string
  /** id процедуры приведения (`kind: normalize`). */
  normalize: string
  /** id процедуры агрегации (`kind: aggregate`). */
  aggregate: string
  /** id проверок (`kind: check`). */
  checks: string[]
  /** Пути, которые не сравниваем. */
  ignore_paths: string[]
  /** Режим сравнения по пути массива. Без записи — `key`. */
  array_modes: Record<string, ArrayMode>
  /** Границы бакетов для ADJUSTED_VALUE, одни и те же для обоих срезов. */
  buckets: Record<string, number[]>
}

/** Конфигурация в списке и в ответе на создание (п. 4.1). */
export type Config = {
  id: string
  name: string
  dataset: string
  updated_at: string
}

export type ConfigsResponse = {
  configs: Config[]
}

// ─── 5. Запуски ──────────────────────────────────────────────────────────────

/** Ответ на `POST /api/runs` (202): интерфейс не ждёт расчёта, забирает id. */
export type RunCreated = {
  id: string
  status: Status
  config_id: string
}

/** Сколько файлов обработано. Всего 4004 = 2002 заявки × 2 среза. */
export type RunProgress = {
  done: number
  total: number
}

/** Статус запуска (п. 5.2). */
export type RunStatus = {
  id: string
  status: Status
  config_id: string
  dataset: string
  created_at: string
  finished_at: string | null
  progress: RunProgress
  /** Какой этап идёт сейчас. У ещё не начатого запуска этапа нет. */
  current_stage: StageName | null
  /** Заполнено только при `status: 'error'`. Отмену узнаём по `code: 'cancelled'`. */
  error: ApiError | null
}

/** Строка в списке запусков (п. 5.3). Полей меньше, чем в статусе. */
export type RunListItem = {
  id: string
  status: Status
  config_id: string
  created_at: string
}

export type RunsResponse = {
  runs: RunListItem[]
}

/** Ответ на отмену (п. 5.4). Статус становится `error` с кодом `cancelled`. */
export type RunCancelled = {
  id: string
  status: Status
  error: ApiError
}

// ─── 6. Журнал этапов ────────────────────────────────────────────────────────

/** Этапы идут строго в этом порядке. */
export type StageName = 'normalize' | 'compare' | 'aggregate' | 'checks'

/** Запись журнала. Словарь `level` в договоре не зафиксирован — см. расхождение №7. */
export type StageLogEntry = {
  at: string
  level: string
  message: string
}

/** Откуда взят код: текст в рабочей области или файл на сервере. */
export type CodeSource = 'inline' | 'file'

/** Куда перейти по клику на этап. */
export type CodeRef = {
  procedure_id: string
  source: CodeSource
  /** Только для `source: 'file'`. */
  path?: string
  line: number
}

export type Stage = {
  name: StageName
  /** Человеческое название этапа, его показываем в журнале. */
  title: string
  status: Status
  started_at: string | null
  finished_at: string | null
  procedure_id: string | null
  code_ref: CodeRef | null
  /** Последние записи журнала. Полный журнал — отдельной ручкой. */
  log: StageLogEntry[]
}

export type StagesResponse = {
  stages: Stage[]
}

// ─── 7.1. Итоги ──────────────────────────────────────────────────────────────

export type Summary = {
  applications: number
  applications_changed: number
  /** Доля от 0 до 1, не проценты. */
  applications_changed_share: number
  decision_changed: number
  decision_changes: Record<DecisionChange, number>
  /** Количество различий по типу. `SAME` здесь нет — считаем только различия. */
  attributes: {
    VALUE_CHANGED: number
    ATTRIBUTE_NEW: number
    ATTRIBUTE_LOST: number
  }
  /** Строк проверок с `FAIL`. Появляется после этапа `checks`, без проверок — `0`. */
  checks_fail?: number
}

// ─── 7.4. Список заявок с различиями ─────────────────────────────────────────

export type AppRow = {
  app_id: string
  decision_before: Decision
  decision_after: Decision
  decision_change: DecisionChange
  attributes_changed: number
  pd_model_before: string
  pd_model_after: string
  cutoff_before: string
  cutoff_after: string
  /** `null`, если в этом срезе отказа не было. */
  reject_reason_before: string | null
  reject_reason_after: string | null
}

export type AppsResponse = {
  page: number
  size: number
  total: number
  apps: AppRow[]
}

/** Параметры списка заявок. Пустые поля в query-строку не попадают. */
export type AppsParams = {
  /** Один или несколько видов изменения решения. */
  decision_change?: DecisionChange[]
  /** `true` — только заявки, где хотя бы один атрибут различается. */
  has_attr_change?: boolean
  /** Поиск по APP_ID и текстовым полям разреза. */
  search?: string
  /** Поле сортировки, минус впереди — по убыванию: `-attributes_changed`. */
  sort?: string
  /** Нумерация с 1. */
  page?: number
  /** До 500. */
  size?: number
}

// ─── 8.1. Атрибуты одной заявки ──────────────────────────────────────────────

export type AttributeRow = {
  /** Путь в JSON с маркером массива: `decisionResult.product_trials[].scoring.pd.value`. */
  path: string
  /** Ключ элемента массива (например id продукта). `null`, если массива в пути нет. */
  array_key: string | null
  key: string
  /** `null` с той стороны, где атрибута нет (ATTRIBUTE_NEW / ATTRIBUTE_LOST). */
  value_before: string | null
  value_after: string | null
  /** Бакет значения по границам из конфигурации. */
  adjusted_before: string | null
  adjusted_after: string | null
  /** 1 — значения различаются. Дублирует `change_type`, но так в витрине ТЗ. */
  diff_flag: 0 | 1
  change_type: ChangeType
}

export type AttributesResponse = {
  app_id: string
  page: number
  size: number
  total: number
  attributes: AttributeRow[]
}

/** Параметры списка атрибутов. */
export type AttributesParams = {
  page?: number
  size?: number
}

// ─── 7.2–7.3. Факты и заявки группы ──────────────────────────────────────────

export type FactValue = string | number | null
export type FactsMeasure = 'counts' | 'counts_distinct_apps'

export type FactsParams = {
  /** От одного до трёх разных полей. */
  dims: string[]
  filter?: Record<string, string[]>
  measure: FactsMeasure
  limit?: number
}

export type FactsRow = {
  [dimension: string]: FactValue
  /** Значение показателя для этой группы при любом measure. */
  counts: number
  app_ids_ref: string
}

export type FactsResponse = {
  dims: string[]
  rows: FactsRow[]
  total_groups: number
}

export type FactAppsResponse = {
  page: number
  size: number
  total: number
  apps: string[]
}

// ─── 10.1. Проверки ──────────────────────────────────────────────────────────

export type CheckResult = 'PASS' | 'FAIL'

/** Строка единой таблицы проверок. Проверка, упавшая с ошибкой, приходит строкой
 *  `FAIL` с текстом ошибки в `argument` и `faint: true`. */
export type CheckRow = {
  /** id процедуры: `builtin_…` или `p_…`. */
  check_id: string | null
  check_name: string
  source: Source | null
  argument: string | null
  /** `"CNT / TOTAL"` строкой. */
  numbers: string | null
  metric: number | null
  result: CheckResult
  /** Ссылка на список заявок (ручка 7.3). `null`, если заявок нет. */
  apps_ref: string | null
  /** Мало срабатываний — уверенности нет, строка бледная. */
  faint: boolean
}

export type ChecksResponse = {
  page: number
  size: number
  total: number
  rows: CheckRow[]
}

export type ChecksParams = {
  result?: CheckResult
  page?: number
  size?: number
}
