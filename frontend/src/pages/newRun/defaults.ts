// То, что в MVP не выбирают руками: процедуры встроенные, проверок нет.
// Значения строго по `docs/api.md` п. 4.2 — своих полей не придумываем.
import type { ArrayMode } from '../../api'

/** id встроенной процедуры приведения ответов (`kind: normalize`). */
export const BUILTIN_NORMALIZE = 'builtin_normalize'

/** id встроенной процедуры подготовки фактов (`kind: aggregate`). */
export const BUILTIN_AGGREGATE = 'builtin_aggregate'

/**
 * Единственный режим массива, который договор задаёт явно: у вектора модели
 * значима позиция, поэтому `index`, а не ключ (п. 4.2). Остальные массивы
 * сравниваются по ключу — это значение по умолчанию, присылать его не надо.
 */
export const DEFAULT_ARRAY_MODES: Record<string, ArrayMode> = {
  'decisionResult.scoring[].value': 'index',
}

/** Границы бакетов в MVP не настраиваем: отправляем пусто, бэк берёт свои. */
export const DEFAULT_BUCKETS: Record<string, number[]> = {}

/** Название по умолчанию — «Прогон на 07.11». */
export function defaultConfigName(now: Date = new Date()): string {
  const day = String(now.getDate()).padStart(2, '0')
  const month = String(now.getMonth() + 1).padStart(2, '0')
  return `Прогон на ${day}.${month}`
}
