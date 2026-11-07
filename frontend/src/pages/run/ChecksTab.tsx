import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import type { CheckRow, Stage } from '../../api'
import { getChecks, getFactApps, getStages, isAbortError } from '../../api'
import { EmptyState, ErrorBox, Spinner } from '../../components'
import { DASH, formatDateTime, formatNumber } from '../../lib/format'
import { ChecksAppsPanel } from './ChecksAppsPanel'
import './ChecksTab.css'
import {
  checksCount,
  countOf,
  appsLinkLabel,
  displayArgument,
  isArDrop,
  variantLabel,
  variantsOf,
  failedChecks,
  groupRows,
  formatMetric,
  formatShare,
  isErrorRow,
  isShareMetric,
  plural,
  shortPath,
  sortByVerdict,
  sourceLabel,
  verdictOf,
} from './checksRows'
import { NotReadyNotice } from './NotReadyNotice'
import { useRunContext } from './runContext'

/** Максимум договора (п. 10.1). Строк проверок обычно десятки, хватает одной страницы. */
const PAGE_SIZE = 500

/** Сколько запросов «сколько заявок за ссылкой» идёт параллельно. */
const SAMPLE_WORKERS = 4

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
  // Развёрнутые группы строк (по умолчанию все свёрнуты).
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())
  const toggleGroup = (key: string) =>
    setExpandedGroups((prev) => {
      const next = new Set(prev)
      if (!next.delete(key)) next.add(key)
      return next
    })

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
          // Журнал нужен только для плашки об ошибках и времени проверки:
          // если он не пришёл, таблицу всё равно показываем.
          getStages(runId, { signal: controller.signal }).catch((e: unknown) => {
            if (isAbortError(e)) throw e
            return []
          }),
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

  // Сколько заявок реально лежит за каждой ссылкой `apps_ref`. Прогон просит у проверок все заявки
  // (`app_ids_limit` перекрыт), но своя проверка может сохранить часть — тогда пишем «20 примеров из 273».
  // Грузим фоном по одной заявке на ссылку: таблица показывается сразу, подпись уточняется следом.
  const [samples, setSamples] = useState<Record<string, number>>({})
  const loadedRows = state.status === 'ready' ? state.data.rows : null
  useEffect(() => {
    if (loadedRows === null) return
    const controller = new AbortController()
    const queue = [...new Set(loadedRows.map((row) => row.apps_ref).filter((ref): ref is string => ref !== null))]
    // Не больше SAMPLE_WORKERS запросов одновременно: строк проверок десятки, бэк заваливать незачем.
    const worker = async () => {
      for (let ref = queue.shift(); ref !== undefined; ref = queue.shift()) {
        if (controller.signal.aborted) return
        const key = ref
        try {
          const data = await getFactApps(runId, key, 1, 1, { signal: controller.signal })
          setSamples((prev) => ({ ...prev, [key]: data.total }))
        } catch {
          // Не узнали — на кнопке останется число из строки, как раньше.
        }
      }
    }
    for (let i = 0; i < SAMPLE_WORKERS; i += 1) void worker()
    return () => controller.abort()
  }, [runId, loadedRows])

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
  const variants = variantsOf(rows) // номера считаем по всем строкам, чтобы фильтр «Только FAIL» их не менял

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

      {/* Новичок не знает, что такое FAIL и что с ним делать: сначала смысл, потом числа. */}
      <p className="checks-summary">
        Автопроверки ищут подозрительные последствия новой версии СПР. <b>FAIL</b> — проверка нашла
        проблему, её стоит разобрать до выпуска; <b>PASS</b> — всё в норме.{' '}
        {fails > 0 ? 'Есть непройденные проверки — разберите их перед выпуском.' : 'Все проверки пройдены.'}
      </p>
      <p className="checks-summary muted">
        Не пройдено{' '}
        <b className="num">
          {formatNumber(fails)} из {formatNumber(rows.length)}
        </b>{' '}
        строк (проверок: {formatNumber(checksCount(rows))}). Одна проверка даёт несколько строк — по каждому
        продукту, модели или атрибуту, который она смотрела.
      </p>

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
                  <th scope="col" title="К какой версии СПР относится результат: «до» — старая, «после» — новая">Версия</th>
                  <th scope="col" title="Что именно проверяли: продукт, модель или атрибут">Объект проверки</th>
                  <th scope="col" className="num" title="Сколько заявок задело / из скольких проверяли">Заявок задето / из</th>
                  <th scope="col" className="num" title="Что посчитала проверка">Что намерили</th>
                  <th scope="col">Результат</th>
                  <th scope="col" title="Насколько можно доверять результату: низкая — заявок слишком мало для вывода">Уверенность</th>
                  <th scope="col" className="num" title="Открыть заявки, на которых сработала проверка">Заявки</th>
                </tr>
              </thead>
              <tbody>
                {groupRows(shown).map((item) => {
                  const rowsToShow =
                    item.kind === 'row'
                      ? [item.row]
                      : expandedGroups.has(item.key)
                        ? item.rows
                        : []
                  return (
                    <Fragment key={item.kind === 'row' ? `row-${item.row.check_name}-${item.row.argument ?? ''}-${item.row.source ?? ''}` : `group-${item.key}`}>
                      {item.kind === 'group' && (
                        <tr className="checks-group">
                          <td colSpan={8}>
                            <button
                              type="button"
                              className="checks-group__toggle"
                              aria-expanded={expandedGroups.has(item.key)}
                              onClick={() => toggleGroup(item.key)}
                            >
                              <span aria-hidden="true">{expandedGroups.has(item.key) ? '▾' : '▸'}</span>{' '}
                              <b>{item.title}</b> — {formatNumber(item.rows.length)}{' '}
                              {plural(item.rows.length, ['строка', 'строки', 'строк'])}
                              {item.fails > 0 && `, не пройдено (FAIL): ${formatNumber(item.fails)}`}
                              {expandedGroups.has(item.key) ? ', свернуть' : ', развернуть'}
                            </button>
                          </td>
                        </tr>
                      )}
                      {rowsToShow.map((row, index) => (
                        <CheckTableRow
                          key={`${row.check_name}-${row.argument ?? ''}-${row.source ?? ''}-${index}`}
                          row={row}
                          variant={variants.get(row)}
                          isError={isErrorRow(row, failed)}
                          isOpened={opened === row}
                          samples={row.apps_ref === null ? undefined : samples[row.apps_ref]}
                          onOpen={(button) => {
                            opener.current = button
                            setOpened(row)
                          }}
                        />
                      ))}
                    </Fragment>
                  )
                })}
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
  /** Сколько заявок реально за ссылкой; `undefined` — ещё не узнали. */
  samples?: number
  /** Номер варианта, если есть строка-близнец с другими заявками. */
  variant?: number
  isError: boolean
  isOpened: boolean
  onOpen: (button: HTMLButtonElement) => void
}

const VERDICT_CHIP = { pass: 'chip--pass', fail: 'chip--fail', low: 'chip--low' } as const

function CheckTableRow({ row, variant, samples, isError, isOpened, onOpen }: CheckTableRowProps) {
  const verdict = verdictOf(row)
  const count = countOf(row)
  const argument = isError ? row.argument : displayArgument(row)

  return (
    <tr className={`checks-row checks-row--${verdict}${isOpened ? ' checks-row--opened' : ''}`}>
      <td>
        {/* Внутренний id — только в подсказке */}
        <div className="checks-name" title={row.check_id !== null ? `Код проверки: ${row.check_id}` : undefined}>
          {row.check_name}
          {variant !== undefined && (
            <span
              className="muted"
              title="Проверка вернула несколько строк с одним названием и одинаковыми числами, но для разных групп заявок (например, у стоп-фактора: правило удалено из стратегии и правило перестало срабатывать)"
            >
              {` · ${variantLabel(row, variant)}`}
            </span>
          )}
        </div>
      </td>
      <td>{sourceLabel(row.source) ?? DASH}</td>
      <td
        className={isError ? 'checks-arg checks-arg--error mono' : 'checks-arg'}
        title={argument ?? undefined}
      >
        {argument === null ? DASH : isError ? argument : <BreakableAt text={shortPath(argument)} />}
      </td>
      <td
        className="num"
        title={isArDrop(row) ? 'потеряли одобрение / заявок по продукту' : undefined}
      >
        {isError || row.numbers === null ? DASH : row.numbers}
      </td>
      <td className="num">
        {isError || row.metric === null ? (
          DASH
        ) : isArDrop(row) ? (
          <span title={`Относительное падение доли одобрений (Approval Rate) после изменения; FAIL, если больше 10 %. Исходное значение ${formatMetric(row.metric)}`}>
            {`падение ${formatShare(row.metric)}`}
          </span>
        ) : isShareMetric(row) ? (
          // Доля 0..1 — показываем процентом, исходное число по наведению.
          <span title={`Исходное значение: ${formatMetric(row.metric)}`}>
            {formatShare(row.metric)}
          </span>
        ) : (
          formatMetric(row.metric)
        )}
      </td>
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
            {appsLinkLabel(samples, count)}
            <span className="visually-hidden"> — проверка «{row.check_name}»</span>
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
