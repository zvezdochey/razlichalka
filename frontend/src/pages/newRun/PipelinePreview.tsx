/** Этапы обработки. В MVP все три — встроенные процедуры, выбирать нечего. */
const STEPS = [
  {
    title: 'Приведение ответов',
    description: 'Разворачивает JSON ответа СПР в плоские строки витрины.',
  },
  {
    title: 'Сравнение',
    description: 'Сводит срезы BEFORE и AFTER и помечает различия.',
  },
  {
    title: 'Факты',
    description: 'Считает агрегаты для обзора и сводной.',
  },
]

/**
 * Секции «Обработка» и «Проверки». В MVP не работают, но показаны честно:
 * видно, что будет происходить, и видно, что настройки появятся позже.
 */
export function PipelinePreview() {
  return (
    <>
      <section className="panel section section--later" aria-labelledby="section-pipeline">
        <h2 id="section-pipeline">Обработка</h2>
        <p className="section__note muted">
          Процедуры встроенные. Свой код — рабочей областью или файлом <code>.py</code> —
          подключим позже.
        </p>

        <ul className="steps">
          {STEPS.map((step) => (
            <li key={step.title} className="steps__item">
              <div className="steps__main">
                <span className="steps__title">{step.title}</span>
                <span className="muted">{step.description}</span>
              </div>
              <div className="steps__right">
                <span className="chip">Встроенная процедура</span>
                <span className="segmented" aria-label={`Источник кода: ${step.title}`}>
                  <button type="button" className="btn segmented__btn" disabled>
                    Рабочая область
                  </button>
                  <button type="button" className="btn segmented__btn" disabled>
                    Файл .py
                  </button>
                  <span className="chip">скоро</span>
                </span>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel section section--later" aria-labelledby="section-checks">
        <h2 id="section-checks">Проверки</h2>
        <p className="section__note muted">
          Проверки подключатся позже. Прогон считается без них — отчёт PASS / FAIL появится,
          когда наборы проверок будут готовы.
        </p>
      </section>
    </>
  )
}
