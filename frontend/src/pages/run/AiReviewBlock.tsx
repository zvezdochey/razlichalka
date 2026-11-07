import { useCallback, useEffect, useState } from 'react'
import type { AiReview } from '../../api'
import { getAiReview, isAbortError } from '../../api'
import { Spinner } from '../../components'
import { usePolling } from '../../hooks/usePolling'
import './AiReviewBlock.css'

const POLL_MS = 3000

/** «Мнение ИИ» (api.md п. 12): второе мнение по агрегатам, не замена проверкам. */
export function AiReviewBlock({ runId }: { runId: string }) {
  const [review, setReview] = useState<AiReview | null>(null)
  const [failure, setFailure] = useState<string | null>(null)

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        setReview(await getAiReview(runId, { signal }))
        setFailure(null)
      } catch (e) {
        if (isAbortError(e)) return
        setFailure(e instanceof Error ? e.message : 'Не удалось получить мнение ИИ')
      }
    },
    [runId],
  )

  useEffect(() => {
    const controller = new AbortController()
    // eslint-disable-next-line react/set-state-in-effect -- загрузка данных эффектом и есть синхронизация с внешней системой
    void load(controller.signal)
    return () => controller.abort()
  }, [load])

  // Пока модель считает — спрашиваем раз в несколько секунд.
  usePolling(() => load(), POLL_MS, review?.status !== 'pending')

  return (
    <section className="panel ai-review" aria-labelledby="ai-review-head">
      <h2 className="overview__head" id="ai-review-head">Мнение ИИ</h2>
      {failure !== null && <p className="muted">{failure}</p>}
      {failure === null && (review === null || review.status === 'pending') && (
        <Spinner label="Считаем мнение ИИ…" />
      )}
      {failure === null && review?.status === 'error' && (
        <p className="muted">{review.error.message}</p>
      )}
      {failure === null && review?.status === 'ready' && (
        <>
          <p className="ai-review__text">{review.text}</p>
          <p className="muted" title={`Модель: ${review.model}`}>
            Модель видела только общие цифры прогона, без отдельных заявок. Это второе мнение, а не замена проверкам.
          </p>
        </>
      )}
    </section>
  )
}
