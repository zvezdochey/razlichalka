import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import type { Stage, StageLogEntry, StageName } from '../../api'
import { getStages, isAbortError, isCancelled } from '../../api'
import { ErrorBox, Spinner, StatusBadge } from '../../components'
import { usePolling } from '../../hooks/usePolling'
import { formatDuration, formatTime } from '../../lib/format'
import './LogTab.css'
import { ProgressBar } from './ProgressBar'
import { RetryRunButton } from './RetryRunButton'
import { useRunContext } from './runContext'
import { STAGE_ACTIVE_TEXT, STAGE_ORDER, STAGE_TITLES } from './stages'

const POLL_INTERVAL_MS = 1000

/** Этап, который бэк ещё не прислал: путь должен быть виден целиком. */
function placeholderStage(name: StageName): Stage {
  return {
    name,
    title: STAGE_TITLES[name],
    status: 'pending',
    started_at: null,
    finished_at: null,
    procedure_id: null,
    code_ref: null,
    log: [],
  }
}

/** Ссылка в рабочую область процедур: `/procedures?id=<id>&line=<строка>`. */
function codeLink(procedureId: string, line: number | undefined): string {
  const search = new URLSearchParams({ id: procedureId })
  if (line !== undefined && line > 0) search.set('line', String(line))
  return `/procedures?${search.toString()}`
}

/** Четыре известных этапа в договорном порядке, плюс всё лишнее — в конец. */
function orderStages(stages: Stage[]): Stage[] {
  const byName = new Map(stages.map((stage) => [stage.name, stage]))
  const known = STAGE_ORDER.map((name) => byName.get(name) ?? placeholderStage(name))
  const extra = stages.filter((stage) => !STAGE_ORDER.includes(stage.name))
  return [...known, ...extra]
}

/**
 * Уровень записи журнала. Словарь в договоре пока не закреплён (расхождение №7),
 * поэтому незнакомый уровень показываем как есть и ничего не ломаем.
 */
function levelLook(
  level: string,
  cancelled: boolean,
): { label: string; icon: string; tone: string } {
  // Запуск остановлен человеком — бэк пишет это уровнем `error`, но аварии не было,
  // поэтому внутри остановленного прогона такие строки нейтральные.
  if (level === 'error' && cancelled) return { label: 'остановлено', icon: '■', tone: 'warn' }
  if (level === 'error') return { label: 'ошибка', icon: '×', tone: 'error' }
  if (level === 'warn') return { label: 'предупреждение', icon: '!', tone: 'warn' }
  if (level === 'info') return { label: 'инфо', icon: 'i', tone: 'info' }
  // Незнакомый уровень показываем как есть: словарь в договоре пока не закреплён.
  return { label: level, icon: 'i', tone: 'info' }
}

/** Журнал этапов: что выполняется сейчас, что уже готово, что впереди. */
export function LogTab() {
  const { runId, run, reloadRun } = useRunContext()
  const [stages, setStages] = useState<Stage[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Раскрытые логи храним по имени этапа, а не по индексу: опрос раз в секунду
  // не должен схлопывать то, что человек открыл.
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [now, setNow] = useState(() => Date.now())

  const load = useCallback(async () => {
    try {
      setStages(await getStages(runId))
      setNow(Date.now())
      setError(null)
    } catch (e) {
      if (isAbortError(e)) return
      setError(e instanceof Error ? e.message : 'Не удалось прочитать журнал этапов')
    }
  }, [runId])

  const status = run?.status ?? null
  const finished = status === 'ready' || status === 'error'

  // Перечитываем при каждой смене статуса, в том числе на последней: иначе
  // в журнале остался бы предпоследний снимок.
  useEffect(() => {
    // eslint-disable-next-line react/set-state-in-effect -- загрузка данных эффектом и есть синхронизация с внешней системой
    void load()
  }, [load, status])

  usePolling(load, POLL_INTERVAL_MS, finished)

  // Для завершённого запуска время «сейчас» останавливаем на его конце: иначе
  // длительность упавшего этапа продолжала бы тикать и через час после падения.
  const finishedAtMs = run?.finished_at === null ? null : Date.parse(run?.finished_at ?? '')
  const clock = finished && finishedAtMs !== null && !Number.isNaN(finishedAtMs) ? finishedAtMs : now

  const rows = stages === null ? null : orderStages(stages)
  const runError = run?.error ?? null
  const cancelled = isCancelled(runError)
  // Перезапуск сервера — тоже не авария прогона: показываем спокойно, как остановку.
  const interrupted = runError?.code === 'interrupted'

  const toggle = (stage: Stage) => {
    const isOpen = expanded[stage.name] ?? stage.status === 'error'
    setExpanded((current) => ({ ...current, [stage.name]: !isOpen }))
  }

  return (
    <div className="log">
      {/* Отмена — не авария: отдельный нейтральный блок, без красного. */}
      {(cancelled || interrupted) && runError !== null && (
        <div className="panel log__stop">
          <h2>{interrupted ? 'Прогон прерван' : 'Запуск остановлен'}</h2>
          <p className="muted">{runError.message}</p>
          {run !== null && <RetryRunButton configId={run.config_id} />}
        </div>
      )}

      {runError !== null && !cancelled && !interrupted && (
        <div className="panel log__fail" role="alert">
          <h2>Ошибка выполнения</h2>
          <p>{runError.message}</p>
          {run !== null && <RetryRunButton configId={run.config_id} />}
        </div>
      )}

      {error !== null && <ErrorBox message={error} onRetry={() => void load()} />}

      {rows === null && error === null && (
        <div className="panel">
          <Spinner label="Читаем журнал этапов" />
        </div>
      )}

      {rows !== null && (
        <ol className="log__stages panel">
          {rows.map((stage) => {
            const active = stage.status === 'running'
            const isOpen = expanded[stage.name] ?? stage.status === 'error'
            const procedureId = stage.code_ref?.procedure_id ?? stage.procedure_id

            // Остановленный этап помечаем отдельно: красная кромка — только для падения.
            const tone = stage.status === 'error' && (cancelled || interrupted) ? 'stopped' : stage.status

            return (
              <li key={stage.name} className={`stage stage--${tone}`}>
                <div className="stage__head">
                  <span className="stage__title">{STAGE_TITLES[stage.name] ?? stage.title}</span>
                  {stage.name === 'compare' && (
                    <span className="stage__hint muted">срез — набор ответов одной версии СПР</span>
                  )}
                  <StatusBadge status={stage.status} error={runError} />
                  <span className="stage__times muted">
                    {stage.started_at === null
                      ? 'ещё не начинался'
                      : `начат ${formatTime(stage.started_at)} · ${formatDuration(
                          stage.started_at,
                          stage.finished_at,
                          clock,
                        )}`}
                  </span>
                </div>

                {active && (
                  <div className="stage__now">
                    <div>{STAGE_ACTIVE_TEXT[stage.name] ?? 'Выполняется…'}</div>
                    {run !== null && (
                      <ProgressBar done={run.progress.done} total={run.progress.total} />
                    )}
                  </div>
                )}

                {procedureId !== null && procedureId !== undefined && (
                  // Код этапа открывается в рабочей области процедур (E13), с прокруткой к строке.
                  <div className="stage__code">
                    <Link
                      to={codeLink(procedureId, stage.code_ref?.line)}
                      title="Код процедуры, которую исполнил этап"
                    >
                      Открыть код этапа →
                    </Link>
                  </div>
                )}

                {stage.procedures !== undefined && stage.procedures.length > 0 && (
                  // Этап «Проверки» исполняет несколько процедур — ссылка на код каждой.
                  <div className="stage__code">
                    Код проверок:{' '}
                    {stage.procedures.map((proc, index) => (
                      <span key={proc.id}>
                        {index > 0 && ' · '}
                        <Link to={codeLink(proc.id, 1)}>{proc.name}</Link>
                      </span>
                    ))}
                  </div>
                )}

                {stage.log.length > 0 ? (
                  <>
                    <button
                      type="button"
                      className="stage__toggle"
                      aria-expanded={isOpen}
                      onClick={() => toggle(stage)}
                    >
                      {isOpen ? 'Скрыть журнал' : `Журнал этапа (${stage.log.length})`}
                    </button>
                    {isOpen && <StageLog entries={stage.log} cancelled={cancelled || interrupted} />}
                  </>
                ) : (
                  <div className="stage__code faint">Записей журнала нет</div>
                )}
              </li>
            )
          })}
        </ol>
      )}

      {!finished && (
        <button type="button" className="btn log__refresh" onClick={reloadRun}>
          Обновить статус
        </button>
      )}
    </div>
  )
}

function StageLog({ entries, cancelled }: { entries: StageLogEntry[]; cancelled: boolean }) {
  return (
    <ol className="stage__log">
      {entries.map((entry, index) => {
        const look = levelLook(entry.level, cancelled)
        return (
          <li key={`${entry.at}-${index}`} className={`log-line log-line--${look.tone}`}>
            <span className="log-line__at mono">{formatTime(entry.at)}</span>
            <span className="log-line__level">
              <span className="log-line__icon" aria-hidden="true">
                {look.icon}
              </span>
              {look.label}
            </span>
            <span className="log-line__message">{entry.message}</span>
          </li>
        )
      })}
    </ol>
  )
}
