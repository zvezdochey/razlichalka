import { formatNumber } from '../../lib/format'
import './ProgressBar.css'

type ProgressBarProps = {
  done: number
  /** `0` или меньше — общий объём неизвестен, полосу рисовать нельзя. */
  total: number
  /** `false` — только полоса, без строки с числами (для узкой полосы в шапке). */
  withCaption?: boolean
}

/**
 * Прогресс запуска. Числовую полосу показываем только при известном `total`,
 * иначе — индикатор активности (DESIGN п. 5): полоса «на глазок» врёт.
 *
 * Единица измерения — **файлы**, не заявки: 4004 = 2002 заявки × 2 среза.
 */
export function ProgressBar({ done, total, withCaption = true }: ProgressBarProps) {
  const known = total > 0
  const percent = known ? Math.min(100, Math.round((done / total) * 100)) : 0

  return (
    <div className="progress">
      <div
        className={known ? 'progress__track' : 'progress__track progress__track--unknown'}
        role="progressbar"
        aria-valuemin={known ? 0 : undefined}
        aria-valuemax={known ? total : undefined}
        aria-valuenow={known ? done : undefined}
        aria-label="Обработано файлов"
      >
        {known && <div className="progress__fill" style={{ width: `${percent}%` }} />}
      </div>
      {withCaption && (
        <div className="progress__caption muted">
          {known ? (
            <>
              <span className="num">{formatNumber(done)}</span> из{' '}
              <span className="num">{formatNumber(total)}</span> файлов — это 2002 заявки × 2 среза
            </>
          ) : (
            'Обрабатываем — общий объём ещё неизвестен'
          )}
        </div>
      )}
    </div>
  )
}
