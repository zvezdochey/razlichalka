import type { ProcedureKind } from '../../api'
import { STAGE_TITLES } from '../run/stages'

/** Подписи видов процедур. Для этапов — те же названия, что в журнале. */
export const KIND_TITLES: Record<ProcedureKind, string> = {
  check: 'Проверки',
  normalize: STAGE_TITLES.normalize,
  aggregate: STAGE_TITLES.aggregate,
}

/** Вид одной процедуры — в шапке редактора. */
export const KIND_NAMES: Record<ProcedureKind, string> = {
  check: 'Проверка',
  normalize: STAGE_TITLES.normalize,
  aggregate: STAGE_TITLES.aggregate,
}

/** Порядок групп в списке: проверки пишут чаще всего — они первые. */
export const KIND_ORDER: readonly ProcedureKind[] = ['check', 'normalize', 'aggregate']

/**
 * Шаблон новой проверки по контракту из `checks/README.md`: объект `CHECK` и
 * `run(mart, params) -> list[dict]`. Код рабочий как есть — его можно сразу
 * проверить, сохранить и запустить, а потом переписать под свою задачу.
 * `id` в CHECK делаем случайным хвостом, чтобы две новые проверки не совпали.
 */
export function newCheckTemplate(): string {
  const suffix = Math.random().toString(36).slice(2, 6)
  return `# -*- coding: utf-8 -*-
"""Новая проверка. Опишите здесь, что она ищет и когда это плохо."""

# Параметры по умолчанию. Их видно в CHECK["params"], менять можно здесь.
DEFAULTS = {"low_confidence_cnt": 5, "app_ids_limit": 20}


def run(mart, params=None):
    p = {**DEFAULTS, **(params or {})}
    total = mart.total_apps()

    # Пример: заявки, у которых в AFTER пропал хотя бы один атрибут.
    apps = mart.app_ids(change_type="ATTRIBUTE_LOST")
    cnt = len(apps)

    # Одна строка результата. Проверка может вернуть и несколько — по строке на предмет.
    return [{
        "LABEL": CHECK["label"],
        "SOURCE": "AFTER",                 # сравнение срезов пишем в AFTER
        "ARGUMENT": "пропавшие атрибуты",  # что проверяли: продукт, атрибут, стоп-фактор
        "CNT": cnt,                        # сколько заявок попало
        "TOTAL": total,                    # от чего считали
        "METRIC": round(cnt / total, 4) if total else 0.0,
        "APP_IDS": apps[:p["app_ids_limit"]],
        "RESULT": "FAIL" if cnt > 0 else "PASS",
        # Мало срабатываний — сигнал есть, уверенности нет: строка будет бледной.
        "CONFIDENCE": "LOW" if 0 < cnt < p["low_confidence_cnt"] else "HIGH",
    }]


CHECK = {
    "id": "my_check_${suffix}",
    "label": "Моя проверка",
    "params": DEFAULTS,
    "entrypoint": run,
}
`
}

/**
 * Делает копию проверки отличимой от оригинала: дописывает пометку к `id` и `label`
 * внутри `CHECK`. Бэк сопоставляет строки результата с проверкой по `LABEL`, поэтому
 * без этого оригинал и копия в одной конфигурации слились бы под одним названием.
 * Правим только последний `CHECK = {...}`; если его нет, код остаётся как был.
 */
export function markCheckAsCopy(code: string): string {
  const start = code.lastIndexOf('CHECK')
  if (start === -1) return code
  const head = code.slice(0, start)
  const tail = code
    .slice(start)
    .replace(/(["']id["']\s*:\s*["'])([^"']+)(["'])/, '$1$2_copy$3')
    .replace(/(["']label["']\s*:\s*["'])([^"']+)(["'])/, '$1$2 (копия)$3')
  return head + tail
}
