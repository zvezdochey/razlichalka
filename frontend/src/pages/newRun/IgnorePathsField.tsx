import { useState } from 'react'

type IgnorePathsFieldProps = {
  paths: string[]
  onChange: (paths: string[]) => void
}

/**
 * Список «Не сравнивать» (`ignore_paths`). Предзаполнен техническими полями
 * датасета, пользователь может убрать путь или дописать свой текстом.
 */
export function IgnorePathsField({ paths, onChange }: IgnorePathsFieldProps) {
  const [draft, setDraft] = useState('')
  const trimmed = draft.trim()

  function add() {
    if (trimmed === '') return
    // Дубль пути бэку ничего не ломает, но в списке выглядит как ошибка ввода.
    if (!paths.includes(trimmed)) onChange([...paths, trimmed])
    setDraft('')
  }

  return (
    <div className="field">
      <span className="field__label" id="ignore-paths-label">
        Не сравнивать
      </span>
      <p className="field__hint muted">
        Технические поля датасета различаются у всех заявок — без них в отчёте будет шум.
        Можно убрать лишнее или дописать свой путь.
      </p>

      {paths.length === 0 ? (
        <p className="muted">Сравниваем все поля.</p>
      ) : (
        <ul className="paths" aria-labelledby="ignore-paths-label">
          {paths.map((path) => (
            <li key={path} className="paths__item">
              <span className="mono">{path}</span>
              <button
                type="button"
                className="paths__remove"
                onClick={() => onChange(paths.filter((item) => item !== path))}
              >
                Убрать<span className="visually-hidden"> путь {path}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="paths__add">
        <input
          type="text"
          className="input mono paths__input"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          // Enter здесь добавляет путь, а не отправляет форму на запуск прогона.
          onKeyDown={(event) => {
            if (event.key !== 'Enter') return
            event.preventDefault()
            add()
          }}
          placeholder="appData.createDateTime"
          aria-label="Путь, который не сравнивать"
        />
        <button type="button" className="btn" onClick={add} disabled={trimmed === ''}>
          Добавить
        </button>
      </div>
    </div>
  )
}
