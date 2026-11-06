import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createRun, isAbortError } from '../../api'
import { ErrorBox } from '../../components'

type RetryRunButtonProps = {
  /** Конфигурация упавшего прогона — повторяем ровно её. */
  configId: string
}

/**
 * «Повторить запуск»: создаёт новый прогон с той же конфигурацией и уводит в его журнал.
 * Старый прогон остаётся в списке — его результат никуда не девается.
 */
export function RetryRunButton({ configId }: RetryRunButtonProps) {
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  const onClick = async () => {
    setStarting(true)
    setError(null)
    try {
      const created = await createRun(configId)
      navigate(`/runs/${encodeURIComponent(created.id)}/log`)
    } catch (e) {
      if (!isAbortError(e)) {
        setError(e instanceof Error ? e.message : 'Не удалось запустить прогон заново')
      }
      setStarting(false)
    }
  }

  return (
    <>
      <button type="button" className="btn" onClick={onClick} disabled={starting}>
        {starting ? 'Запускаем…' : 'Повторить запуск'}
      </button>
      {error !== null && <ErrorBox message={error} />}
    </>
  )
}
