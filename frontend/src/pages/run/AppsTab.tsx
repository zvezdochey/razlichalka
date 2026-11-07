import { useCallback, useEffect, useState } from 'react'
import { useLocation, useSearchParams } from 'react-router-dom'
import { downloadAppsCsv, getApps } from '../../api'
import type { ChangeSource, DecisionChange } from '../../api'
import { EmptyState, ErrorBox } from '../../components'
import { DECISION_CHANGE_LABELS, decisionLabel } from '../../lib/decisions'
import { DASH, formatNumber } from '../../lib/format'
import { NotReadyNotice } from './NotReadyNotice'
import { useRunContext } from './runContext'
import { usePivotRequest } from './usePivotRequest'
import { AppPanel } from './AppPanel'
import './AppsTab.css'

const DECISIONS = DECISION_CHANGE_LABELS
const SOURCES: Record<ChangeSource, string> = {
  logic: 'Из-за правил', data: 'Из-за данных заявки', both: 'И правила, и данные', none: 'Ничего не поменялось',
}
const FILTER_KEYS = ['decision_change', 'change_source', 'has_attr_change', 'search']

/**
 * «Только с различиями» включена по умолчанию, но только когда в ссылке нет ни одного фильтра.
 * Ссылки из Обзора и Сводной (?decision_change=…, ?has_attr_change=1) несут свои фильтры и
 * открывают ровно ту выборку, по которой кликнули. Явное «выключено» хранится как has_attr_change=0
 * (на бэк этот флаг не уходит — см. api/endpoints.ts).
 */
const hasDefaultFilters = (params: URLSearchParams) => FILTER_KEYS.every((key) => !params.has(key))

/**
 * Пара значений — отдельная ячейка на «до» и отдельная на «после» (а не одна ячейка
 * с обоими значениями через разделитель): так подпись «до»/«после» в шапке стоит
 * ровно над своим значением, а не читается общей строкой через слеш.
 * Цвет (apps-different) отмечает только факт различия, а не его оценку.
 * `label` — человеческая подпись значения (для решений); исходный код остаётся в `title`.
 */
function PairCells({ before, after, badge = false, label = (value) => value }: {
  before: string | null; after: string | null; badge?: boolean; label?: (value: string | null) => string | null
}) {
  const different = before !== after
  return <>
    <td className={different ? 'apps-different' : undefined}>
      <span className={badge ? 'chip' : undefined} title={before ?? DASH}>{label(before) ?? DASH}</span>
    </td>
    <td className={different ? 'apps-different' : undefined}>
      <span className={badge ? 'chip' : undefined} title={after ?? DASH}>{label(after) ?? DASH}</span>
    </td>
  </>
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
  return <label className="apps-search">Найти заявку (номер, модель, причина отказа)
    <input className="input" type="search" value={value} placeholder="Например, номер заявки или модель"
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
  const hasAttr = params.get('has_attr_change') === '1' || hasDefaultFilters(params)
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
  const [csv, setCsv] = useState<{ busy: boolean; error: string | null }>({ busy: false, error: null })
  // CSV — та же выборка, что в таблице (фильтры, поиск, сортировка), но целиком, без страниц
  const exportCsv = async () => {
    setCsv({ busy: true, error: null })
    try {
      await downloadAppsCsv(runId, {
        decision_change: decision ? decision.split(',') as DecisionChange[] : undefined,
        change_source: source ? source.split(',') as ChangeSource[] : undefined,
        has_attr_change: hasAttr, search, sort,
      })
      setCsv({ busy: false, error: null })
    } catch (e) {
      setCsv({ busy: false, error: e instanceof Error ? e.message : 'Не удалось скачать CSV' })
    }
  }

  const update = useCallback((key: string, value: string, resetPage = true) => {
    setParams((previous) => {
      const next = new URLSearchParams(previous)
      // Меняем другой фильтр при включённом по умолчанию «Только с различиями» — закрепляем его в ссылке,
      // иначе он пропадёт вместе с «отсутствием фильтров».
      if (FILTER_KEYS.includes(key) && key !== 'has_attr_change' && hasDefaultFilters(previous)) next.set('has_attr_change', '1')
      if (value) next.set(key, value)
      else next.delete(key)
      // Атрибут из сводной относится к одной открытой заявке: сменили заявку — забываем его
      if (key === 'app') next.delete('attr')
      if (resetPage) { next.set('page', '1'); next.delete('app'); next.delete('attr') }
      return next
    }, { preventScrollReset: true })
  }, [setParams])
  const applySearch = useCallback((value: string) => update('search', value), [update])
  const reset = () => setParams((previous) => {
    const next = new URLSearchParams(previous)
    FILTER_KEYS.forEach((key) => next.delete(key))
    next.set('has_attr_change', '0') // «Сбросить» убирает все фильтры, в том числе умолчание «Только с различиями»
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
    ...source.split(',').filter(Boolean).map((value) => ({ key: 'change_source', value, label: `Почему изменилось: ${SOURCES[value as ChangeSource] ?? value}` })),
    ...(hasAttr ? [{ key: 'has_attr_change', value: '1', label: 'Только с различиями' }] : []),
    ...(search ? [{ key: 'search', value: search, label: `Поиск: ${search}` }] : []),
  ]
  const sortHeader = (field: string, label: string) => <th scope="col" rowSpan={2}
    aria-sort={sort === field ? 'ascending' : sort === `-${field}` ? 'descending' : 'none'}>
    <button className="apps-sort" onClick={() => update('sort', sort === `-${field}` ? field : `-${field}`)}>
      {label} <span aria-hidden="true">{sort === field ? '↑' : sort === `-${field}` ? '↓' : '↕'}</span>
    </button>
  </th>
  /** Группа «до/после» в шапке: название поля сверху (на обе колонки), подписи под ним — каждая над своим значением. */
  const pairHead = (label: string) => <th scope="colgroup" colSpan={2}>{label}</th>
  const data = result.status === 'ready' ? result.data : null
  const pages = data ? Math.max(1, Math.ceil(data.total / size)) : page
  const appId = params.get('app')

  return <section className="apps" aria-labelledby="apps-title">
    <div className="panel apps-controls">
      <div className="apps-heading"><h2 id="apps-title">Заявки</h2><button className="btn" onClick={exportCsv} disabled={csv.busy}>{csv.busy ? 'Готовим CSV…' : 'Скачать CSV'}</button></div>
      {csv.error !== null && <ErrorBox message={csv.error} />}
      <fieldset className="apps-filter"><legend>Решение</legend>
        {Object.entries(DECISIONS).map(([value, label]) => <label key={value}><input type="checkbox"
          checked={decision.split(',').includes(value)} onChange={() => toggle('decision_change', decision, value)} />{label}</label>)}
      </fieldset>
      <fieldset className="apps-filter"><legend>Почему изменилось</legend>
        {Object.entries(SOURCES).map(([value, label]) => <label key={value}><input type="checkbox"
          checked={source.split(',').includes(value)} onChange={() => toggle('change_source', source, value)} />{label}</label>)}
      </fieldset>
      <p className="muted apps-hint">«До» — решение старой версии СПР, «после» — новой. Из-за правил — данные заявки те же, но новая версия посчитала иначе; из-за данных заявки — у заявки другие входные данные или ответ внешнего сервиса.</p>
      <div className="apps-search-row"><Search navigationKey={location.key} applied={search} onApply={applySearch} />
        <label><input type="checkbox" checked={hasAttr} onChange={() => update('has_attr_change', hasAttr ? '0' : '1')} />Только с различиями</label>
      </div>
      {chips.length > 0 && <div className="apps-chips" aria-label="Активные фильтры">
        {chips.map(({ key, value, label }) => <button className="btn" key={`${key}:${value}`} aria-label={`Убрать фильтр ${label}`}
          onClick={() => key === 'decision_change' || key === 'change_source' ? toggle(key, params.get(key) ?? '', value) : update(key, key === 'has_attr_change' ? '0' : '')}>
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
          <colgroup>
            <col /><col /><col /><col /><col /><col /><col /><col /><col /><col /><col />
          </colgroup>
          <thead>
            <tr>
              {sortHeader('app_id', 'Заявка')}
              {pairHead('Решение')}
              {sortHeader('attributes_changed', 'Полей ответа изменилось')}
              <th scope="col" rowSpan={2} title="Почему у заявки что-то поменялось: из-за правил или из-за данных">Почему изменилось</th>
              {pairHead('Модель оценки')}
              {pairHead('Набор порогов')}
              {pairHead('Причина отказа')}
            </tr>
            <tr>
              <th scope="col">до</th><th scope="col">после</th>
              <th scope="col">до</th><th scope="col">после</th>
              <th scope="col">до</th><th scope="col">после</th>
              <th scope="col">до</th><th scope="col">после</th>
            </tr>
          </thead>
          <tbody>{data.apps.map((app) => <tr key={app.app_id} tabIndex={0} aria-label={`Открыть заявку ${app.app_id}`}
            aria-current={params.get('app') === app.app_id ? 'true' : undefined} onClick={() => update('app', app.app_id, false)}
            onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); update('app', app.app_id, false) } }}>
            <td className="mono">{app.app_id}</td>
            <PairCells before={app.decision_before} after={app.decision_after} badge label={decisionLabel} />
            <td className="num">{formatNumber(app.attributes_changed)}</td>
            {/* «Почему» — сразу за решением и числом полей: на узком экране главное видно без прокрутки */}
            <td>{app.change_source === null ? DASH : SOURCES[app.change_source]}</td>
            <PairCells before={app.pd_model_before} after={app.pd_model_after} />
            <PairCells before={app.cutoff_before} after={app.cutoff_after} />
            <PairCells before={app.reject_reason_before} after={app.reject_reason_after} />
          </tr>)}</tbody>
        </table>
      </div>)}
    <p className="muted apps-hint">Нажмите на заявку, чтобы увидеть, что в ней изменилось. Причина отказа CUTOFF — оценка модели ниже порога; «—» — отказа не было.</p>
    <div className="apps-pagination">
      <span role="status">{data ? `Показано ${formatNumber(data.apps.length ? (page - 1) * size + 1 : 0)}–${formatNumber(data.apps.length ? (page - 1) * size + data.apps.length : 0)} из ${formatNumber(data.total)}` : result.status === 'error' ? 'Выборка не загружена' : 'Загрузка выборки…'}</span>
      <label>На странице <select className="select" value={size} onChange={(event) => update('size', event.target.value)}>
        {[50, 100, 200].map((value) => <option key={value}>{value}</option>)}
      </select></label>
      <div className="apps-page-buttons"><button className="btn" disabled={!data || page <= 1} onClick={() => update('page', String(page - 1), false)}>Назад</button>
        <span>{page}{data ? ` / ${pages}` : ''}</span><button className="btn" disabled={!data || page >= pages} onClick={() => update('page', String(page + 1), false)}>Далее</button></div>
    </div>
    {appId && <AppPanel key={appId} runId={runId} appId={appId} focusPath={params.get('attr') ?? undefined}
      app={data?.apps.find((item) => item.app_id === appId)}
      onClose={() => update('app', '', false)} />}
  </section>
}
