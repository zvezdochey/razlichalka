import { useEffect, useState } from 'react'
import { isAbortError } from '../../api'

type Loader<T> = (signal: AbortSignal) => Promise<T>
type RequestResult<T> =
  | { status: 'loading' }
  | { status: 'ready'; data: T; elapsed: number }
  | { status: 'error'; message: string }

export function usePivotRequest<T>(load: Loader<T>) {
  const [attempt, setAttempt] = useState(0)
  const [response, setResponse] = useState<{ load: Loader<T>; attempt: number; result: RequestResult<T> }>()

  useEffect(() => {
    const controller = new AbortController()
    const start = performance.now()
    void load(controller.signal).then(
      (data) => {
        if (controller.signal.aborted) return
        setResponse({ load, attempt, result: { status: 'ready', data, elapsed: performance.now() - start } })
      },
      (error: unknown) => {
        if (controller.signal.aborted || isAbortError(error)) return
        const message = error instanceof Error ? error.message : 'Не удалось загрузить данные'
        setResponse({ load, attempt, result: { status: 'error', message } })
      },
    )
    return () => controller.abort()
  }, [load, attempt])

  const result: RequestResult<T> = response?.load === load && response.attempt === attempt
    ? response.result
    : { status: 'loading' }

  return { result, retry: () => setAttempt((previous) => previous + 1) }
}
