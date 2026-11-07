import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getReportHtml, isAbortError } from '../api'
import { ErrorBox, Spinner } from '../components'
import './ReportPage.css'

/**
 * Постоянная ссылка на HTML-отчёт прогона: `/runs/<id>/report`.
 *
 * Бэк отдаёт отчёт только владельцу (заголовок X-User), а обычный переход по ссылке заголовков не шлёт.
 * Поэтому документ грузит страница приложения от имени выбранного пользователя и показывает его целиком.
 * Ссылки внутри отчёта открываются во всём окне (`<base target="_top">`), а не внутри рамки.
 */
export function ReportPage() {
  const { id = '' } = useParams()
  const [html, setHtml] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    getReportHtml(id, { signal: controller.signal }).then(
      (text) => {
        setHtml(text.replace(/<head>/i, '<head><base target="_top">'))
        setError(null)
      },
      (e: unknown) => {
        if (isAbortError(e)) return
        setError(e instanceof Error ? e.message : 'Не удалось загрузить отчёт')
      },
    )
    return () => controller.abort()
  }, [id, attempt])

  return (
    <div className="report-page">
      <div className="report-page__head">
        <Link to={`/runs/${encodeURIComponent(id)}/overview`}>← К прогону {id}</Link>
      </div>
      {error !== null && <ErrorBox message={error} onRetry={() => setAttempt((value) => value + 1)} />}
      {html === null && error === null && <Spinner label="Загружаем отчёт" />}
      {html !== null && (
        // Отчёт — наш же HTML без скриптов. sandbox без allow-scripts: код в рамке не исполняется;
        // allow-same-origin нужен, чтобы браузер отрисовал документ, переходы по ссылкам — только по клику
        <iframe
          className="report-page__frame"
          title={`Отчёт прогона ${id}`}
          srcDoc={html}
          sandbox="allow-same-origin allow-popups allow-top-navigation-by-user-activation"
        />
      )}
    </div>
  )
}
