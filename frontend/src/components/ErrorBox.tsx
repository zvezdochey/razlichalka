import './ErrorBox.css'

type ErrorBoxProps = {
  /** Текст ошибки показываем как есть: это message из ответа бэка. */
  message: string
  /** Необязательная повторная попытка — «предложить действие», а не только сообщить. */
  onRetry?: () => void
}

/** Ошибка: называем, что произошло, без извинений. */
export function ErrorBox({ message, onRetry }: ErrorBoxProps) {
  return (
    <div className="error-box" role="alert">
      <div className="error-box__text">{message}</div>
      {onRetry && (
        <button type="button" className="btn" onClick={onRetry}>
          Повторить
        </button>
      )}
    </div>
  )
}
