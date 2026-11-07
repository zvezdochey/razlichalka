// Вопрос «уйти без сохранения?» для ссылок вне страницы. Роутер у нас BrowserRouter,
// а `useBlocker` работает только с data-роутером, поэтому страница с несохранённой
// работой кладёт сюда вопрос, а ссылки меню спрашивают перед переходом.

let question: string | null = null

/** Страница ставит вопрос, пока есть несохранённое, и `null`, когда всё сохранено. */
export function setLeaveGuard(next: string | null): void {
  question = next
}

/** `true` — можно уходить: либо нечего терять, либо человек согласился. */
export function confirmLeave(): boolean {
  return question === null || window.confirm(question)
}
