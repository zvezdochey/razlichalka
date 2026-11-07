// Фейковые запуски. Статус не хранится «готовым», а считается от времени старта:
// так один и тот же запуск честно проходит pending → running → ready, и опрос
// статуса (F4/F5) есть что показывать.
import type {
  ApiError,
  RunListItem,
  RunStatus,
  Stage,
  StageName,
  Status,
} from '../api/types'
import { DATASET, TOTAL_FILES } from './data'

/** Сколько «идёт» запуск целиком. */
const RUN_DURATION_MS = 6000
/** До этой секунды запуск ещё только принят, работа не началась. */
const PENDING_MS = 800

/** Этапы с их человеческими названиями и долей времени запуска. */
const STAGE_PLAN: ReadonlyArray<{ name: StageName; title: string; share: number }> = [
  { name: 'normalize', title: 'Приведение ответов', share: 0.5 },
  { name: 'compare', title: 'Сравнение срезов', share: 0.25 },
  { name: 'aggregate', title: 'Факты counts', share: 0.15 },
  { name: 'checks', title: 'Проверки', share: 0.1 },
]

const PROCEDURE_BY_STAGE: Partial<Record<StageName, string>> = {
  normalize: 'builtin_normalize',
  aggregate: 'builtin_aggregate',
}

type MockRun = {
  id: string
  configId: string
  /** Момент старта в миллисекундах. */
  startedAt: number
  /**
   * Момент, когда запуск перестал идти не по своей воле: его остановили или он упал.
   * Заполнено — значит запуск навсегда в статусе `error`.
   */
  stoppedAt: number | null
  /** Чем именно кончился запуск. Отмена — `cancelled`, падение — `internal`. */
  stopError: ApiError | null
}

const runs = new Map<string, MockRun>()
let nextRunNumber = 1

/**
 * Готовый запуск для проверок: `getSummary('r_mock')` должен работать сразу,
 * без нажатия «Запустить». Стартовал заведомо давно, значит уже `ready`.
 */
const READY_RUN_ID = 'r_mock'
runs.set(READY_RUN_ID, {
  id: READY_RUN_ID,
  configId: 'cfg_1',
  startedAt: Date.now() - RUN_DURATION_MS * 10,
  stoppedAt: null,
  stopError: null,
})

/**
 * Упавший запуск — чтобы F4 было на чём показать «Ошибку выполнения», а не только
 * отмену. Падает на `compare`: прогресс успел дойти до середины работы.
 */
const FAILED_RUN_ID = 'r_fail'
const FAILED_RUN_STARTED_AT = Date.now() - RUN_DURATION_MS * 20
const FAILED_RUN_ERROR: ApiError = {
  code: 'internal',
  message:
    'Этап «Сравнение срезов» прерван: не удалось прочитать файл среза AFTER ' +
    '(RUN-20260827-0001/BETA/APP-0412.json)',
}
runs.set(FAILED_RUN_ID, {
  id: FAILED_RUN_ID,
  configId: 'cfg_1',
  startedAt: FAILED_RUN_STARTED_AT,
  // Чуть больше половины работы: normalize успел, compare упал на середине.
  stoppedAt: FAILED_RUN_STARTED_AT + PENDING_MS + (RUN_DURATION_MS - PENDING_MS) * 0.6,
  stopError: FAILED_RUN_ERROR,
})

export function createMockRun(configId: string): MockRun {
  const id = `r_${(nextRunNumber++).toString(16).padStart(4, '0')}`
  const run: MockRun = {
    id,
    configId,
    startedAt: Date.now(),
    stoppedAt: null,
    stopError: null,
  }
  runs.set(id, run)
  return run
}

export function findMockRun(id: string): MockRun | undefined {
  return runs.get(id)
}

const CANCELLED_ERROR: ApiError = { code: 'cancelled', message: 'Остановлено пользователем' }

/** Остановка пользователем. По коду `cancelled` фронт отличит её от падения. */
export function cancelMockRun(run: MockRun): void {
  if (run.stoppedAt !== null) return
  run.stoppedAt = Date.now()
  run.stopError = CANCELLED_ERROR
}

function elapsed(run: MockRun): number {
  const until = run.stoppedAt ?? Date.now()
  return until - run.startedAt
}

function statusOf(run: MockRun): Status {
  if (run.stoppedAt !== null) return 'error'
  const ms = elapsed(run)
  if (ms < PENDING_MS) return 'pending'
  return ms < RUN_DURATION_MS ? 'running' : 'ready'
}

export function isReady(run: MockRun): boolean {
  return statusOf(run) === 'ready'
}

/** Запуск уже закончился — успешно или с ошибкой. Такой не отменяют. */
export function isFinished(run: MockRun): boolean {
  const status = statusOf(run)
  return status === 'ready' || status === 'error'
}

/** Доля выполненной работы от 0 до 1 — из неё считаем и прогресс, и этапы. */
function progressShare(run: MockRun): number {
  const ms = elapsed(run) - PENDING_MS
  const total = RUN_DURATION_MS - PENDING_MS
  return Math.min(1, Math.max(0, ms / total))
}

function isoAt(ms: number): string {
  return new Date(ms).toISOString()
}

export function toRunStatus(run: MockRun): RunStatus {
  const status = statusOf(run)
  const share = progressShare(run)
  const done = status === 'ready' ? TOTAL_FILES : Math.floor(TOTAL_FILES * share)

  const finishedAt =
    status === 'ready'
      ? isoAt(run.startedAt + RUN_DURATION_MS)
      : run.stoppedAt !== null
        ? isoAt(run.stoppedAt)
        : null

  return {
    id: run.id,
    status,
    config_id: run.configId,
    dataset: DATASET.id,
    created_at: isoAt(run.startedAt),
    finished_at: finishedAt,
    progress: { done, total: TOTAL_FILES },
    current_stage: status === 'running' ? currentStage(share) : null,
    error: run.stopError,
  }
}

export function toRunListItem(run: MockRun): RunListItem {
  const { id, status, config_id, dataset, created_at } = toRunStatus(run)
  // Моки не хранят сохранённые конфигурации — название подставляем по id.
  return { id, status, config_id, name: `Конфигурация ${config_id}`, dataset, created_at }
}

export function listMockRuns(): RunListItem[] {
  // Свежие сверху — так же, как будет показывать F4.
  return [...runs.values()]
    .sort((a, b) => b.startedAt - a.startedAt)
    .map(toRunListItem)
}

/** Какой этап идёт при такой доле выполнения. */
function currentStage(share: number): StageName {
  let passed = 0
  for (const stage of STAGE_PLAN) {
    passed += stage.share
    if (share < passed) return stage.name
  }
  return STAGE_PLAN[STAGE_PLAN.length - 1]!.name
}

/** Журнал этапов. Статус каждого выводим из того же прогресса, что и у запуска. */
export function toStages(run: MockRun): Stage[] {
  const runStatus = statusOf(run)
  const share = progressShare(run)
  const workMs = RUN_DURATION_MS - PENDING_MS

  let startShare = 0
  return STAGE_PLAN.map((stage) => {
    const endShare = startShare + stage.share
    const stageStartMs = run.startedAt + PENDING_MS + startShare * workMs
    const stageEndMs = run.startedAt + PENDING_MS + endShare * workMs

    const status = stageStatus(runStatus, share, startShare, endShare)
    const started = status !== 'pending'
    const finished = status === 'ready'
    const procedureId = PROCEDURE_BY_STAGE[stage.name] ?? null

    const result: Stage = {
      name: stage.name,
      title: stage.title,
      status,
      started_at: started ? isoAt(stageStartMs) : null,
      finished_at: finished ? isoAt(stageEndMs) : null,
      procedure_id: procedureId,
      code_ref:
        procedureId === null
          ? null
          : {
              procedure_id: procedureId,
              source: 'file',
              path: `procedures/${stage.name}.py`,
              line: 1,
            },
      log: buildLog(stage.name, status, stageStartMs, run.stopError),
    }

    startShare = endShare
    return result
  })
}

function stageStatus(
  runStatus: Status,
  share: number,
  startShare: number,
  endShare: number,
): Status {
  if (runStatus === 'error') {
    // Остановили — упал тот этап, на котором стояли; следующие не начинались.
    if (share >= endShare) return 'ready'
    return share >= startShare ? 'error' : 'pending'
  }
  if (share >= endShare) return 'ready'
  if (share >= startShare) return 'running'
  return 'pending'
}

function buildLog(
  name: StageName,
  status: Status,
  startMs: number,
  stopError: ApiError | null,
): Stage['log'] {
  if (status === 'pending') return []
  if (status === 'error') {
    return [
      {
        at: isoAt(startMs),
        // Остановка пользователем — не авария, поэтому уровень не `error`.
        level: stopError?.code === 'cancelled' ? 'warn' : 'error',
        message: stopError?.message ?? 'Этап прерван',
      },
    ]
  }

  const half = Math.floor(TOTAL_FILES / 2)
  const log: Stage['log'] = [
    { at: isoAt(startMs), level: 'info', message: `Этап ${name} начат` },
  ]

  // Предупреждение и незнакомый уровень нужны фронту, чтобы было видно:
  // уровни раскрашены по словарю (№7), а неизвестный уровень не ломает отрисовку.
  if (name === 'normalize') {
    log.push({
      at: isoAt(startMs + 120),
      level: 'warn',
      message: '3 файла без APP_ID — пропущены',
    })
    log.push({
      at: isoAt(startMs + 180),
      level: 'trace',
      message: 'Правила массивов взяты из процедуры по умолчанию',
    })
  }

  if (status === 'ready') {
    log.push({
      at: isoAt(startMs + 500),
      level: 'info',
      message: `Обработано ${TOTAL_FILES} из ${TOTAL_FILES}`,
    })
  } else {
    log.push({
      at: isoAt(startMs + 300),
      level: 'info',
      message: `Обработано ${half} из ${TOTAL_FILES}`,
    })
  }

  return log
}
