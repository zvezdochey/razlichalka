import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'

const FOCUSABLE = 'button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex="0"]'

/**
 * Поведение модального окна:
 * - при открытии фокус уходит внутрь, при закрытии возвращается туда, откуда открыли;
 * - Tab и Shift+Tab ходят по кругу внутри окна;
 * - Escape закрывает окно;
 * - страница под окном не прокручивается.
 */
export function useDialogFocus(dialog: RefObject<HTMLElement | null>, onClose: () => void) {
  const opener = useRef<HTMLElement | null>(null)

  useEffect(() => {
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    dialog.current?.querySelector<HTMLElement>(FOCUSABLE)?.focus()

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    return () => {
      document.body.style.overflow = previousOverflow
      opener.current?.focus()
    }
  }, [dialog])

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab' || !dialog.current) return

      const items = Array.from(dialog.current.querySelectorAll<HTMLElement>(FOCUSABLE))
      if (items.length === 0) return
      const first = items[0]
      const last = items[items.length - 1]

      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [dialog, onClose])
}
