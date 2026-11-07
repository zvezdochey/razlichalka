import { useCallback } from 'react'
import { getAppCard } from '../../api'
import type { AppCard, AppProduct, Decision, Reason } from '../../api'
import { ErrorBox, Spinner } from '../../components'
import { DECISION_LABELS } from '../../lib/decisions'
import { DASH } from '../../lib/format'
import { usePivotRequest } from './usePivotRequest'
import './AppWhy.css'

/** Общий словарь решений — тот же, что в «Заявках» и шапке карточки. */
const DECISION: Record<Decision, string> = DECISION_LABELS

const SOURCE: Record<Reason['source'], string> = {
  rule: 'Стоп-фактор',
  cutoff: 'Порог',
  score: 'Модель',
  product: 'Продукт',
  data: 'Входные данные',
  unknown: 'Источник не определён',
}

function formatParts(...parts: (string | number | null)[]): string | null {
  const values = parts.filter((part) => part !== null)
  return values.length > 0 ? values.join(' · ') : null
}

const FIELDS: { label: string; read: (product: AppProduct) => string | null }[] = [
  { label: 'Решение', read: (product) => DECISION[product.decision] },
  { label: 'Причина отказа', read: (product) => formatParts(product.reject_reason, product.reject_reason_code) },
  { label: 'Модель', read: (product) => product.pd_model },
  { label: 'Вероятность дефолта (PD)', read: (product) => formatParts(product.pd) },
  { label: 'Порог', read: (product) => formatParts(product.cutoff.name, product.cutoff.value) },
  {
    label: 'Сработавшие стоп-факторы',
    read: (product) => product.rules.filter((rule) => rule.hit === true).map((rule) => rule.name).sort().join(', ') || null,
  },
]

function Products({ before, after }: { before: AppProduct[]; after: AppProduct[] }) {
  const left = new Map(before.map((product) => [String(product.product_id), product]))
  const right = new Map(after.map((product) => [String(product.product_id), product]))
  const ids = new Set([...left.keys(), ...right.keys()])

  if (ids.size === 0) return <p className="muted">В обоих срезах нет продуктов.</p>

  return (
    <table className="table app-why-table">
      <caption className="visually-hidden">Детали продуктов до и после</caption>
      <thead>
        <tr><th scope="col">Параметр</th><th scope="col">До</th><th scope="col" className="app-why-after">После</th></tr>
      </thead>
      {Array.from(ids, (id) => {
        const beforeProduct = left.get(id)
        const afterProduct = right.get(id)
        return (
          <tbody key={id}>
            <tr>
              <th scope="rowgroup">Продукт <span className="mono">{id}</span></th>
              <td>{beforeProduct ? '' : 'Продукт отсутствует'}</td>
              <td className="app-why-after">{afterProduct ? '' : 'Продукт отсутствует'}</td>
            </tr>
            {FIELDS.map(({ label, read }) => {
              const oldValue = beforeProduct ? read(beforeProduct) : null
              const newValue = afterProduct ? read(afterProduct) : null
              const changed = oldValue !== newValue
              const valueClass = [label === 'Вероятность дефолта (PD)' && 'num', changed && 'app-why-changed'].filter(Boolean).join(' ')
              return (
                <tr key={label}>
                  <th scope="row">{label}</th>
                  <td className={valueClass}>{oldValue ?? DASH}</td>
                  <td className={`app-why-after ${valueClass}`}>{newValue ?? DASH}</td>
                </tr>
              )
            })}
          </tbody>
        )
      })}
    </table>
  )
}

function Offers({ label, offers }: { label: string; offers: AppCard['before']['offers'] }) {
  return (
    <div>
      <h4>{label}</h4>
      {offers.length === 0 ? <p className="muted">Офферов нет.</p> : (
        <ul>
          {offers.map(({ product_id, type }) => (
            <li key={JSON.stringify([String(product_id), type])}>
              <span className="mono">{product_id}</span> · {type ?? DASH}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function AppWhy({ runId, appId }: { runId: string; appId: string }) {
  const load = useCallback((signal: AbortSignal) => getAppCard(runId, appId, { signal }), [runId, appId])
  const { result, retry } = usePivotRequest(load)

  if (result.status === 'loading') return <Spinner label="Загружаем объяснение решения" />
  if (result.status === 'error') return <ErrorBox message={result.message} onRetry={retry} />

  const { before, after, reasons } = result.data
  return (
    <div className="app-why">
      <p className="app-why-decision">
        <span>{DECISION[before.decision]}</span>
        <span className="axis"><span aria-hidden="true">→ </span><span className="visually-hidden">после </span>{DECISION[after.decision]}</span>
      </p>
      <section aria-label="Объяснения решения">
        <h3>Почему изменилось решение</h3>
        {reasons.length === 0 ? <p className="muted">Объяснения для заявки отсутствуют.</p> : (
          <ul className="app-why-reasons">
            {reasons.map(({ text, source, confidence }) => (
              <li key={`${source}:${text}`} className={confidence === 'low' ? 'muted' : undefined}>
                <p>{text}</p>
                <small className="muted">{SOURCE[source]}{confidence === 'low' && ' · предположение'}</small>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section aria-label="Продукты">
        <h3>Продукты</h3>
        <Products before={before.products} after={after.products} />
      </section>
      <section aria-label="Офферы">
        <h3>Офферы</h3>
        <div className="app-why-offers"><Offers label="До" offers={before.offers} /><Offers label="После" offers={after.offers} /></div>
      </section>
    </div>
  )
}
