import { useEffect, useMemo, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  ApiRequestError,
  createProcedure,
  deleteProcedure,
  getProcedure,
  isAbortError,
  listProcedures,
  updateProcedure,
  validateProcedure,
} from '../api'
import type { CodeError, CodeSource, Procedure, ProcedureInput, ProcedureKind } from '../api'
import { EmptyState, ErrorBox, Spinner } from '../components'
import { setLeaveGuard } from '../lib/leaveGuard'
import { CodeEditor } from './procedures/CodeEditor'
import type { CodeEditorHandle } from './procedures/CodeEditor'
import { ProcedureHelp } from './procedures/ProcedureHelp'
import { RunWithCheck } from './procedures/RunWithCheck'
import { KIND_NAMES, KIND_ORDER, KIND_TITLES, markCheckAsCopy, newCheckTemplate } from './procedures/templates'
import './procedures/ProceduresPage.css'

/** То, что сейчас в редакторе. `id: null` — ещё не сохранена. */
type Draft = {
  id: string | null
  kind: ProcedureKind
  name: string
  source: CodeSource
  /** Код держим и для файла: при переключении на «Рабочую область» он станет начальным текстом. */
  code: string
  path: string
  builtin: boolean
}

/** Что сравниваем, чтобы понять «есть несохранённые изменения». */
function snapshot(draft: Draft): string {
  return JSON.stringify([draft.name, draft.source, draft.source === 'inline' ? draft.code : draft.path])
}

/** Тело на сохранение: для рабочей области — код, для файла — путь. */
function toInput(draft: Draft): ProcedureInput {
  const base = { kind: draft.kind, name: draft.name.trim(), source: draft.source }
  return draft.source === 'inline' ? { ...base, code: draft.code } : { ...base, path: draft.path.trim() }
}

/** `bad_code` с бэка приходит текстом «Строка N: причина» — разбираем в ту же форму, что у проверки. */
function parseBadCode(message: string): CodeError | null {
  const match = /^Строка (\d+):\s*(.*)$/s.exec(message)
  return match === null ? null : { line: Number(match[1]), message: match[2] }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Запрос не удался'
}

const LEAVE_QUESTION = 'Есть несохранённые изменения. Уйти без сохранения?'

type Busy = 'idle' | 'loading' | 'checking' | 'saving' | 'deleting'

/**
 * Рабочая область процедур (DESIGN.md п. 4, задача E13). Слева — список по видам,
 * справа — редактор. Что открыто, лежит в URL: `?id=<процедура>&line=<строка>` (так
 * ведёт ссылка «код этапа» из журнала), `?new=check` — новая проверка из шаблона,
 * `?copy=<id>` — копия встроенной процедуры или проверки в рабочую область.
 */
export function ProceduresPage() {
  const [params, setParams] = useSearchParams()
  const openId = params.get('id')
  const copyId = params.get('copy')
  const isNew = params.get('new') === 'check'
  const lineParam = Number(params.get('line'))
  const targetLine = openId !== null && Number.isInteger(lineParam) && lineParam > 0 ? lineParam : null

  // ─── Список процедур ──────────────────────────────────────────────────────
  const [list, setList] = useState<Procedure[] | null>(null)
  const [listError, setListError] = useState<string | null>(null)
  const [listKey, setListKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    listProcedures(undefined, { signal: controller.signal })
      .then((items) => {
        setList(items)
        setListError(null)
      })
      .catch((e: unknown) => {
        if (isAbortError(e)) return
        setListError(errorMessage(e))
      })
    return () => controller.abort()
  }, [listKey])

  // ─── Открытая процедура ───────────────────────────────────────────────────
  const [draft, setDraft] = useState<Draft | null>(null)
  const [saved, setSaved] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busy, setBusy] = useState<Busy>('idle')
  // Результат последней проверки: null — не проверяли или код с тех пор правили.
  const [codeErrors, setCodeErrors] = useState<CodeError[] | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const editor = useRef<CodeEditorHandle>(null)

  // Открыть то, что указано в URL: загрузка с бэка и есть синхронизация с внешней системой.
  useEffect(() => {
    // eslint-disable-next-line react/set-state-in-effect -- сброс прошлой процедуры перед загрузкой новой
    setCodeErrors(null)
    setActionError(null)
    setLoadError(null)

    if (isNew) {
      setDraft({
        id: null,
        kind: 'check',
        name: 'Моя проверка',
        source: 'inline',
        code: newCheckTemplate(),
        path: '',
        builtin: false,
      })
      setSaved(null)
      return
    }

    const id = openId ?? copyId
    if (id === null) {
      setDraft(null)
      setSaved(null)
      return
    }

    const controller = new AbortController()
    setBusy('loading')
    getProcedure(id, { signal: controller.signal })
      .then((proc) => {
        const loaded: Draft = {
          id: proc.id,
          kind: proc.kind,
          name: proc.name,
          source: proc.source,
          code: proc.code,
          path: proc.path ?? '',
          builtin: proc.builtin,
        }
        if (copyId !== null && openId === null) {
          // Копия — уже своя, несохранённая процедура в рабочей области.
          setDraft({
            ...loaded,
            id: null,
            name: `${proc.name} (копия)`,
            source: 'inline',
            // У проверки в копии меняем CHECK.id, чтобы она не совпала со встроенной
            code: loaded.kind === 'check' ? markCheckAsCopy(loaded.code) : loaded.code,
            path: '',
            builtin: false,
          })
          setSaved(null)
        } else {
          setDraft(loaded)
          setSaved(snapshot(loaded))
        }
        setBusy('idle')
      })
      .catch((e: unknown) => {
        if (isAbortError(e)) return
        setDraft(null)
        setLoadError(errorMessage(e))
        setBusy('idle')
      })
    return () => controller.abort()
  }, [openId, copyId, isNew])

  // Пришли по ссылке из журнала — прокручиваем к строке этапа, когда код уже на месте.
  const loadedId = draft?.id ?? null
  useEffect(() => {
    if (targetLine !== null && loadedId !== null && loadedId === openId) {
      editor.current?.scrollToLine(targetLine)
    }
  }, [targetLine, loadedId, openId])

  const dirty = draft !== null && !draft.builtin && snapshot(draft) !== saved

  // Закрыть вкладку с несохранённым кодом браузер не даст без вопроса.
  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => event.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  // Ссылки меню тоже спрашивают, пока есть несохранённое (useBlocker с BrowserRouter не работает).
  useEffect(() => {
    setLeaveGuard(dirty ? LEAVE_QUESTION : null)
    return () => setLeaveGuard(null)
  }, [dirty])

  const errorLines = useMemo(() => new Set((codeErrors ?? []).map((e) => e.line)), [codeErrors])

  /** Переход к другой процедуре: несохранённое не теряем молча. */
  function open(next: Record<string, string>) {
    if (dirty && !window.confirm(LEAVE_QUESTION)) return
    setParams(next)
  }

  function edit(patch: Partial<Draft>) {
    setDraft((current) => (current === null ? current : { ...current, ...patch }))
    // Строки сдвинулись — старая подсветка ошибок врёт, её убираем.
    if ('code' in patch || 'source' in patch || 'path' in patch) setCodeErrors(null)
    setActionError(null)
  }

  async function handleValidate() {
    if (draft === null || busy !== 'idle') return
    setBusy('checking')
    setActionError(null)
    try {
      const { name: _name, ...input } = toInput(draft)
      const res = await validateProcedure(input)
      setCodeErrors(res.errors)
      const first = res.errors[0]
      if (first !== undefined) editor.current?.scrollToLine(first.line)
    } catch (e) {
      setActionError(errorMessage(e))
    } finally {
      setBusy('idle')
    }
  }

  async function handleSave() {
    if (draft === null || draft.builtin || busy !== 'idle') return
    setBusy('saving')
    setActionError(null)
    try {
      const input = toInput(draft)
      // Запоминаем то, что реально ушло на сервер: правка, сделанная пока шёл запрос,
      // не должна считаться сохранённой.
      const sent = snapshot(draft)
      const proc = draft.id === null ? await createProcedure(input) : await updateProcedure(draft.id, input)
      setCodeErrors(null)
      setListKey((key) => key + 1)
      if (draft.id === null) {
        // Новую открываем по id: эффект перечитает её с бэка (для файла — уже с кодом).
        setSaved(sent)
        setParams({ id: proc.id }, { replace: true })
      } else {
        setSaved(sent)
      }
    } catch (e) {
      // Ошибка контракта показывается так же, как результат «Проверить».
      const parsed = e instanceof ApiRequestError && e.code === 'bad_code' ? parseBadCode(e.message) : null
      if (parsed !== null) {
        setCodeErrors([parsed])
        editor.current?.scrollToLine(parsed.line)
      } else {
        setActionError(errorMessage(e))
      }
    } finally {
      setBusy('idle')
    }
  }

  async function handleDelete() {
    if (draft === null || draft.id === null || draft.builtin || busy !== 'idle') return
    const question =
      `Удалить «${draft.name}»? Если проверка подключена к конфигурациям, в них останется ` +
      'id несуществующей процедуры: новые прогоны по ним её молча пропустят. ' +
      'Уже посчитанные прогоны останутся.'
    if (!window.confirm(question)) return
    setBusy('deleting')
    try {
      await deleteProcedure(draft.id)
      setSaved(null)
      setDraft(null)
      setListKey((key) => key + 1)
      setParams({}, { replace: true })
    } catch (e) {
      setActionError(errorMessage(e))
    } finally {
      setBusy('idle')
    }
  }

  const selectedId = isNew || copyId !== null ? null : openId

  return (
    <div className="procs">
      <div className="page-head">
        <h1>Процедуры</h1>
        <button type="button" className="btn" onClick={() => open({ new: 'check' })}>
          Новая проверка
        </button>
      </div>

      <p className="muted">
        Процедура — это кусок логики: шаг обработки (приведение, сравнение, факты) или проверка. Для
        обычной работы менять их не нужно. Чтобы заменить шаг, скопируйте встроенную процедуру в
        рабочую область, поправьте и выберите копию в форме «Новый прогон».
      </p>

      <div className="procs__layout">
        <nav className="procs__list panel" aria-label="Процедуры">
          {listError !== null && <ErrorBox message={listError} onRetry={() => setListKey((k) => k + 1)} />}
          {list === null && listError === null && <Spinner label="Читаем процедуры" />}
          {list !== null &&
            KIND_ORDER.map((kind) => {
              const items = list.filter((proc) => proc.kind === kind)
              if (items.length === 0) return null
              return (
                <section key={kind} className="procs__group">
                  <h2 className="overline">{KIND_TITLES[kind]}</h2>
                  <ul>
                    {items.map((proc) => (
                      <li key={proc.id}>
                        <Link
                          to={`?id=${encodeURIComponent(proc.id)}`}
                          className={`procs__item${proc.id === selectedId ? ' procs__item--active' : ''}`}
                          aria-current={proc.id === selectedId ? 'page' : undefined}
                          onClick={(event) => {
                            event.preventDefault()
                            if (proc.id !== selectedId) open({ id: proc.id })
                          }}
                        >
                          <span className="procs__name">{proc.name}</span>
                          <span className="procs__meta">
                            {proc.builtin && <span className="chip">встроенная</span>}
                            <span className="faint">{proc.source === 'file' ? 'файл' : 'рабочая область'}</span>
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </section>
              )
            })}
        </nav>

        <div className="procs__main">
          {loadError !== null && <ErrorBox message={loadError} />}
          {busy === 'loading' && draft === null && (
            <div className="panel">
              <Spinner label="Открываем код" />
            </div>
          )}
          {draft === null && busy !== 'loading' && loadError === null && (
            <EmptyState
              title="Выберите процедуру в списке"
              hint="Встроенные открываются на чтение. Свою проверку можно написать с шаблона."
              action={
                <button type="button" className="btn" onClick={() => open({ new: 'check' })}>
                  Новая проверка
                </button>
              }
            />
          )}
          {draft !== null && (
            <Workspace
              draft={draft}
              dirty={dirty}
              busy={busy}
              codeErrors={codeErrors}
              actionError={actionError}
              errorLines={errorLines}
              targetLine={draft.id === openId ? targetLine : null}
              editorRef={editor}
              onEdit={edit}
              onValidate={() => void handleValidate()}
              onSave={() => void handleSave()}
              onDelete={() => void handleDelete()}
              onCopy={() => draft.id !== null && open({ copy: draft.id })}
            />
          )}
        </div>
      </div>
    </div>
  )
}

type WorkspaceProps = {
  draft: Draft
  dirty: boolean
  busy: Busy
  codeErrors: CodeError[] | null
  actionError: string | null
  errorLines: ReadonlySet<number>
  targetLine: number | null
  editorRef: RefObject<CodeEditorHandle | null>
  onEdit: (patch: Partial<Draft>) => void
  onValidate: () => void
  onSave: () => void
  onDelete: () => void
  onCopy: () => void
}

/** Состояние кода словами (DESIGN.md п. 4): сохранено, не сохранено, идёт, ошибка. */
function statusText(draft: Draft, dirty: boolean, busy: Busy, codeErrors: CodeError[] | null): string {
  if (busy === 'checking') return 'Проверяем…'
  if (busy === 'saving') return 'Сохраняем…'
  if (busy === 'deleting') return 'Удаляем…'
  if (draft.builtin) return 'Только чтение'
  if (codeErrors !== null && codeErrors.length > 0) return 'Ошибка'
  if (draft.id === null) return 'Не сохранена'
  return dirty ? 'Есть несохранённые изменения' : 'Сохранено'
}

function Workspace({
  draft,
  dirty,
  busy,
  codeErrors,
  actionError,
  errorLines,
  targetLine,
  editorRef,
  onEdit,
  onValidate,
  onSave,
  onDelete,
  onCopy,
}: WorkspaceProps) {
  const readOnly = draft.builtin
  // Файл на сервере правят на сервере: здесь его только читают и проверяют.
  const codeReadOnly = readOnly || draft.source === 'file' || busy === 'saving'
  const locked = busy !== 'idle'
  const status = statusText(draft, dirty, busy, codeErrors)

  return (
    <>
      <section className="proc panel" aria-label="Редактор процедуры">
        <div className="proc__head">
          <label className="proc__field proc__field--name">
            <span className="overline">Название</span>
            <input
              className="input"
              value={draft.name}
              readOnly={readOnly || busy === 'saving'}
              onChange={(event) => onEdit({ name: event.target.value })}
            />
          </label>
          <div className="proc__field">
            <span className="overline">Вид</span>
            <span className="proc__kind">{KIND_NAMES[draft.kind]}</span>
          </div>
        </div>

        {draft.kind === 'check' && !readOnly && (
          <p className="faint proc__hint">
            Название — для списка процедур. В отчёте строка проверки подписывается из кода:{' '}
            <code>CHECK["label"]</code>.
          </p>
        )}

        {readOnly && (
          <div className="proc__note muted">
            Встроенная процедура — открыта только на чтение.
            <button type="button" className="btn" onClick={onCopy}>
              Копировать в рабочую область
            </button>
          </div>
        )}

        {readOnly ? (
          <p className="muted proc__hint">
            Встроенная, только чтение
            {draft.source === 'file' && <>. Файл на сервере: <code>{draft.path}</code></>}
          </p>
        ) : (
          <fieldset className="proc__source" disabled={locked}>
            <legend className="overline">Источник кода</legend>
            <label>
              <input
                type="radio"
                name="proc-source"
                checked={draft.source === 'inline'}
                onChange={() => onEdit({ source: 'inline' })}
              />
              Рабочая область
            </label>
            <label>
              <input
                type="radio"
                name="proc-source"
                checked={draft.source === 'file'}
                onChange={() => onEdit({ source: 'file' })}
              />
              Файл на сервере
            </label>
            {draft.source === 'file' && (
              <input
                className="input mono proc__path"
                aria-label="Путь к файлу на сервере"
                placeholder={draft.kind === 'check' ? 'checks/check_my.py' : 'procedures/my_procedure.py'}
                value={draft.path}
                onChange={(event) => onEdit({ path: event.target.value })}
              />
            )}
          </fieldset>
        )}

        {draft.source === 'file' && !readOnly && (
          <p className="faint proc__hint">
            Файл берётся из папок <code>procedures/</code> или <code>checks/</code> на сервере
            {draft.kind === 'compare' && <> (пример: <code>procedures/example_compare_by_bucket.py</code>)</>}. Код ниже —
            {draft.id === null ? ' появится после сохранения.' : ' последняя сохранённая версия файла.'}
          </p>
        )}

        <CodeEditor
          ref={editorRef}
          // У нового файла кода ещё нет: он придёт с сервера после сохранения.
          // Текст рабочей области при этом не теряется — вернётся при переключении обратно.
          value={draft.source === 'file' && draft.id === null ? '' : draft.code}
          onChange={(code) => onEdit({ code })}
          readOnly={codeReadOnly}
          errorLines={errorLines}
          targetLine={targetLine}
          label={`Код: ${draft.name}`}
        />
        {!codeReadOnly && <p className="faint proc__hint">Tab — 4 пробела. Выйти из поля: Esc, затем Tab.</p>}

        <div className="proc__actions">
          <button type="button" className="btn" disabled={locked} onClick={onValidate}>
            Проверить
          </button>
          {!readOnly && (
            <button type="button" className="btn btn--primary" disabled={locked || !dirty} onClick={onSave}>
              Сохранить
            </button>
          )}
          <span className="proc__status" aria-live="polite">
            {status}
          </span>
          {!readOnly && draft.id !== null && (
            <button type="button" className="btn proc__delete" disabled={locked} onClick={onDelete}>
              Удалить
            </button>
          )}
        </div>

        {actionError !== null && <ErrorBox message={actionError} />}

        {codeErrors !== null && codeErrors.length === 0 && (
          <p className="proc__ok">Проверка контракта пройдена: ошибок не нашли.</p>
        )}
        {codeErrors !== null && codeErrors.length > 0 && (
          <div className="proc__errors" role="alert">
            <div className="proc__errors-title">Код не проходит проверку контракта</div>
            <ul>
              {codeErrors.map((err, index) => (
                <li key={`${err.line}-${index}`}>
                  <button
                    type="button"
                    className="proc__error-line"
                    onClick={() => editorRef.current?.scrollToLine(err.line)}
                  >
                    строка {err.line}: {err.message}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      {draft.kind === 'check' && draft.id !== null && (
        <RunWithCheck
          procedureId={draft.id}
          blockedReason={dirty ? 'Сначала сохраните изменения' : null}
        />
      )}

      <ProcedureHelp kind={draft.kind} />
    </>
  )
}
