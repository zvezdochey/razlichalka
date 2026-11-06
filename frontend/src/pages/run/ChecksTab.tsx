import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import type { CheckRow, Stage } from '../../api'
import { getChecks, getStages, isAbortError } from '../../api'
import { EmptyState, ErrorBox, Spinner } from '../../components'
import { DASH, formatDateTime, formatNumber } from '../../lib/format'
import { ChecksAppsPanel } from './ChecksAppsPanel'
import './ChecksTab.css'
import {
  countOf,
  failedChecks,
  formatMetric,
  isErrorRow,
  sortByVerdict,
  verdictOf,
} from './checksRows'
import { NotReadyNotice } from './NotReadyNotice'
import { useRunContext } from './runContext'

/** Максимум договора (п. 10.1). Строк проверок обычно десятки, хватает одной страницы. */
const PAGE_SIZE = 500

type Loaded = {
  rows: CheckRow[]
  stage: Stage | null
}

type LoadState =
  | { status: 'loading' }
  | { status: 'ready'; data: Loaded }
  | { status: 'error'; message: string }

/**
 * Все строки проверок разом. Сортировку и счётчик «FAIL: N из M» считаем на фронте:
 * бэк отдаёт строки по проверкам, а «уверенные FAIL сверху» нужно по всей таблице.
 */
async function loadAllChecks(runId: string, signal: AbortSignal): Promise<CheckRow[]> {
  const rows: CheckRow[] = []
  for (let page = 1; ; page += 1) {
    const res = await getChecks(runId, { page, size: PAGE_SIZE }, { signal })
    rows.push(...res.rows)
    if (res.rows.length === 0 || rows.length >= res.total) return rows
  }
}

/** Вкладка «Проверки»: единая таблица вердиктов всех проверок и переход к заявкам. */
export function ChecksTab() {
  const { runId, run } = useRunContext()
  const ready = run?.status === 'ready'

  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)
  const [params, setParams] = useSearchParams()
  const onlyFail = params.get('result') === 'FAIL'

  // Открытая строка: её список заявок справа. Кнопку запоминаем, чтобы вернуть на неё фокус.
  const [opened, setOpened] = useState<CheckRow | null>(null)
  const opener = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    if (!ready) return
    const controller = new AbortController()
    const load = async () => {
      setState({ status: 'loading' })
      try {
        const [rows, stages] = await Promise.all([
          loadAllChecks(runId, controller.signal),
          getStages(runId, { signal: controller.signal }),
        ])
        setState({
          status: 'ready',
          data: { rows, stage: stages.find((stage) => stage.name === 'checks') ?? null },
        })
      } catch (e) {
        if (isAbortError(e) || controller.signal.aborted) return
        setState({
          status: 'error',
          message: e instanceof Error ? e.message : 'Не удалось загрузить проверки',
        })
      }
    }
    // eslint-disable-next-line react/set-state-in-effect -- загрузка данных эффектом и есть синхронизация с внешней системой
    void load()
    return () => controller.abort()
  }, [runId, ready, attempt])

  const closePanel = useCallback(() => {
    setOpened(null)
    opener.current?.focus()
  }, [])

  const setFilter = (fail: boolean) => {
    const next = new URLSearchParams(params)
    if (fail) next.set('result', 'FAIL')
    else next.delete('result')
    setParams(next, { replace: true })
    setOpened(null)
  }

  if (run?.status === 'pending' || run?.status === 'running') {
    return (
      <div className="panel">
        <p>Проверки ещё считаются</p>
        <p className="muted">
          Таблица появится, когда прогон закончится. Ход этапов — в{' '}
          <Link to="../log">журнале</Link>.
        </p>
      </div>
    )
  }
  if (!ready) return <NotReadyNotice run={run} />

  if (state.status === 'loading') {
    return (
      <div className="panel">
        <Spinner label="Загружаем результаты проверок" />
      </div>
    )
  }
  if (state.status === 'error') {
    return <ErrorBox message={state.message} onRetry={() => setAttempt((n) => n + 1)} />
  }

  const { rows, stage } = state.data
  if (stage !== null && stage.status !== 'ready') {
    return (
      <div className="panel">
        <p>Проверки ещё считаются</p>
        <p className="muted">
          Этап «{stage.title}» не завершён — см. <Link to="../log">журнал</Link>.
        </p>
      </div>
    )
  }
  if (rows.length === 0) {
    return (
      <EmptyState
        title="В конфигурации не выбраны проверки"
        hint="Подключите проверки к конфигурации и запустите прогон заново — их вердикты появятся здесь."
      />
    )
  }

  const failed = failedChecks(stage?.log ?? [])
  const fails = rows.filter((row) => row.result === 'FAIL').length
  const shown = sortByVerdict(onlyFail ? rows.filter((row) => row.result === 'FAIL') : rows)

  return (
    <div className="checks">
      {failed.length > 0 && (
        <div className="checks-errors" role="status">
          {failed.map((name) => (
            <p key={name}>
              Проверка <b>{name}</b> не выполнилась — см. <Link to="../log">журнал</Link>.
            </p>
          ))}
          <p className="muted">
            Это ошибка кода проверки, а не её вердикт: в таблице такая строка помечена «Не
            выполнилась».
          </p>
        </div>
      )}

      <div className="checks-bar">
        <div className="checks-filter" role="group" aria-label="Какие строки показать">
          <button
            type="button"
            className="btn"
            aria-pressed={!onlyFail}
            onClick={() => setFilter(false)}
          >
            Все
          </button>
          <button
            type="button"
            className="btn"
            aria-pressed={onlyFail}
            onClick={() => setFilter(true)}
          >
            Только FAIL
          </button>
        </div>
        <p className="checks-count">
          FAIL: <span className="num">{formatNumber(fails)}</span> из{' '}
          <span className="num">{formatNumber(rows.length)}</span>
        </p>
        {stage?.finished_at && (
          <p className="checks-updated muted">Проверено {formatDateTime(stage.finished_at)}</p>
        )}
      </div>

      <div className={opened ? 'checks-results checks-results--with-apps' : 'checks-results'}>
        {shown.length === 0 ? (
          <EmptyState
            title="FAIL нет — все проверки прошли"
            hint="Чтобы увидеть строки PASS, переключитесь на «Все»."
          />
        ) : (
          <div className="table-scroll checks-scroll">
            <table className="table checks-table">
              <caption className="visually-hidden">
                Результаты проверок. Сначала уверенные FAIL, затем FAIL с низкой уверенностью,
                затем PASS.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Проверка</th>
                  <th scope="col">Срез</th>
                  <th scope="col">Аргумент</th>
                  <th scope="col" className="num">Кол-во / база</th>
                  <th scope="col" className="num">Метрика</th>
                  <th scope="col">Результат</th>
                  <th scope="col">Уверенность</th>
                  <th scope="col" className="num">Заявки</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((row, index) => (
                  <CheckTableRow
                    key={`${row.check_name}-${row.argument ?? ''}-${row.source ?? ''}-${index}`}
                    row={row}
                    isError={isErrorRow(row, failed)}
                    isOpened={opened === row}
                    onOpen={(button) => {
                      opener.current = button
                      setOpened(row)
                    }}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {opened !== null && opened.apps_ref !== null && (
          <ChecksAppsPanel
            key={opened.apps_ref}
            runId={runId}
            row={opened}
            appsRef={opened.apps_ref}
            onClose={closePanel}
          />
        )}
      </div>
    </div>
  )
}

type CheckTableRowProps = {
  row: CheckRow
  isError: boolean
  isOpened: boolean
  onOpen: (button: HTMLButtonElement) => void
}

const VERDICT_CHIP = { pass: 'chip--pass', fail: 'chip--fail', low: 'chip--low' } as const

function CheckTableRow({ row, isError, isOpened, onOpen }: CheckTableRowProps) {
  const verdict = verdictOf(row)
  const count = countOf(row)

  return (
    <tr className={`checks-row checks-row--${verdict}${isOpened ? ' checks-row--opened' : ''}`}>
      <td>
        <div className="checks-name">{row.check_name}</div>
        {row.check_id !== null && <div className="checks-id mono">{row.check_id}</div>}
      </td>
      <td>{row.source ?? DASH}</td>
      <td className={isError ? 'checks-arg checks-arg--error mono' : 'checks-arg'}>
        {row.argument === null ? DASH : isError ? row.argument : <BreakableAt text={row.argument} />}
      </td>
      <td className="num">{isError || row.numbers === null ? DASH : row.numbers}</td>
      <td className="num">{isError || row.metric === null ? DASH : formatMetric(row.metric)}</td>
      <td>
        <span className={`chip ${VERDICT_CHIP[verdict]}`}>{row.result}</span>
      </td>
      <td className="checks-confidence">
        {isError ? (
          <span className="checks-error-label">Не выполнилась</span>
        ) : row.faint ? (
          'Низкая уверенность'
        ) : (
          <span className="muted">Высокая</span>
        )}
      </td>
      <td className="num">
        {row.apps_ref === null ? (
          DASH
        ) : (
          <button
            type="button"
            className="checks-apps-link"
            aria-expanded={isOpened}
            onClick={(event) => onOpen(event.currentTarget)}
          >
            {count === null ? 'Открыть' : formatNumber(count)}
            <span className="visually-hidden"> — заявки проверки «{row.check_name}»</span>
          </button>
        )}
      </td>
    </tr>
  )
}

/** Аргумент часто путь атрибута: разрешаем перенос после точек, а не посреди слова. */
function BreakableAt({ text }: { text: string }) {
  const parts = text.split('.')
  return (
    <>
      {parts.map((part, index) => (
        <Fragment key={index}>
          {part}
          {index < parts.length - 1 && (
            <>
              .<wbr />
            </>
          )}
        </Fragment>
      ))}
    </>
  )
}
