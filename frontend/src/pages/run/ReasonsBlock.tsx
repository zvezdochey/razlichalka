import { useCallback, useRef } from 'react'
import { getReasons } from '../../api'
import { ErrorBox, Spinner } from '../../components'
import { formatNumber } from '../../lib/format'
import { PivotGroupPanel } from './PivotGroupPanel'
import { useFactGroup } from './useFactGroup'
import { usePivotRequest } from './usePivotRequest'
import './ReasonsBlock.css'

const PERCENT = new Intl.NumberFormat('ru-RU', { style: 'percent', maximumFractionDigits: 1 })

export function ReasonsBlock({ runId }: { runId: string }) {
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
        <h2 className="overview__head" id="reasons-heading">Что ломает решение</h2>
        {result.status === 'loading' && <Spinner label="Считаем причины отказов" />}
        {result.status === 'error' && <ErrorBox message={result.message} onRetry={retry} />}
        {data && <>
          {data.reasons.length > 0 ? <>
            <p className="muted">Число строк продуктов и доля среди причин отказа.</p>
            <ul className="reasons-list">
              {data.reasons.slice(0, 5).map((reason) => {
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
                      setGroup(expanded ? null : { key, ref: reason.app_ids_ref, label: reason.text })
                    }}
                  >
                    <span>{reason.text}</span>
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
          <p className="muted">Без найденной причины: {formatNumber(data.unexplained)} заявок</p>
          {sources && (
            <p className="muted">
              Из-за логики {formatNumber(sources.logic)} · из-за данных {formatNumber(sources.data)}
              {' · из-за логики и данных '}{formatNumber(sources.both)}
            </p>
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
