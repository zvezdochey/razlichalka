import { forwardRef, useImperativeHandle, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'

/** Высота строки и отступ сверху — те же числа, что в CSS (`.code`). На них
 *  считаются положение подсветки и прокрутка к строке, поэтому держим их в одном месте. */
const LINE_HEIGHT = 20
const PADDING_TOP = 8
const INDENT = '    '

export type CodeEditorHandle = {
  /** Прокрутить к строке (с 1) и поставить на неё курсор. */
  scrollToLine: (line: number) => void
}

type CodeEditorProps = {
  value: string
  onChange: (value: string) => void
  readOnly: boolean
  /** Строки с ошибками проверки — подсвечены и помечены в номерах. */
  errorLines: ReadonlySet<number>
  /** Строка, на которую пришли по ссылке из журнала. */
  targetLine: number | null
  label: string
}

/**
 * Редактор кода на обычном `<textarea>`: моноширинный шрифт, номера строк сбоку,
 * Tab вставляет 4 пробела. Monaco и CodeMirror не тащим — это мегабайты ради того,
 * что textarea и так умеет. Строки не переносятся (`wrap="off"`), поэтому строка
 * кода = строка на экране, и подсветку можно поставить простым расчётом.
 */
export const CodeEditor = forwardRef<CodeEditorHandle, CodeEditorProps>(function CodeEditor(
  { value, onChange, readOnly, errorLines, targetLine, label },
  ref,
) {
  const textRef = useRef<HTMLTextAreaElement>(null)
  const [scrollTop, setScrollTop] = useState(0)
  // После Escape следующий Tab уводит фокус из поля, иначе с клавиатуры отсюда не выйти.
  const leaveOnTab = useRef(false)

  useImperativeHandle(ref, () => ({
    scrollToLine(line: number) {
      const text = textRef.current
      if (text === null) return
      // Строку ставим на треть высоты, а не к самому краю: видно и что выше, и что ниже.
      text.scrollTop = Math.max(0, (line - 1) * LINE_HEIGHT - text.clientHeight / 3)
      setScrollTop(text.scrollTop)
      const lines = text.value.split('\n')
      const start = lines.slice(0, Math.max(0, line - 1)).reduce((sum, l) => sum + l.length + 1, 0)
      text.focus({ preventScroll: true })
      text.setSelectionRange(start, start)
    },
  }))

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Escape') {
      leaveOnTab.current = true
      return
    }
    if (event.key !== 'Tab' || event.shiftKey || readOnly || leaveOnTab.current) {
      leaveOnTab.current = false
      return
    }
    event.preventDefault()
    const text = event.currentTarget
    // insertText сохраняет историю правок (Ctrl+Z работает). Если браузер его не умеет —
    // вставляем руками, история при этом теряется.
    if (!document.execCommand('insertText', false, INDENT)) {
      text.setRangeText(INDENT, text.selectionStart, text.selectionEnd, 'end')
      onChange(text.value)
    }
  }

  const lineCount = value.split('\n').length
  const numbers = Array.from({ length: lineCount }, (_, i) => i + 1)
  const marks = [...errorLines].filter((line) => line >= 1 && line <= lineCount)
  const shift = { transform: `translateY(${-scrollTop}px)` }

  return (
    <div className={`code${readOnly ? ' code--readonly' : ''}`}>
      <div className="code__marks" aria-hidden="true">
        <div style={shift}>
          {targetLine !== null && targetLine <= lineCount && (
            <div
              className="code__mark code__mark--target"
              style={{ top: PADDING_TOP + (targetLine - 1) * LINE_HEIGHT }}
            />
          )}
          {marks.map((line) => (
            <div
              key={line}
              className="code__mark code__mark--error"
              style={{ top: PADDING_TOP + (line - 1) * LINE_HEIGHT }}
            />
          ))}
        </div>
      </div>

      <div className="code__gutter" aria-hidden="true">
        <div style={shift}>
          {numbers.map((line) => (
            <div key={line} className={errorLines.has(line) ? 'code__num--error' : undefined}>
              {line}
            </div>
          ))}
        </div>
      </div>

      <textarea
        ref={textRef}
        className="code__text"
        aria-label={label}
        value={value}
        readOnly={readOnly}
        wrap="off"
        spellCheck={false}
        autoCapitalize="off"
        autoComplete="off"
        autoCorrect="off"
        onChange={(event) => onChange(event.target.value)}
        onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
        onKeyDown={handleKeyDown}
      />
    </div>
  )
})
