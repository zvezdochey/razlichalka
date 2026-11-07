// По функции на каждую ручку MVP из docs/api.md. Экраны зовут только это,
// про fetch и адреса знает client.ts.
import { request } from './client'
import type {
  AppsParams,
  AppsResponse,
  AttributesParams,
  AttributesResponse,
  ChecksParams,
  ChecksResponse,
  Config,
  ConfigDetail,
  ConfigInput,
  ConfigsResponse,
  ConfigUpdate,
  Dataset,
  DatasetsResponse,
  FactAppsResponse,
  FactsParams,
  FactsResponse,
  HealthResponse,
  Procedure,
  ProcedureInput,
  ProcedureKind,
  ProceduresResponse,
  ProcedureWithCode,
  RunCancelled,
  RunCreated,
  RunListItem,
  RunStatus,
  RunsResponse,
  Stage,
  StagesResponse,
  Summary,
  ValidateInput,
  ValidateResponse,
} from './types'

/** Параметр можно отменить: при быстрой смене фильтров ответы приходят не по порядку. */
type Options = {
  signal?: AbortSignal
}

type QueryValue = string | number | boolean | string[] | undefined

/**
 * Собирает query-строку. Пропускает `undefined` и пустые массивы, массив склеивает
 * запятыми (так ждёт `decision_change`), `true` отдаёт как `1`, `false` — пропускает
 * (флаг `has_attr_change=0` в договоре не предусмотрен, его просто не присылаем).
 */
function toQuery(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams()

  for (const [key, value] of Object.entries(params)) {
    if (value === undefined) continue
    if (Array.isArray(value)) {
      if (value.length > 0) search.set(key, value.join(','))
      continue
    }
    if (typeof value === 'boolean') {
      if (value) search.set(key, '1')
      continue
    }
    if (value === '') continue
    search.set(key, String(value))
  }

  const query = search.toString()
  return query === '' ? '' : `?${query}`
}

// ─── 1. Здоровье бэка ────────────────────────────────────────────────────────

export function getHealth(options?: Options): Promise<HealthResponse> {
  return request<HealthResponse>('/health', options)
}

// ─── 2. Датасеты ─────────────────────────────────────────────────────────────

export async function getDatasets(options?: Options): Promise<Dataset[]> {
  const res = await request<DatasetsResponse>('/datasets', options)
  return res.datasets
}

// ─── 4. Конфигурации ─────────────────────────────────────────────────────────

export function createConfig(input: ConfigInput, options?: Options): Promise<Config> {
  return request<Config>('/configs', {
    ...options,
    method: 'POST',
    body: JSON.stringify(input),
  })
}

// ─── 5. Запуски ──────────────────────────────────────────────────────────────

export function createRun(configId: string, options?: Options): Promise<RunCreated> {
  return request<RunCreated>('/runs', {
    ...options,
    method: 'POST',
    body: JSON.stringify({ config_id: configId }),
  })
}

export function getRun(runId: string, options?: Options): Promise<RunStatus> {
  return request<RunStatus>(`/runs/${encodeURIComponent(runId)}`, options)
}

export async function listRuns(options?: Options): Promise<RunListItem[]> {
  const res = await request<RunsResponse>('/runs', options)
  return res.runs
}

export function cancelRun(runId: string, options?: Options): Promise<RunCancelled> {
  return request<RunCancelled>(`/runs/${encodeURIComponent(runId)}/cancel`, {
    ...options,
    method: 'POST',
  })
}

// ─── 6. Журнал этапов ────────────────────────────────────────────────────────

export async function getStages(runId: string, options?: Options): Promise<Stage[]> {
  const res = await request<StagesResponse>(`/runs/${encodeURIComponent(runId)}/stages`, options)
  return res.stages
}

// ─── 7. Витрина ──────────────────────────────────────────────────────────────

export function getSummary(runId: string, options?: Options): Promise<Summary> {
  return request<Summary>(`/runs/${encodeURIComponent(runId)}/summary`, options)
}

export function getApps(
  runId: string,
  params: AppsParams = {},
  options?: Options,
): Promise<AppsResponse> {
  const query = toQuery({
    decision_change: params.decision_change,
    has_attr_change: params.has_attr_change,
    search: params.search,
    sort: params.sort,
    page: params.page,
    size: params.size,
  })
  return request<AppsResponse>(`/runs/${encodeURIComponent(runId)}/apps${query}`, options)
}

// ─── 8. Одна заявка ──────────────────────────────────────────────────────────

export function getAttributes(
  runId: string,
  appId: string,
  params: AttributesParams = {},
  options?: Options,
): Promise<AttributesResponse> {
  const query = toQuery({ page: params.page, size: params.size })
  const path = `/runs/${encodeURIComponent(runId)}/apps/${encodeURIComponent(appId)}/attributes`
  return request<AttributesResponse>(`${path}${query}`, options)
}

// ─── 11. Отчёт ───────────────────────────────────────────────────────────────
// Это не fetch, а адреса для <a href>: отчёт открывает и скачивает сам браузер.

/** HTML-страница отчёта — открыть в новой вкладке. */
export function reportUrl(runId: string): string {
  return `/api/runs/${encodeURIComponent(runId)}/report`
}

/** То же, но с заголовком на скачивание. */
export function reportDownloadUrl(runId: string): string {
  return `/api/runs/${encodeURIComponent(runId)}/report.html`
}

// ─── 7.2–7.3. Факты и заявки группы ──────────────────────────────────────────

/** Пустой массив отключает условие, а один пустой элемент выбирает пустые ячейки. */
export function formatFactsFilter(filters: Record<string, string[]>): string {
  return Object.entries(filters)
    .filter(([, values]) => values.length > 0)
    .map(([field, values]) => `${field}:${values.join(',')}`)
    .join(';')
}

export function getFacts(
  runId: string,
  params: FactsParams,
  options?: Options,
): Promise<FactsResponse> {
  const query = toQuery({
    dims: params.dims,
    filter: params.filter && formatFactsFilter(params.filter),
    measure: params.measure,
    limit: params.limit,
  })
  return request<FactsResponse>(`/runs/${encodeURIComponent(runId)}/facts${query}`, options)
}

export function getFactApps(
  runId: string,
  ref: string,
  page: number,
  size: number,
  options?: Options,
): Promise<FactAppsResponse> {
  const query = toQuery({ page, size })
  const path = `/runs/${encodeURIComponent(runId)}/facts/${encodeURIComponent(ref)}/apps`
  return request<FactAppsResponse>(`${path}${query}`, options)
}

// ─── 10.1. Проверки ──────────────────────────────────────────────────────────

export function getChecks(
  runId: string,
  params: ChecksParams = {},
  options?: Options,
): Promise<ChecksResponse> {
  const query = toQuery({ result: params.result, page: params.page, size: params.size })
  return request<ChecksResponse>(`/runs/${encodeURIComponent(runId)}/checks${query}`, options)
}

// ─── 4. Конфигурации: список, чтение, изменение ──────────────────────────────

export async function listConfigs(options?: Options): Promise<Config[]> {
  const res = await request<ConfigsResponse>('/configs', options)
  return res.configs
}

export function getConfig(configId: string, options?: Options): Promise<ConfigDetail> {
  return request<ConfigDetail>(`/configs/${encodeURIComponent(configId)}`, options)
}

export function updateConfig(
  configId: string,
  input: ConfigUpdate,
  options?: Options,
): Promise<ConfigDetail> {
  return request<ConfigDetail>(`/configs/${encodeURIComponent(configId)}`, {
    ...options,
    method: 'PUT',
    body: JSON.stringify(input),
  })
}

// ─── 3. Процедуры и проверки ─────────────────────────────────────────────────

/** Без `kind` — все виды разом. */
export async function listProcedures(
  kind?: ProcedureKind,
  options?: Options,
): Promise<Procedure[]> {
  const res = await request<ProceduresResponse>(`/procedures${toQuery({ kind })}`, options)
  return res.procedures
}

/** Процедура вместе с кодом — по нему показываем и «код этапа» из журнала. */
export function getProcedure(id: string, options?: Options): Promise<ProcedureWithCode> {
  return request<ProcedureWithCode>(`/procedures/${encodeURIComponent(id)}`, options)
}

export function createProcedure(input: ProcedureInput, options?: Options): Promise<Procedure> {
  return request<Procedure>('/procedures', {
    ...options,
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function updateProcedure(
  id: string,
  input: ProcedureInput,
  options?: Options,
): Promise<Procedure> {
  return request<Procedure>(`/procedures/${encodeURIComponent(id)}`, {
    ...options,
    method: 'PUT',
    body: JSON.stringify(input),
  })
}

export function deleteProcedure(id: string, options?: Options): Promise<void> {
  return request<void>(`/procedures/${encodeURIComponent(id)}`, {
    ...options,
    method: 'DELETE',
  })
}

/** Проверка контракта без запуска: ошибки приходят списком «строка — текст». */
export function validateProcedure(
  input: ValidateInput,
  options?: Options,
): Promise<ValidateResponse> {
  return request<ValidateResponse>('/procedures/validate', {
    ...options,
    method: 'POST',
    body: JSON.stringify(input),
  })
}
