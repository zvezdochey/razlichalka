import { useCallback, useEffect, useState } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import { getApps } from '../../api'
import type { ChangeSource, DecisionChange } from '../../api'
import { EmptyState, ErrorBox } from '../../components'
import { DASH, formatNumber } from '../../lib/format'
import { NotReadyNotice } from './NotReadyNotice'
import { useRunContext } from './runContext'
import { usePivotRequest } from './usePivotRequest'
import './AppsTab.css'

const DECISIONS: Record<DecisionChange, string> = {
  approve_to_reject: 'Одобрено → отказ', reject_to_approve: 'Отказ → одобрено',
  same: 'Решение то же', decision_other: 'Другое',
}
const SOURCES: Record<ChangeSource, string> = {
  logic: 'Логика', data: 'Данные', both: 'Логика и данные', none: 'Без различий',
}
const FILTER_KEYS = ['decision_change', 'change_source', 'has_attr_change', 'search']

/** Пара значений: цвет отмечает только факт различия, а не его оценку. */
function Pair({ before, after, badge = false }: { before: string | null; after: string | null; badge?: boolean }) {
  return <div className="apps-pair">
    <span className={badge ? 'chip' : undefined} title={before ?? DASH}>{before ?? DASH}</span>
    <span className="axis"><span className={badge ? 'chip' : undefined} title={after ?? DASH}>{after ?? DASH}</span></span>
  </div>
}

/** Отдельный компонент сбрасывает незавершённый ввод при любой навигации. */
function Search({ applied, navigationKey, onApply }: { applied: string; navigationKey: string; onApply: (value: string) => void }) {
  const [draft, setDraft] = useState({ navigationKey, value: applied })
  if (draft.navigationKey !== navigationKey) setDraft({ navigationKey, value: applied })
  const value = draft.navigationKey === navigationKey ? draft.value : applied
  useEffect(() => {
    if (value === applied) return
    const timer = window.setTimeout(() => onApply(value), 300)
    return () => window.clearTimeout(timer)
  }, [value, applied, onApply])
  return <label className="apps-search">Поиск по APP_ID и разрезам
    <input className="input" type="search" value={value} placeholder="ID, модель, порог, причина отказа"
      onChange={(event) => setDraft({ navigationKey, value: event.target.value })} />
  </label>
}

export function AppsTab() {
  const { runId, run } = useRunContext()
  if (run === null || run.status !== 'ready') return <NotReadyNotice run={run} />
  return <ReadyApps key={runId} runId={runId} />
}

function ReadyApps({ runId }: { runId: string }) {
  const [params, setParams] = useSearchParams()
  const location = useLocation()
  const decision = params.get('decision_change') ?? ''
  const source = params.get('change_source') ?? ''
  const hasAttr = params.get('has_attr_change') === '1'
  const search = params.get('search') ?? ''
  const sort = params.get('sort') || '-attributes_changed'
  const rawPage = Number(params.get('page') ?? 1)
  const page = Number.isSafeInteger(rawPage) && rawPage > 0 ? rawPage : 1
  const rawSize = Number(params.get('size') ?? 50)
  const size = [50, 100, 200].includes(rawSize) ? rawSize : 50
  const load = useCallback((signal: AbortSignal) => getApps(runId, {
    decision_change: decision ? decision.split(',') as DecisionChange[] : undefined,
    change_source: source ? source.split(',') as ChangeSource[] : undefined,
    has_attr_change: hasAttr, search, sort, page, size,
  }, { signal }), [runId, decision, source, hasAttr, search, sort, page, size])
  const { result, retry } = usePivotRequest(load)

  const update = useCallback((key: string, value: string, resetPage = true) => {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      if (value) next.set(key, value)
      else next.delete(key)
      if (resetPage) { next.set('page', '1'); next.delete('app') }
      return next
    }, { preventScrollReset: true })
  }, [setParams])
  const applySearch = useCallback((value: string) => update('search', value), [update])
  const reset = () => setParams((previous) => {
    const next = new URLSearchParams(previous)
    FILTER_KEYS.forEach((key) => next.delete(key))
    next.delete('app')
    next.set('page', '1')
    return next
  }, { preventScrollReset: true })
  const toggle = (key: string, current: string, value: string) => {
    const values = current.split(',').filter(Boolean)
    update(key, values.includes(value) ? values.filter((item) => item !== value).join(',') : [...values, value].join(','))
  }
  const chips = [
    ...decision.split(',').filter(Boolean).map((value) => ({ key: 'decision_change', value, label: DECISIONS[value as DecisionChange] ?? value })),
    ...source.split(',').filter(Boolean).map((value) => ({ key: 'change_source', value, label: `Источник: ${SOURCES[value as ChangeSource] ?? value}` })),
    ...(hasAttr ? [{ key: 'has_attr_change', value: '1', label: 'С различиями атрибутов' }] : []),
    ...(search ? [{ key: 'search', value: search, label: `Поиск: ${search}` }] : []),
  ]
  const sortHeader = (field: string, label: string) => <th scope="col"
    aria-sort={sort === field ? 'ascending' : sort === `-${field}` ? 'descending' : 'none'}>
    <button className="apps-sort" onClick={() => update('sort', sort === `-${field}` ? field : `-${field}`)}>
      {label} <span aria-hidden="true">{sort === field ? '↑' : sort === `-${field}` ? '↓' : '↕'}</span>
    </button>
  </th>
  const data = result.status === 'ready' ? result.data : null
  const pages = data ? Math.max(1, Math.ceil(data.total / size)) : page

  return <section className="apps" aria-labelledby="apps-title">
    <div className="panel apps-controls">
      <div className="apps-heading"><h2 id="apps-title">Заявки</h2><button className="btn" disabled>Скачать CSV · скоро</button></div>
      <fieldset className="apps-filter"><legend>Решение</legend>
        {Object.entries(DECISIONS).map(([value, label]) => <label key={value}><input type="checkbox"
          checked={decision.split(',').includes(value)} onChange={() => toggle('decision_change', decision, value)} />{label}</label>)}
      </fieldset>
      <fieldset className="apps-filter"><legend>Источник</legend>
        {Object.entries(SOURCES).map(([value, label]) => <label key={value}><input type="checkbox"
          checked={source.split(',').includes(value)} onChange={() => toggle('change_source', source, value)} />{label}</label>)}
      </fieldset>
      <div className="apps-search-row"><Search navigationKey={location.key} applied={search} onApply={applySearch} />
        <label><input type="checkbox" checked={hasAttr} onChange={() => update('has_attr_change', hasAttr ? '' : '1')} />Только с различиями атрибутов</label>
      </div>
      {chips.length > 0 && <div className="apps-chips" aria-label="Активные фильтры">
        {chips.map(({ key, value, label }) => <button className="btn" key={`${key}:${value}`} aria-label={`Убрать фильтр ${label}`}
          onClick={() => key === 'decision_change' || key === 'change_source' ? toggle(key, params.get(key) ?? '', value) : update(key, '')}>
          {label} <span aria-hidden="true">×</span></button>)}
        <button className="btn" onClick={reset}>Сбросить</button>
      </div>}
    </div>
    {result.status === 'error' && <ErrorBox message={result.message} onRetry={retry} />}
    {result.status === 'loading' && <div className="apps-skeleton panel" role="status" aria-label="Загрузка заявок">
      <span className="visually-hidden">Загрузка заявок</span>{Array.from({ length: 6 }, (_, i) => <div key={i} />)}
    </div>}
    {data && (data.apps.length === 0 ? <EmptyState title={data.total === 0 ? 'Ничего не найдено' : 'На этой странице нет заявок'}
      hint={data.total === 0 ? 'Измените поиск или сбросьте фильтры.' : 'Перейдите на первую страницу выборки.'}
      action={<button className="btn" onClick={data.total === 0 ? reset : () => update('page', '1', false)}>{data.total === 0 ? 'Сбросить фильтры' : 'На первую страницу'}</button>} /> :
      <div className="table-scroll apps-table-scroll" tabIndex={0} aria-label="Таблица заявок, прокручиваемая область">
        <table className="table apps-table"><caption className="visually-hidden">Заявки: значения до и после</caption>
          <thead><tr>{sortHeader('app_id', 'APP_ID')}<th scope="col">Решение · до / после</th>{sortHeader('attributes_changed', 'Изменено атр.')}
            <th scope="col">Модель · до / после</th><th scope="col">Порог · до / после</th><th scope="col">Причина отказа · до / после</th><th scope="col">Источник</th></tr></thead>
          <tbody>{data.apps.map((app) => <tr key={app.app_id} tabIndex={0} aria-label={`Открыть заявку ${app.app_id}`}
            aria-current={params.get('app') === app.app_id ? 'true' : undefined} onClick={() => update('app', app.app_id, false)}
            onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); update('app', app.app_id, false) } }}>
            <td className="mono">{app.app_id}</td><td><Pair before={app.decision_before} after={app.decision_after} badge /></td>
            <td className="num">{formatNumber(app.attributes_changed)}</td>
            <td className={app.pd_model_before !== app.pd_model_after ? 'apps-different' : undefined}><Pair before={app.pd_model_before} after={app.pd_model_after} /></td>
            <td className={app.cutoff_before !== app.cutoff_after ? 'apps-different' : undefined}><Pair before={app.cutoff_before} after={app.cutoff_after} /></td>
            <td className={app.reject_reason_before !== app.reject_reason_after ? 'apps-different' : undefined}><Pair before={app.reject_reason_before} after={app.reject_reason_after} /></td>
            <td>{SOURCES[app.change_source] ?? DASH}</td>
          </tr>)}</tbody>
        </table>
      </div>)}
    <div className="apps-pagination">
      <span role="status">{data ? `Показано ${formatNumber(data.apps.length ? (page - 1) * size + 1 : 0)}–${formatNumber(data.apps.length ? (page - 1) * size + data.apps.length : 0)} из ${formatNumber(data.total)}` : result.status === 'error' ? 'Выборка не загружена' : 'Загрузка выборки…'}</span>
      <label>На странице <select className="select" value={size} onChange={(event) => update('size', event.target.value)}>
        {[50, 100, 200].map((value) => <option key={value}>{value}</option>)}
      </select></label>
      <div className="apps-page-buttons"><button className="btn" disabled={!data || page <= 1} onClick={() => update('page', String(page - 1), false)}>Назад</button>
        <span>{page}{data ? ` / ${pages}` : ''}</span><button className="btn" disabled={!data || page >= pages} onClick={() => update('page', String(page + 1), false)}>Далее</button></div>
    </div>
  </section>
}
