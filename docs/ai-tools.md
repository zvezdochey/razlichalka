# Плагины и скилы для ИИ: кому что ставить

Найди своё имя и пройди по галочкам. Раздел 0 — для всех.

| Кто | Роль | ИИ |
|---|---|---|
| Семён | капитан | Claude Code |
| Саня | фронт | Claude Code |
| Стёпа | бэк | Codex |
| Илья | бэк + фронт | Codex |

Ставим только официальное (Anthropic, OpenAI) и скилы набора superpowers от obra (MIT) — его мы проверили. Непроверенные плагины не ставим:
это код, который ИИ выполняет на твоём ноуте.

---

## 0. Всем

- [ ] Установлен **Node.js 20+** — проверь: `node -v`. Без него не заработают Context7 и Playwright.
- [ ] Открыл проект в своём ИИ и **разрешил настройки проекта**:
  - Claude спросит, можно ли включить серверы из `.mcp.json` → **да**.
  - Codex спросит, доверяешь ли проекту → **да**.
- [ ] Проверил, что подключились **Context7** и **Playwright**:
  - Claude: команда `/mcp`
  - Codex: `codex mcp list`

Это ставится само, руками ничего не надо:

| Что | Зачем |
|---|---|
| `AGENTS.md` / `CLAUDE.md` | инструкции по проекту: стек, правила, где API |
| **Context7** | свежая документация к библиотекам, чтобы ИИ не выдумывал по старой памяти |
| **Playwright** | ИИ сам открывает сайт в браузере, кликает и проверяет |

И ещё один скил всем — для ночной отладки:

- [ ] **systematic-debugging** — ИИ ищет настоящую причину бага, а не латает симптом.
  Автор — obra (набор superpowers, лицензия MIT).
  - Claude: `npx skills add obra/superpowers@systematic-debugging`
  - Codex: `$skill-installer install https://github.com/obra/superpowers/tree/main/skills/systematic-debugging`

---

## Семён — капитан, Claude Code

- [ ] `npx skills add obra/superpowers@brainstorming` — превращает сырую идею в план через вопросы.
  Нужен 6-го после постановки задачи. **Только капитану:** скил включается перед любой новой работой
  и задаёт кучу вопросов — у тех, кто пишет код, он будет тормозить каждую мелочь.
- [ ] `/plugin install code-review@claude-plugins-official` — проверка Pull Request перед тем, как жать Merge
- [ ] `/plugin install commit-commands@claude-plugins-official` — коммиты и Pull Request одной командой
- [ ] `npx skills add anthropics/skills@pptx` — слайды для защиты
- [ ] `/plugin install security-guidance@claude-plugins-official` — предупреждает про дырявый код

## Саня — фронт, Claude Code

- [ ] `/plugin install frontend-design@claude-plugins-official` — красивый UI, а не шаблонный
- [ ] `npx skills add anthropics/skills@webapp-testing` — запускает сайт, делает скриншоты, смотрит ошибки
- [ ] `/plugin install typescript-lsp@claude-plugins-official` — ИИ сразу видит ошибки TypeScript
- [ ] `/plugin install security-guidance@claude-plugins-official` — предупреждает про дырявый код

## Стёпа — бэк, Codex

- [ ] `$skill-installer security-best-practices` — проверка кода на уязвимости

## Илья — бэк + фронт, Codex

Ставит всё, чтобы помогать любой стороне:

- [ ] `$skill-installer security-best-practices` — проверка кода на уязвимости
- [ ] `$skill-installer install https://github.com/anthropics/skills/tree/main/skills/frontend-design` — красивый UI
- [ ] `$skill-installer install https://github.com/anthropics/skills/tree/main/skills/webapp-testing` — проверка сайта
- [ ] `$skill-installer screenshot` — скриншоты для проверки вида

Проверка Pull Request в Codex уже встроена — команда `/review`. Пригодится, когда проверяешь вместе с капитаном.

---

## Если что-то не ставится

- **Claude не знает `claude-plugins-official`** → сначала `/plugin marketplace add anthropics/claude-plugins-official`.
- **Codex не видит новый скил** → перезапусти Codex.
- **Codex не показывает Context7/Playwright** → ты отказал проекту в доверии. Запусти Codex заново в папке проекта и ответь «да» на вопрос о доверии.
- **`npx: command not found`** → не установлен Node.js.

## Не ставим

- `ralph-loop` — крутит одну задачу по кругу и сжигает лимиты.
- Сборники «100 скилов в одном» от неизвестных авторов.
- Всё про деплой — нам не нужно, показываем с ноута.
