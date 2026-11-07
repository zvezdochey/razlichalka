import { useCallback, useRef } from 'react'
import { getReasons } from '../../api'
import { ErrorBox, Spinner } from '../../components'
import { formatNumber } from '../../lib/format'
import { PivotGroupPanel } from './PivotGroupPanel'
import { useFactGroup } from './useFactGroup'
import { usePivotRequest } from './usePivotRequest'
import './ReasonsBlock.css'

/** Сколько причин показываем в блоке. */
const REASONS_SHOWN = 5

const PERCENT = new Intl.NumberFormat('ru-RU', { style: 'percent', maximumFractionDigits: 1 })

/** Понятные подписи стоп-факторов. Незнакомый код показываем как есть. */
const REASON_LABELS: Record<string, string> = {
  DOCS_EXPIRED: 'Просрочены документы (DOCS_EXPIRED)',
  'AGELOW@21': 'Возраст младше 21 (AGELOW@21)',
}

/** «Отсечка MODEL (порог 0.7)» → «Не прошёл порог модели MODEL (порог 0.7)». */
function reasonLabel(text: string): string {
  const known = REASON_LABELS[text.trim()]
  if (known) return known
  const cutoff = /^Отсечка\s+(.+)$/.exec(text.trim())
  return cutoff ? `Не прошёл порог модели ${cutoff[1]}` : text
}

export function ReasonsBlock({ runId, rejectedCount }: { runId: string; rejectedCount?: number }) {
  const load = useCallback((signal: AbortSignal) => getReasons(runId, { signal }), [runId])
  const { result, retry } = usePivotRequest(load)
  const { group, page, setGroup, setPage } = useFactGroup()
  const opener = useRef<HTMLButtonElement>(null)
  const closeGroup = useCallback(() => {
    const button = opener.current?.isConnected ? opener.current
      : document.querySelector<HTMLButtonElement>(`[data-reason-key="${CSS.escape(group?.key ?? '')}"]`)
    setGroup(null)
    button?.focus()
  }, [setGroup, group])

  const data = result.status === 'ready' ? result.data : null
  const sources = data?.by_source

  return (
    <div className={group ? 'reasons-layout reasons-layout--open' : 'reasons-layout'}>
      <section className="panel reasons-block" aria-labelledby="reasons-heading">
        <h2 className="overview__head" id="reasons-heading">Почему заявки стали отказами</h2>
        {result.status === 'loading' && <Spinner label="Считаем причины отказов" />}
        {result.status === 'error' && <ErrorBox message={result.message} onRetry={retry} />}
        {data && <>
          {data.reasons.length > 0 ? <>
            <p className="reasons-note">
              {data.reasons.length <= REASONS_SHOWN
                ? `${formatNumber(data.reasons.reduce((sum, r) => sum + r.affected, 0))} строк продуктов у заявок, ставших отказами (одна заявка может давать несколько причин)`
                : 'Одна заявка может давать несколько причин, поэтому считаем строки продуктов, а не заявки.'}
            </p>
            <div className="reasons-head" aria-hidden="true">
              <span>Причина</span>
              <span className="num">Строк продукта</span>
              <span />
              <span className="num">Доля</span>
            </div>
            <ul className="reasons-list">
              {data.reasons.slice(0, REASONS_SHOWN).map((reason) => {
                const key = JSON.stringify([reason.source, reason.rule])
                const expanded = group?.key === key
                return <li key={key}>
                  <button
                    type="button"
                    className="reasons-row"
                    data-reason-key={key}
                    aria-expanded={expanded}
                    onClick={(event) => {
                      opener.current = event.currentTarget
                      setGroup(expanded ? null : { key, ref: reason.app_ids_ref, label: reasonLabel(reason.text) })
                    }}
                  >
                    <span>{reasonLabel(reason.text)}</span>
                    <span className="num">{formatNumber(reason.affected)}</span>
                    <span className="reasons-track" aria-hidden="true">
                      <span style={{ inlineSize: `${reason.share * 100}%` }} />
                    </span>
                    <span className="num muted">{PERCENT.format(reason.share)}</span>
                  </button>
                </li>
              })}
            </ul>
          </> : <p className="muted">В этом прогоне нет сгруппированных причин отказа.</p>}
          <p className="muted">Без найденной причины: {formatNumber(data.unexplained)}{rejectedCount === undefined ? ' заявок' : ` из ${formatNumber(rejectedCount)} заявок, ставших отказами`}</p>
          {sources && sources.both > 0 && (
            <p className="muted">Из-за логики и данных одновременно: {formatNumber(sources.both)}</p>
          )}
        </>}
      </section>
      {group && <PivotGroupPanel
        key={group.key}
        runId={runId}
        group={group}
        page={page}
        onPageChange={setPage}
        onClose={closeGroup}
        emptyHint="Выберите другую причину на обзоре."
      />}
    </div>
  )
}
