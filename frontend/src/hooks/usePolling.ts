import { useEffect, useRef } from 'react'

/**
 * Опрос ручки с заданной частотой — для статуса запуска, пока он идёт.
 *
 * Останавливается в трёх случаях:
 *  - `stopWhen` стало `true` (например статус уже `ready` или `error`);
 *  - компонент размонтировался (ушли со страницы);
 *  - вкладку свернули или переключили (`document.hidden`) — запросы в фоне не нужны,
 *    при возврате сразу делаем один опрос, чтобы не ждать целый интервал.
 *
 * `poll` можно пересоздавать на каждый рендер: мы храним его в ref, таймер от этого
 * не перезапускается. Ошибку внутри `poll` глотаем — её должен обработать и положить
 * в состояние сам вызывающий, иначе опрос развалится на первом сетевом сбое.
 */
export function usePolling(
  poll: () => void | Promise<void>,
  intervalMs: number,
  stopWhen: boolean,
): void {
  const pollRef = useRef(poll)
  useEffect(() => {
    pollRef.current = poll
  }, [poll])

  useEffect(() => {
    if (stopWhen) return

    let stopped = false
    let timer: number | undefined

    const schedule = () => {
      if (stopped) return
      timer = window.setTimeout(tick, intervalMs)
    }

    const tick = async () => {
      if (stopped) return
      if (!document.hidden) {
        try {
          await pollRef.current()
        } catch {
          // Вызывающий сам решает, что показать: здесь только не даём опросу умереть.
        }
      }
      schedule()
    }

    const onVisibilityChange = () => {
      if (stopped || document.hidden) return
      // Вернулись во вкладку: опрашиваем сразу, не дожидаясь таймера.
      window.clearTimeout(timer)
      void tick()
    }

    schedule()
    document.addEventListener('visibilitychange', onVisibilityChange)

    return () => {
      stopped = true
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [intervalMs, stopWhen])
}
