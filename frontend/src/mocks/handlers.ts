// Ручки-моки. Отвечают ровно тем, что описано в docs/api.md: ни одного лишнего поля,
// иначе на F8 (переход на настоящий бэк) экраны развалятся.
import { HttpResponse, delay, http } from 'msw'
import type {
  AppRow,
  AppsResponse,
  AttributesResponse,
  Config,
  ConfigInput,
  DecisionChange,
  ErrorCode,
} from '../api/types'
import { APPS, DATASET, SUMMARY, buildAttributes } from './data'
import {
  cancelMockRun,
  createMockRun,
  findMockRun,
  isFinished,
  isReady,
  listMockRuns,
  toRunStatus,
  toStages,
} from './runs'

/** Небольшая задержка: без неё не увидеть спиннеры и не поймать мигание таблицы. */
const RESPONSE_DELAY_MS = 150

const DEFAULT_PAGE = 1
const DEFAULT_APPS_SIZE = 50
const DEFAULT_ATTRIBUTES_SIZE = 100
const MAX_SIZE = 500

/** Ошибка в том же виде, что у бэка: `{ error: { code, message } }`. */
function error(status: number, code: ErrorCode, message: string) {
  return HttpResponse.json({ error: { code, message } }, { status })
}

const notFound = (what: string) => error(404, 'not_found', `Не нашли ${what}`)
const notReady = () =>
  error(409, 'not_ready', 'Запуск ещё не готов — результаты появятся, когда он закончится')

function readInt(params: URLSearchParams, name: string, fallback: number, max?: number): number {
  const raw = params.get(name)
  if (raw === null) return fallback
  const value = Number.parseInt(raw, 10)
  if (!Number.isFinite(value) || value < 1) return fallback
  return max === undefined ? value : Math.min(value, max)
}

/** Отрезает страницу от уже отфильтрованного списка. */
function paginate<T>(rows: T[], page: number, size: number): T[] {
  const from = (page - 1) * size
  return rows.slice(from, from + size)
}

// ─── Список заявок: фильтры, поиск, сортировка (п. 7.4) ──────────────────────

/** По договору сортировать можно по любому полю строки ответа. */
function isSortable(field: string): field is keyof AppRow {
  return APPS[0] !== undefined && Object.hasOwn(APPS[0], field)
}

function matchesSearch(app: AppRow, search: string): boolean {
  const haystack = [
    app.app_id,
    app.pd_model_before,
    app.pd_model_after,
    app.cutoff_before,
    app.cutoff_after,
    app.reject_reason_before ?? '',
    app.reject_reason_after ?? '',
  ]
  return haystack.some((value) => value.toLowerCase().includes(search))
}

function sortApps(rows: AppRow[], sort: string | null): AppRow[] {
  if (sort === null || sort === '') return rows

  const desc = sort.startsWith('-')
  const field = desc ? sort.slice(1) : sort
  if (!isSortable(field)) return rows

  const sorted = [...rows].sort((a, b) => {
    const left = a[field]
    const right = b[field]
    if (typeof left === 'number' && typeof right === 'number') return left - right
    return String(left).localeCompare(String(right))
  })
  return desc ? sorted.reverse() : sorted
}

function filterApps(params: URLSearchParams): AppRow[] {
  const rawChanges = params.get('decision_change')
  const changes = rawChanges === null ? null : (rawChanges.split(',') as DecisionChange[])
  const onlyAttrChange = params.get('has_attr_change') === '1'
  const sources = params.get('change_source')?.split(',')
  const search = params.get('search')?.trim().toLowerCase() ?? ''

  const filtered = APPS.filter((app) => {
    if (sources && !sources.includes(app.change_source)) return false
    if (changes !== null && !changes.includes(app.decision_change)) return false
    if (onlyAttrChange && app.attributes_changed === 0) return false
    if (search !== '' && !matchesSearch(app, search)) return false
    return true
  })

  return sortApps(filtered, params.get('sort'))
}

// ─── Ручки ───────────────────────────────────────────────────────────────────

export const handlers = [
  // 1. Здоровье бэка
  http.get('/api/health', async () => {
    await delay(RESPONSE_DELAY_MS)
    return HttpResponse.json({ status: 'ok' })
  }),

  // 2.1. Список датасетов
  http.get('/api/datasets', async () => {
    await delay(RESPONSE_DELAY_MS)
    return HttpResponse.json({ datasets: [DATASET] })
  }),

  // 4.2. Создать конфигурацию
  http.post('/api/configs', async ({ request }) => {
    await delay(RESPONSE_DELAY_MS)
    const body = (await request.json()) as Partial<ConfigInput>
    if (typeof body?.dataset !== 'string' || body.dataset !== DATASET.id) {
      return notFound('такой датасет')
    }
    const config: Config = {
      id: `cfg_${Date.now().toString(16)}`,
      name: body.name ?? 'Без названия',
      dataset: body.dataset,
      updated_at: new Date().toISOString(),
    }
    return HttpResponse.json(config, { status: 201 })
  }),

  // 5.1. Запустить прогон
  http.post('/api/runs', async ({ request }) => {
    await delay(RESPONSE_DELAY_MS)
    const body = (await request.json()) as { config_id?: string }
    if (typeof body?.config_id !== 'string' || body.config_id === '') {
      return error(400, 'bad_file', 'Не передана конфигурация запуска')
    }
    const run = createMockRun(body.config_id)
    return HttpResponse.json(
      { id: run.id, status: 'pending', config_id: run.configId },
      { status: 202 },
    )
  }),

  // 5.3. Список запусков пользователя
  http.get('/api/runs', async () => {
    await delay(RESPONSE_DELAY_MS)
    return HttpResponse.json({ runs: listMockRuns() })
  }),

  // 5.4. Остановить запуск
  http.post('/api/runs/:id/cancel', async ({ params }) => {
    await delay(RESPONSE_DELAY_MS)
    const run = findMockRun(String(params.id))
    if (run === undefined) return notFound('такой запуск')
    // Завершённый запуск отменить нельзя, иначе итоги пропадут с 409 not_ready
    // и F4 будет отлаживать поведение, которого на настоящем бэке не будет.
    if (isFinished(run)) {
      return error(409, 'conflict', 'Запуск уже завершён — отменять нечего')
    }
    cancelMockRun(run)
    const status = toRunStatus(run)
    return HttpResponse.json({ id: status.id, status: status.status, error: status.error })
  }),

  // 6. Журнал этапов
  http.get('/api/runs/:id/stages', async ({ params }) => {
    await delay(RESPONSE_DELAY_MS)
    const run = findMockRun(String(params.id))
    if (run === undefined) return notFound('такой запуск')
    return HttpResponse.json({ stages: toStages(run) })
  }),

  // 7.1. Итоги
  http.get('/api/runs/:id/summary', async ({ params }) => {
    await delay(RESPONSE_DELAY_MS)
    const run = findMockRun(String(params.id))
    if (run === undefined) return notFound('такой запуск')
    if (!isReady(run)) return notReady()
    return HttpResponse.json(SUMMARY)
  }),

  // 8.1. Атрибуты заявки
  http.get('/api/runs/:id/apps/:appId/attributes', async ({ params, request }) => {
    await delay(RESPONSE_DELAY_MS)
    const run = findMockRun(String(params.id))
    if (run === undefined) return notFound('такой запуск')
    if (!isReady(run)) return notReady()

    const appId = String(params.appId)
    if (!APPS.some((app) => app.app_id === appId)) return notFound('такую заявку')

    const url = new URL(request.url)
    const page = readInt(url.searchParams, 'page', DEFAULT_PAGE)
    const size = readInt(url.searchParams, 'size', DEFAULT_ATTRIBUTES_SIZE, MAX_SIZE)
    const search = url.searchParams.get('search')?.toLowerCase() ?? ''
    const rows = buildAttributes(appId).filter((row) =>
      (url.searchParams.get('only_diff') !== '1' || row.diff_flag === 1) && row.path.toLowerCase().includes(search))

    const response: AttributesResponse = {
      app_id: appId,
      page,
      size,
      total: rows.length,
      attributes: paginate(rows, page, size),
    }
    return HttpResponse.json(response)
  }),

  // 7.4. Список заявок с различиями
  http.get('/api/runs/:id/apps', async ({ params, request }) => {
    await delay(RESPONSE_DELAY_MS)
    const run = findMockRun(String(params.id))
    if (run === undefined) return notFound('такой запуск')
    if (!isReady(run)) return notReady()

    const url = new URL(request.url)
    const sort = url.searchParams.get('sort') ?? ''
    if (sort && !isSortable(sort.replace(/^-/, ''))) return error(400, 'bad_file', `Неизвестное поле сортировки: ${sort}`)
    const page = readInt(url.searchParams, 'page', DEFAULT_PAGE)
    const size = readInt(url.searchParams, 'size', DEFAULT_APPS_SIZE, MAX_SIZE)
    const rows = filterApps(url.searchParams)

    const response: AppsResponse = {
      page,
      size,
      total: rows.length,
      apps: paginate(rows, page, size),
    }
    return HttpResponse.json(response)
  }),

  // 5.2. Статус запуска
  http.get('/api/runs/:id', async ({ params }) => {
    await delay(RESPONSE_DELAY_MS)
    const run = findMockRun(String(params.id))
    if (run === undefined) return notFound('такой запуск')
    return HttpResponse.json(toRunStatus(run))
  }),

  // 11. Отчёт. Настоящий HTML делает бэк; мок отдаёт заглушку, чтобы ссылка не вела в пустоту.
  http.get('/api/runs/:id/report', async ({ params }) => {
    await delay(RESPONSE_DELAY_MS)
    const run = findMockRun(String(params.id))
    if (run === undefined) return notFound('такой запуск')
    if (!isReady(run)) return notReady()
    return HttpResponse.html(
      `<!doctype html><meta charset="utf-8"><title>Отчёт ${run.id}</title>` +
        `<p>Это мок отчёта. Настоящий HTML соберёт бэк.</p>`,
    )
  }),
]
