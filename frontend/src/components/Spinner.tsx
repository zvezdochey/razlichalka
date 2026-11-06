import './Spinner.css'

type SpinnerProps = {
  /** Что именно грузится — попадёт в подпись и в aria-label. */
  label?: string
}

/** Ожидание. Единственная анимация в состоянии загрузки. */
export function Spinner({ label = 'Загружаем' }: SpinnerProps) {
  return (
    <div className="spinner" role="status">
      <span className="spinner__dial" aria-hidden="true" />
      <span className="muted">{label}</span>
    </div>
  )
}
