// Выдуманные данные для моков. Цифры взяты из docs/api.md (п. 7.1), чтобы итоги
// на экране сходились со счётчиками в договоре, а не жили своей жизнью.
//
// Данные генерируются один раз при загрузке модуля и детерминированно: один и тот же
// app_id всегда даёт те же атрибуты. Иначе пагинация и сортировка показывали бы
// каждый раз разное, и проверять было бы нечего.
import type {
  AppCard,
  AppRow,
  AttributeRow,
  ChangeType,
  Dataset,
  DecisionChange,
  Reason,
  ReasonsResponse,
  Summary,
} from '../api/types'

// ─── Цифры датасета RUN-20260827-0001 ────────────────────────────────────────

const APPLICATIONS = 2002
/** Файлов на обработку: 2002 заявки × 2 среза. */
export const TOTAL_FILES = 4004

const APPROVE_TO_REJECT = 273
const REJECT_TO_APPROVE = 112
/** Заявки, где решение то же, но атрибуты различаются: 502 − 385. */
const SAME_WITH_ATTR_CHANGES = 117

export const DATASET: Dataset = {
  id: 'RUN-20260827-0001',
  applications: APPLICATIONS,
  sources: { BEFORE: 'MASTER', AFTER: 'BETA' },
  technical_fields: ['appData.request_id', 'appData.createDateTime'],
}

export const SUMMARY: Summary = {
  applications: APPLICATIONS,
  applications_changed: 502,
  applications_changed_share: 0.251,
  decision_changed: 385,
  decision_changes: {
    same: 1617,
    approve_to_reject: APPROVE_TO_REJECT,
    reject_to_approve: REJECT_TO_APPROVE,
    decision_other: 0,
  },
  attributes: { VALUE_CHANGED: 8217, ATTRIBUTE_NEW: 3835, ATTRIBUTE_LOST: 3010 },
}

// ─── Детерминированный «случай» ──────────────────────────────────────────────

/** Простой генератор: из числа-семени даёт одну и ту же последовательность. */
function createRandom(seed: number): () => number {
  let state = seed >>> 0
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let t = state
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Семя из строки: нужно, чтобы атрибуты заявки зависели только от её id. */
function seedFromString(value: string): number {
  let hash = 2166136261
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

function pick<T>(items: readonly T[], random: () => number): T {
  return items[Math.floor(random() * items.length)]!
}

// ─── Справочники значений ────────────────────────────────────────────────────

const PD_MODELS = ['ML_MICRO_LOAN_V1', 'ML_MICRO_LOAN_V2', 'ML_MICRO_LOAN_V3'] as const
const CUTOFFS = [
  'MFO_ZAIMER_2026',
  'MFO_ZAIMER_2026_LOW',
  'MFO_ZAIMER_2026_MID',
  'MFO_ZAIMER_2026_V3',
] as const
const REJECT_REASONS = ['CUTOFF', 'HARDCHECK'] as const
const PRODUCT_IDS = ['751', '5123', '15210'] as const

/** Границы бакетов для ADJUSTED_VALUE — как в примере п. 8.1. */
const BUCKET_BOUNDS = [0.3, 0.6] as const

/** Подпись бакета: в какой интервал попало значение. */
function bucketLabel(value: number): string {
  const bounds = [0, ...BUCKET_BOUNDS, 1]
  for (let i = 1; i < bounds.length; i++) {
    if (value <= bounds[i]!) {
      const left = bounds[i - 1]!
      const open = i === 1 ? '[' : '('
      return `${open}${left} – ${bounds[i]}]`
    }
  }
  return `(${BUCKET_BOUNDS[1]} – 1]`
}

// ─── Заявки (п. 7.4) ─────────────────────────────────────────────────────────

/** Раскладываем 2002 заявки по видам изменения, перетасовав индексы. */
function buildApps(): AppRow[] {
  const random = createRandom(20260827)

  const indexes = Array.from({ length: APPLICATIONS }, (_, i) => i)
  for (let i = indexes.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1))
    ;[indexes[i], indexes[j]] = [indexes[j]!, indexes[i]!]
  }

  // Кому какой вид изменения достался и есть ли различия в атрибутах.
  const plan = new Map<number, { change: DecisionChange; hasAttrChange: boolean }>()
  let cursor = 0
  for (let i = 0; i < APPROVE_TO_REJECT; i++) {
    plan.set(indexes[cursor++]!, { change: 'approve_to_reject', hasAttrChange: true })
  }
  for (let i = 0; i < REJECT_TO_APPROVE; i++) {
    plan.set(indexes[cursor++]!, { change: 'reject_to_approve', hasAttrChange: true })
  }
  for (let i = 0; i < SAME_WITH_ATTR_CHANGES; i++) {
    plan.set(indexes[cursor++]!, { change: 'same', hasAttrChange: true })
  }

  // Отдаём по порядку id: так список стабилен, а виды изменений разбросаны по нему.
  return Array.from({ length: APPLICATIONS }, (_, index) => {
    const appId = `I${32554000 + index}`
    const slot = plan.get(index) ?? { change: 'same' as DecisionChange, hasAttrChange: false }
    return buildApp(appId, slot.change, slot.hasAttrChange)
  })
}

function buildApp(appId: string, change: DecisionChange, hasAttrChange: boolean): AppRow {
  const random = createRandom(seedFromString(appId))
  const pdModel = pick(PD_MODELS, random)
  const cutoffBefore = CUTOFFS[0]
  // Порог обычно и есть то, что поменяли в BETA.
  const cutoffAfter = change === 'same' ? cutoffBefore : pick(CUTOFFS, random)
  const reason = pick(REJECT_REASONS, random)
  const sameIsReject = change === 'same' && random() < 0.4

  const base = {
    change_source: (hasAttrChange ? (Number(appId.slice(-1)) % 3 === 0 ? 'data' : 'logic') : 'none') as AppRow['change_source'],
    app_id: appId,
    pd_model_before: pdModel,
    // Модель меняется редко: чаще меняют порог, а не сам скоринг.
    pd_model_after: random() < 0.1 ? pick(PD_MODELS, random) : pdModel,
    cutoff_before: cutoffBefore,
    cutoff_after: cutoffAfter,
    attributes_changed: hasAttrChange ? 20 + Math.floor(random() * 21) : 0,
  }

  if (change === 'approve_to_reject') {
    return {
      ...base,
      decision_before: 'approve',
      decision_after: 'reject',
      decision_change: change,
      reject_reason_before: null,
      reject_reason_after: reason,
    }
  }

  if (change === 'reject_to_approve') {
    return {
      ...base,
      decision_before: 'reject',
      decision_after: 'approve',
      decision_change: change,
      reject_reason_before: reason,
      reject_reason_after: null,
    }
  }

  return {
    ...base,
    decision_before: sameIsReject ? 'reject' : 'approve',
    decision_after: sameIsReject ? 'reject' : 'approve',
    decision_change: 'same',
    reject_reason_before: sameIsReject ? reason : null,
    reject_reason_after: sameIsReject ? reason : null,
  }
}

/** Все заявки датасета, отсортированы по app_id. */
export const APPS: AppRow[] = buildApps()

const MOCK_RULE = 'DOCS_EXPIRED'

function buildSlice(app: AppRow, side: 'before' | 'after'): AppCard['before'] {
  const decision = app[`decision_${side}`]
  const reason = app[`reject_reason_${side}`]
  const cutoff = app[`cutoff_${side}`]
  const hit = reason === 'HARDCHECK'
  const productId = PRODUCT_IDS[0]
  return {
    decision,
    offers: decision === 'approve' ? [{ product_id: productId, type: 'standard' }] : [],
    products: [{
      product_id: productId,
      decision,
      reject_reason: reason,
      reject_reason_code: hit ? MOCK_RULE : reason === 'CUTOFF' ? cutoff : null,
      pd_model: app[`pd_model_${side}`],
      pd: null,
      cutoff: { name: cutoff, value: null },
      rules: [{ name: MOCK_RULE, hit }],
    }],
  }
}

export function buildAppCard(app: AppRow): AppCard {
  const before = buildSlice(app, 'before')
  const after = buildSlice(app, 'after')
  const reasons: Reason[] = []
  const hitBefore = before.products[0]?.rules[0]?.hit
  const hitAfter = after.products[0]?.rules[0]?.hit
  if (hitBefore !== hitAfter) {
    const side = hitBefore ? 'BEFORE' : 'AFTER'
    reasons.push({ text: `Стоп-фактор ${MOCK_RULE} сработал в ${side}`, source: 'rule', confidence: 'high' })
  }
  if (app.cutoff_before !== app.cutoff_after) {
    reasons.push({ text: `Порог ${app.cutoff_before} → ${app.cutoff_after}`, source: 'cutoff', confidence: 'high' })
  }
  if (reasons.length === 0) {
    reasons.push({ text: 'Причина не найдена в решающих полях', source: 'unknown', confidence: 'low' })
  }
  return { app_id: app.app_id, decision_change: app.decision_change, before, after, reasons }
}

type MockReason = Omit<ReasonsResponse['reasons'][number], 'affected' | 'share'> & { apps: string[] }
const reasonGroups = new Map<string, MockReason>()
const bySource = { logic: 0, data: 0, both: 0 }
let unexplained = 0
for (const app of APPS) {
  if (app.decision_change === 'same') continue
  if (app.change_source && app.change_source !== 'none') bySource[app.change_source] += 1
  if (app.decision_change !== 'approve_to_reject') continue

  const reason = app.reject_reason_after
  if (reason !== 'HARDCHECK' && reason !== 'CUTOFF') {
    unexplained += 1
    continue
  }
  const source = reason === 'HARDCHECK' ? 'rule' : 'cutoff'
  const rule = source === 'rule' ? MOCK_RULE : app.cutoff_after
  const ref = `mock-${rule}`
  const group = reasonGroups.get(ref) ?? {
    source, rule, app_ids_ref: ref, text: `${source === 'rule' ? 'Стоп-фактор' : 'Отсечка'} ${rule}`, apps: [],
  }
  group.apps.push(app.app_id)
  reasonGroups.set(ref, group)
}

const knownReasons = APPROVE_TO_REJECT - unexplained
export const REASONS: ReasonsResponse = {
  reasons: Array.from(reasonGroups.values(), ({ apps, ...reason }) => ({
    ...reason, affected: apps.length, share: Math.round(apps.length / knownReasons * 1000) / 1000,
  })).sort((a, b) => b.affected - a.affected),
  unexplained,
  by_source: bySource,
}

export function mockReasonApps(ref: string): string[] | undefined {
  return reasonGroups.get(ref)?.apps
}

// ─── Атрибуты одной заявки (п. 8.1) ──────────────────────────────────────────

/** Сколько строк витрины отдаём на заявку. */
const ATTRIBUTES_PER_APP = 30

/** Пути берём настоящие, из структуры ответа СПР. */
const ATTRIBUTE_PATHS: ReadonlyArray<{ path: string; key: string; numeric: boolean }> = [
  { path: 'decisionResult.product_trials[].scoring.pd.value', key: 'value', numeric: true },
  { path: 'decisionResult.product_trials[].cutOff.value', key: 'value', numeric: true },
  { path: 'decisionResult.product_trials[].cutOff.name', key: 'name', numeric: false },
  { path: 'decisionResult.product_trials[].decision', key: 'decision', numeric: false },
  { path: 'decisionResult.product_trials[].rejectReason', key: 'rejectReason', numeric: false },
  { path: 'decisionResult.product_trials[].rules[].hit', key: 'hit', numeric: false },
  { path: 'decisionResult.scoring[].value', key: 'value', numeric: true },
  { path: 'decisionResult.offers[].type', key: 'type', numeric: false },
  { path: 'decisionResult.decision', key: 'decision', numeric: false },
  { path: 'appData.scoring.pd_model', key: 'pd_model', numeric: false },
]

const TEXT_VALUES = ['APPROVE', 'REJECT', 'true', 'false', 'standard', 'manual'] as const

/**
 * Строки витрины для заявки. Типы изменений перемешаны, у ATTRIBUTE_NEW и
 * ATTRIBUTE_LOST одна из сторон пустая — ровно это и надо уметь показать на F7.
 */
export function buildAttributes(appId: string): AttributeRow[] {
  const random = createRandom(seedFromString(appId) ^ 0x5f5f)
  const rows: AttributeRow[] = []

  for (let i = 0; i < ATTRIBUTES_PER_APP; i++) {
    const template = ATTRIBUTE_PATHS[i % ATTRIBUTE_PATHS.length]!
    const changeType = pickChangeType(i, random)
    const hasArray = template.path.includes('[]')
    const arrayKey = hasArray ? pick(PRODUCT_IDS, random) : null

    const before = template.numeric
      ? (0.3 + random() * 0.6).toFixed(3)
      : pick(TEXT_VALUES, random)
    const after = template.numeric
      ? (0.3 + random() * 0.6).toFixed(3)
      : pick(TEXT_VALUES, random)

    const valueBefore = changeType === 'ATTRIBUTE_NEW' ? null : before
    const valueAfter =
      changeType === 'ATTRIBUTE_LOST' ? null : changeType === 'SAME' ? before : after

    rows.push({
      path: template.path,
      array_key: arrayKey,
      key: template.key,
      value_before: valueBefore,
      value_after: valueAfter,
      adjusted_before: adjusted(valueBefore, template.numeric),
      adjusted_after: adjusted(valueAfter, template.numeric),
      diff_flag: changeType === 'SAME' ? 0 : 1,
      change_type: changeType,
    })
  }

  return rows
}

/** Первые строки — заведомо разных типов, чтобы в таблице сразу было видно все четыре. */
function pickChangeType(index: number, random: () => number): ChangeType {
  const fixed: ChangeType[] = ['VALUE_CHANGED', 'ATTRIBUTE_NEW', 'ATTRIBUTE_LOST', 'SAME']
  if (index < fixed.length) return fixed[index]!

  const roll = random()
  if (roll < 0.55) return 'VALUE_CHANGED'
  if (roll < 0.7) return 'ATTRIBUTE_NEW'
  if (roll < 0.85) return 'ATTRIBUTE_LOST'
  return 'SAME'
}

function adjusted(value: string | null, numeric: boolean): string | null {
  if (value === null || !numeric) return null
  return bucketLabel(Number(value))
}
