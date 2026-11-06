import type { StageName } from '../../api'

/**
 * Этапов ровно четыре и порядок известен заранее (docs/api.md п. 6). Рисуем все
 * четыре сразу, а не «по мере прихода»: человек должен видеть весь путь целиком,
 * в том числе то, что ещё впереди.
 */
export const STAGE_ORDER: readonly StageName[] = ['normalize', 'compare', 'aggregate', 'checks']

/** Названия на случай, если этапа в ответе ещё нет. Свои не придумываем — из договора. */
export const STAGE_TITLES: Record<StageName, string> = {
  normalize: 'Приведение ответов',
  compare: 'Сравнение срезов',
  aggregate: 'Факты counts',
  checks: 'Проверки',
}

/** Что происходит прямо сейчас — основной текст активного этапа (DESIGN п. 5). */
export const STAGE_ACTIVE_TEXT: Record<StageName, string> = {
  normalize: 'Нормализуем ответы обоих срезов…',
  compare: 'Сравниваем срезы между собой…',
  aggregate: 'Собираем факты counts…',
  checks: 'Выполняем проверки…',
}
