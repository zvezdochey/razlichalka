# Сабагенты бэка

Устроено так же, как у фронта (см. `docs/frontend/agents.md`): каждый агент работает в своём
контексте и возвращает в основную сессию только итог. Файлы лежат в `docs/backend/сабагенты/`,
а `.claude/agents/back` — симлинк на эту папку, чтобы Claude Code их находил.

> Это агенты для **Claude Code**. Codex (Стёпа и Илья по `docs/ai-tools.md`) их не читает,
> для него эти файлы можно открыть и использовать как готовые подсказки.

## Порядок вызова

Обычный цикл на одну ручку (одну ветку `back/...`):

```
fastapi-coder  →  api-tester  →  code-reviewer-back  →  PR
```

Перед крупными развилками добавляется шаг в начале:

```
planner-back  →  fastapi-coder  →  api-tester  →  code-reviewer-back  →  PR
```

| Агент | Файл | Что делает | Инструменты |
|---|---|---|---|
| **`planner-back`** | `planner-back.md` | Разбивает крупную задачу (загрузка, нормализация, расчёт причин) на шаги/ветки, без кода | Read, Grep, Glob |
| **`fastapi-coder`** | `fastapi-coder.md` | Пишет ручку или логику строго по `docs/api.md`, ошибки в едином формате | Read, Write, Edit, Bash, Grep, Glob |
| **`api-tester`** | `api-tester.md` | Запускает бэк и сверяет живые ответы с `docs/api.md`: поля, словари, коды, ошибки | Read, Bash, Grep, Glob |
| **`code-reviewer-back`** | `code-reviewer-back.md` | Проверяет диф перед PR (`git fetch && git diff origin/main...HEAD`): контракт, загрузка файлов, безопасность | Read, Grep, Glob, Bash |

## Чем отличается от фронта

- Нет `ui-designer`: у бэка нет визуала.
- `api-tester` вместо `browser-tester`: вместо браузера — реальные запросы к ручкам.
- `code-reviewer-back` смотрит на загрузку файлов (размер, формат, имя файла) и на SQL,
  потому что бэк принимает файлы от пользователя.
- Имена агентов не пересекаются с фронтовыми (`planner-back`, а не `planner`): Claude Code
  загружает только один из двух агентов с одинаковым именем.
