import type { ReactNode } from 'react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import type { DecisionChange, Summary } from '../../api'
import { getSummary, isAbortError } from '../../api'
import { ErrorBox, Spinner } from '../../components'
import { DASH, formatNumber } from '../../lib/format'
import { NotReadyNotice } from './NotReadyNotice'
import './OverviewTab.css'
import { useRunContext } from './runContext'

/**
 * Обзор результата — главный экран защиты (сценарий 1 задания: «стоит ли бояться»).
 * Поэтому сверху не четыре плитки с данными, а одна фраза-ответ, и только под ней числа
 * (отклонение от текста задачи согласовано, PLAN п. 2, F5 п. 1).
 */
export function OverviewTab() {
  const { runId, run } = useRunContext()
  if (run === null || run.status !== 'ready') return <NotReadyNotice run={run} />

  return <OverviewBody runId={runId} />
}

// ─── Загрузка ────────────────────────────────────────────────────────────────

function OverviewBody({ runId }: { runId: string }) {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reloadToken, setReloadToken] = useState(0)

  const retry = useCallback(() => setReloadToken((token) => token + 1), [])

  useEffect(() => {
    const controller = new AbortController()

    const load = async () => {
      try {
        const next = await getSummary(runId, { signal: controller.signal })
        setSummary(next)
        setError(null)
      } catch (e) {
        if (isAbortError(e)) return
        setError(e instanceof Error ? e.message : 'Не удалось получить итоги прогона')
      }
    }

    // eslint-disable-next-line react/set-state-in-effect -- загрузка данных эффектом и есть синхронизация с внешней системой
    void load()
    return () => controller.abort()
  }, [runId, reloadToken])

  if (error !== null) {
    return (
      <div className="panel">
        <ErrorBox message={error} onRetry={retry} />
      </div>
    )
  }

  if (summary === null) {
    return (
      <div className="panel">
        <Spinner label="Считаем итоги прогона" />
      </div>
    )
  }

  return (
    <div className="overview">
      <Verdict summary={summary} />
      <div className="overview__columns">
        <DecisionTransitions summary={summary} />
        <AttributeBars summary={summary} />
      </div>
      {/* Ниже встанут «Что ломает решение» (I4) и «Логика или входные данные» (E10) — чужие блоки. */}
    </div>
  )
}

// ─── Доли и подписи ──────────────────────────────────────────────────────────

const PERCENT_PRECISION = 10

/** «25,1 %» из доли 0…1 — так её отдаёт договор (api.md п. 7.1). */
function formatPercent(share: number): string {
  const percent = Math.round(share * 100 * PERCENT_PRECISION) / PERCENT_PRECISION
  return `${formatNumber(percent)} %`
}

/**
 * Доля от объёма прогона для величин, которых в ответе нет (переходы, «решение то же»).
 * Там, где бэк уже посчитал долю сам, берём его число, а не своё.
 */
function formatShare(value: number, total: number): string {
  if (total <= 0) return DASH
  return formatPercent(value / total)
}

/**
 * «Любая смена решения» — перечисление значений словаря через запятую (api.md п. 7.4).
 * Своего значения `any` в договоре нет, выдумывать его нельзя.
 */
const ANY_DECISION_CHANGE = 'approve_to_reject,reject_to_approve,decision_other'

/** Ссылка во вкладку «Заявки» с готовым фильтром: её читает F6 прямо из URL. */
function appsLink(search: string) {
  return { pathname: '../apps', search }
}

// ─── Фраза-ответ и лента чисел ───────────────────────────────────────────────

function Verdict({ summary }: { summary: Summary }) {
  const { applications, applications_changed, applications_changed_share, decision_changed } =
    summary

  return (
    <section className="panel verdict" aria-labelledby="verdict-head">
      <p className="verdict__text" id="verdict-head">
        {applications === 0 ? (
          'В прогоне нет заявок с парой «до» и «после» — сравнивать нечего.'
        ) : applications_changed === applications ? (
          // На настоящем датасете различия пока у всех заявок (служебные поля), и фраза
          // «из 2 002 изменились 2 002» читается как ошибка. Говорим то же самое прямо.
          <>
            Различия нашлись у всех <Big value={applications} /> заявок.
            <br />У <Big value={decision_changed} /> сменилось решение.
          </>
        ) : (
          <>
            Из <Big value={applications} /> заявок изменились <Big value={applications_changed} />.
            <br />У <Big value={decision_changed} /> сменилось решение.
          </>
        )}
      </p>

      <dl className="strip">
        <StripItem label="Заявок в прогоне" hint="уникальные заявки">
          <span className="num">{formatNumber(applications)}</span>
        </StripItem>

        <StripItem
          label="С различиями"
          hint={`доля от прогона — ${formatPercent(applications_changed_share)}`}
        >
          <span className="num">{formatNumber(applications_changed)}</span>
        </StripItem>

        <StripItem label="Сменили решение" hint="любая смена решения">
          <Link
            className="strip__link num"
            to={appsLink(`?decision_change=${ANY_DECISION_CHANGE}`)}
          >
            {formatNumber(decision_changed)}
          </Link>
        </StripItem>

        <StripItem label="Проверки с FAIL" hint="проверки подключатся позже">
          <span className="num faint">{DASH}</span>
        </StripItem>
      </dl>
    </section>
  )
}

function Big({ value }: { value: number }) {
  return <span className="verdict__num num">{formatNumber(value)}</span>
}

type StripItemProps = {
  label: string
  hint: string
  children: ReactNode
}

function StripItem({ label, hint, children }: StripItemProps) {
  return (
    <div className="strip__item">
      <dt className="strip__label">{label}</dt>
      <dd className="strip__value">{children}</dd>
      <dd className="strip__hint">{hint}</dd>
    </div>
  )
}

// ─── Переходы решений ────────────────────────────────────────────────────────

/**
 * Переходы нейтральны по цвету: `approve → reject` может быть ровно тем эффектом,
 * ради которого правку и делали (PLAN п. 1). Акцент — только на величине числа.
 */
const TRANSITIONS: { key: DecisionChange; before: string; after: string }[] = [
  { key: 'approve_to_reject', before: 'одобрено', after: 'отказано' },
  { key: 'reject_to_approve', before: 'отказано', after: 'одобрено' },
  { key: 'decision_other', before: 'любое', after: 'другое решение' },
]

function DecisionTransitions({ summary }: { summary: Summary }) {
  const { applications, applications_changed, decision_changed, decision_changes } = summary

  // Не `decision_changes.same`: туда входят и заявки вообще без различий.
  const changedSameDecision = applications_changed - decision_changed
  const sameFormula = `${formatNumber(applications_changed)} с различиями − ${formatNumber(decision_changed)} со сменой решения`

  return (
    <section className="panel transitions" aria-labelledby="transitions-head">
      <h2 className="overview__head" id="transitions-head">
        Куда сместились решения
      </h2>

      <table className="table transitions__table">
        <thead>
          <tr>
            <th scope="col">Было и стало</th>
            <th scope="col" className="num">
              Заявок
            </th>
            <th scope="col" className="num">
              Доля прогона
            </th>
          </tr>
        </thead>
        <tbody>
          {TRANSITIONS.map(({ key, before, after }) => {
            const value = decision_changes[key]
            return (
              <tr key={key}>
                <th scope="row">
                  {value > 0 ? (
                    <Link
                      className="transitions__pair"
                      to={appsLink(`?decision_change=${key}`)}
                      title="Открыть эти заявки"
                    >
                      <span>{before}</span>
                      <span className="visually-hidden"> сменилось на </span>
                      <span className="axis">{after}</span>
                    </Link>
                  ) : (
                    <span className="transitions__pair muted">
                      <span>{before}</span>
                      <span className="visually-hidden"> сменилось на </span>
                      <span className="axis">{after}</span>
                    </span>
                  )}
                </th>
                <td className="num">{formatNumber(value)}</td>
                <td className="num muted">{formatShare(value, applications)}</td>
              </tr>
            )
          })}

          <tr className="transitions__total">
            <th scope="row">Сменили решение, всего</th>
            <td className="num">{formatNumber(decision_changed)}</td>
            <td className="num muted">{formatShare(decision_changed, applications)}</td>
          </tr>

          {changedSameDecision > 0 && (
            <tr className="transitions__quiet">
              <th scope="row">
                <Link
                  to={appsLink('?decision_change=same&has_attr_change=1')}
                  title={`Считаем так: ${sameFormula}`}
                >
                  Различия есть, решение то же
                </Link>
              </th>
              <td className="num">{formatNumber(changedSameDecision)}</td>
              <td className="num muted">{formatShare(changedSameDecision, applications)}</td>
            </tr>
          )}
        </tbody>
      </table>

      {applications_changed === 0 && (
        <p className="transitions__note muted">
          Различий нет: срезы «до» и «после» совпали на всех заявках.
        </p>
      )}
    </section>
  )
}

// ─── Полосы по атрибутам ─────────────────────────────────────────────────────

/** Тип различия различается текстом и формой полосы, не только цветом (PLAN п. 1). */
const ATTRIBUTE_KINDS: {
  key: keyof Summary['attributes']
  title: string
  shape: string
}[] = [
  { key: 'VALUE_CHANGED', title: 'Значение изменилось', shape: 'solid' },
  { key: 'ATTRIBUTE_NEW', title: 'Атрибут появился', shape: 'hatched' },
  { key: 'ATTRIBUTE_LOST', title: 'Атрибут исчез', shape: 'hollow' },
]

function AttributeBars({ summary }: { summary: Summary }) {
  const { attributes } = summary
  const peak = Math.max(...ATTRIBUTE_KINDS.map(({ key }) => attributes[key]), 1)

  return (
    <section className="panel attrs" aria-labelledby="attrs-head">
      <h2 className="overview__head" id="attrs-head">
        Что изменилось в атрибутах
      </h2>

      <ul className="attrs__list">
        {ATTRIBUTE_KINDS.map(({ key, title, shape }) => {
          const value = attributes[key]
          return (
            <li className="attrs__row" key={key}>
              <span className="attrs__title">{title}</span>
              <span className="attrs__value num">{formatNumber(value)}</span>
              <span className="attrs__track">
                <span
                  className={`attrs__bar attrs__bar--${shape}`}
                  style={{ inlineSize: `${(value / peak) * 100}%` }}
                />
              </span>
            </li>
          )
        })}
      </ul>

      <p className="attrs__note muted">
        Строки атрибутов, не уникальные заявки: одна заявка входит во многие строки.
      </p>
    </section>
  )
}
