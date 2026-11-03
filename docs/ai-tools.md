# Плагины и скилы для ИИ

У кого-то Claude Code, у кого-то Codex — тут команды для обоих.
Ставим только официальное (Anthropic, OpenAI, проверенные разработчики). Непроверенные плагины не ставим:
это код, который ИИ выполняет на твоём ноуте.

Нужен Node.js (для `npx`).

---

## 1. Ставится само (ничего делать не надо)

Как только откроешь проект, ИИ сам подхватит:

| Что | Зачем |
|---|---|
| `AGENTS.md` / `CLAUDE.md` | инструкции по проекту: стек, правила, где API |
| **Context7** | свежая документация к библиотекам, чтобы ИИ не выдумывал по старой памяти |
| **Playwright** | ИИ сам открывает сайт в браузере, кликает и проверяет |

Claude при первом запуске спросит, можно ли включить MCP-серверы из `.mcp.json` — разреши.
Codex спросит, доверяешь ли проекту — ответь «да», иначе настройки из `.codex/config.toml` не включатся.

Проверить: в Claude — команда `/mcp`, в Codex — `codex mcp list`.

---

## 2. Ставим руками — по ролям

### Все

| Что | Claude Code | Codex |
|---|---|---|
| Защита от дырявого кода | `/plugin install security-guidance@claude-plugins-official` | `$skill-installer security-best-practices` |

### Фронт

| Что | Claude Code | Codex |
|---|---|---|
| Красивый UI | `/plugin install frontend-design@claude-plugins-official` | `$skill-installer install https://github.com/anthropics/skills/tree/main/skills/frontend-design` |
| Проверка сайта, скриншоты | `npx skills add anthropics/skills@webapp-testing` | `$skill-installer install https://github.com/anthropics/skills/tree/main/skills/webapp-testing` |
| Ошибки TypeScript сразу | `/plugin install typescript-lsp@claude-plugins-official` | — |
| Скриншоты для проверки вида | — | `$skill-installer screenshot` |

### Бэк

| Что | Claude Code | Codex |
|---|---|---|
| Ошибки Python сразу | `/plugin install pyright-lsp@claude-plugins-official` | — |

### Капитан

| Что | Claude Code | Codex |
|---|---|---|
| Коммиты и PR одной командой | `/plugin install commit-commands@claude-plugins-official` | — |
| Проверка PR перед Merge | `/plugin install code-review@claude-plugins-official` | `$skill-installer gh-address-comments` |

---

## Если что-то не ставится

- **Claude не знает `claude-plugins-official`** → сначала `/plugin marketplace add anthropics/claude-plugins-official`.
- **Codex не видит новый скил** → перезапусти Codex.
- **`npx: command not found`** → не установлен Node.js.

## Не ставим

- `ralph-loop` — крутит одну задачу по кругу и сжигает лимиты.
- Сборники «100 скилов в одном» от неизвестных авторов.
- Всё про деплой — нам не нужно, показываем с ноута.
