# Плагины и скилы для ИИ: кому что ставить

Найди свой раздел, потом свой ИИ (Claude или Codex), и пройди по галочкам:

| Кто | Раздел |
|---|---|
| Стёпа | 1. Бэк |
| Саня | 2. Фронт |
| Семён | 3. Капитан |
| Илья | 1. Бэк **и** 2. Фронт — ставит оба, чтобы помогать любой стороне |

Раздел 0 — для всех.

Ставим только официальное (Anthropic, OpenAI, проверенные разработчики). Непроверенные плагины не ставим:
это код, который ИИ выполняет на твоём ноуте.

---

## 0. Сначала всем

- [ ] Установлен **Node.js 20+** — проверь: `node -v`. Без него не заработают Context7 и Playwright.
- [ ] Открыл проект в своём ИИ и **разрешил настройки проекта**:
  - Claude спросит, можно ли включить серверы из `.mcp.json` → **да**.
  - Codex спросит, доверяешь ли проекту → **да**.
- [ ] Проверил, что подключились **Context7** и **Playwright**:
  - Claude: команда `/mcp`
  - Codex: `codex mcp list`

Это ставится само для всех, руками ничего не надо:

| Что | Зачем |
|---|---|
| `AGENTS.md` / `CLAUDE.md` | инструкции по проекту: стек, правила, где API |
| **Context7** | свежая документация к библиотекам, чтобы ИИ не выдумывал по старой памяти |
| **Playwright** | ИИ сам открывает сайт в браузере, кликает и проверяет |

---

## 1. Бэк

### Claude Code

- [ ] `/plugin install pyright-lsp@claude-plugins-official` — ИИ сразу видит ошибки в Python
- [ ] `/plugin install security-guidance@claude-plugins-official` — предупреждает про дырявый код

### Codex

- [ ] `$skill-installer security-best-practices` — проверка кода на уязвимости

---

## 2. Фронт

### Claude Code

- [ ] `/plugin install frontend-design@claude-plugins-official` — красивый UI, а не шаблонный
- [ ] `npx skills add anthropics/skills@webapp-testing` — запускает сайт, делает скриншоты, смотрит ошибки
- [ ] `/plugin install typescript-lsp@claude-plugins-official` — ИИ сразу видит ошибки TypeScript
- [ ] `/plugin install security-guidance@claude-plugins-official` — предупреждает про дырявый код

### Codex

- [ ] `$skill-installer install https://github.com/anthropics/skills/tree/main/skills/frontend-design` — красивый UI
- [ ] `$skill-installer install https://github.com/anthropics/skills/tree/main/skills/webapp-testing` — проверка сайта
- [ ] `$skill-installer screenshot` — скриншоты для проверки вида
- [ ] `$skill-installer security-best-practices` — проверка кода на уязвимости

---

## 3. Капитан

Капитан сливает всё в `main`, проверяет чужой код и делает презентацию.

### Claude Code

- [ ] `/plugin install code-review@claude-plugins-official` — проверка Pull Request перед тем, как жать Merge
- [ ] `/plugin install commit-commands@claude-plugins-official` — коммиты и Pull Request одной командой
- [ ] `npx skills add anthropics/skills@pptx` — слайды для защиты
- [ ] `/plugin install security-guidance@claude-plugins-official` — предупреждает про дырявый код

### Codex

- [ ] Проверка Pull Request уже встроена — команда `/review`, ставить ничего не надо
- [ ] `$skill-installer gh-address-comments` — разбирает замечания в Pull Request
- [ ] `$skill-installer install https://github.com/anthropics/skills/tree/main/skills/pptx` — слайды для защиты
- [ ] `$skill-installer security-best-practices` — проверка кода на уязвимости

---

## Если что-то не ставится

- **Claude не знает `claude-plugins-official`** → сначала `/plugin marketplace add anthropics/claude-plugins-official`.
- **Codex не видит новый скил** → перезапусти Codex.
- **`npx: command not found`** → не установлен Node.js.

## Не ставим

- `ralph-loop` — крутит одну задачу по кругу и сжигает лимиты.
- Сборники «100 скилов в одном» от неизвестных авторов.
- Всё про деплой — нам не нужно, показываем с ноута.
