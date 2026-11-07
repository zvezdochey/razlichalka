// Русские подписи решений СПР — один словарь на «Заявки», карточку заявки и «почему».
// Исходный код решения (`approve`, `REJECT`) не теряем: его показываем в `title` по наведению.
import type { Decision, DecisionChange } from '../api'

/** Решение по коду из `docs/api.md` (`approve` / `reject` / `other`). */
export const DECISION_LABELS: Record<Decision, string> = {
  approve: 'Одобрено',
  reject: 'Отказ',
  other: 'Другое решение',
}

/** Как изменилось решение между срезами — подписи фильтра и чипов. */
export const DECISION_CHANGE_LABELS: Record<DecisionChange, string> = {
  approve_to_reject: 'Одобрение → отказ',
  reject_to_approve: 'Отказ → одобрение',
  same: 'Решение то же',
  decision_other: 'Другое',
}

/**
 * Подпись для сырого решения из витрины: там бывает и `approve`, и `APPROVE`.
 * Незнакомое значение возвращаем как есть — лучше показать код, чем выдумать перевод.
 */
export function decisionLabel(raw: string | null): string | null {
  if (raw === null) return null
  const key = raw.trim().toLowerCase()
  return Object.prototype.hasOwnProperty.call(DECISION_LABELS, key) ? DECISION_LABELS[key as Decision] : raw
}
