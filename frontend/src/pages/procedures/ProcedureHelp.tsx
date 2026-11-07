import type { ProcedureKind } from '../../api'

/**
 * Сворачиваемая справка рядом с редактором (DESIGN.md п. 4). Для проверки — контракт
 * из `checks/README.md` организаторов. Для остальных видов — то, как устроены наши
 * встроенные процедуры, без выдуманных сигнатур.
 */
export function ProcedureHelp({ kind }: { kind: ProcedureKind }) {
  return (
    <details className="proc-help panel">
      <summary>Справка: {kind === 'check' ? 'как написать проверку' : 'что в этой процедуре'}</summary>
      {kind === 'check' ? <CheckHelp /> : <DataProcedureHelp kind={kind} />}
    </details>
  )
}

function CheckHelp() {
  return (
    <div className="proc-help__body">
      <p>
        Файл проверки объявляет объект <code>CHECK</code> и функцию, которая получает витрину
        сравнения и параметры, а возвращает список строк результата.
      </p>
      <pre className="proc-help__code mono">{`CHECK = {
    "id": "ar_drop_by_product",   # уникальный идентификатор
    "label": "AR по продукту упал", # что видит пользователь
    "params": {"max_drop_rel": 0.10},
    "entrypoint": run,
}

def run(mart, params) -> list[dict]:
    ...`}</pre>

      <h3>Поля строки результата</h3>
      <dl className="proc-help__fields">
        <dt>LABEL</dt>
        <dd>название проверки</dd>
        <dt>SOURCE</dt>
        <dd>
          <code>BEFORE</code> или <code>AFTER</code>; проверка, которая сравнивает срезы, пишет{' '}
          <code>AFTER</code>
        </dd>
        <dt>ARGUMENT</dt>
        <dd>предмет проверки: продукт, скоркарта, атрибут, стоп-фактор</dd>
        <dt>CNT / TOTAL</dt>
        <dd>сколько заявок попало и от какой базы</dd>
        <dt>METRIC</dt>
        <dd>числовая метрика: доля, разница, значение</dd>
        <dt>APP_IDS</dt>
        <dd>
          заявки, не больше <code>params["app_ids_limit"]</code>
        </dd>
        <dt>RESULT</dt>
        <dd>
          <code>PASS</code> или <code>FAIL</code>
        </dd>
        <dt>CONFIDENCE</dt>
        <dd>
          <code>LOW</code>, если срабатываний меньше <code>params["low_confidence_cnt"]</code> —
          строка в отчёте будет бледной
        </dd>
      </dl>

      <h3>Методы витрины</h3>
      <dl className="proc-help__fields">
        <dt>mart.rows(**filters)</dt>
        <dd>строки витрины сравнения</dd>
        <dt>mart.count(**filters)</dt>
        <dd>сколько строк</dd>
        <dt>mart.app_ids(**filters)</dt>
        <dd>уникальные APP_ID, по порядку</dd>
        <dt>mart.segments()</dt>
        <dd>разрезы, строка на заявку</dd>
        <dt>mart.total_apps()</dt>
        <dd>всего заявок в прогоне</dd>
      </dl>
      <p className="muted">
        Фильтры (все необязательны, через И): <code>path</code>, <code>path_prefix</code>,{' '}
        <code>key</code>, <code>array_key</code>, <code>diff_flag</code>, <code>change_type</code>,{' '}
        <code>value_before</code>, <code>value_after</code>, <code>app_ids</code>.
      </p>
      <p className="muted">
        Проверка, которая упала с ошибкой, прогон не валит: в отчёте она строкой «Не
        выполнилась», подробности — в журнале этапа «Проверки».
      </p>
    </div>
  )
}

function DataProcedureHelp({ kind }: { kind: Exclude<ProcedureKind, 'check'> }) {
  if (kind === 'compare') {
    return (
      <div className="proc-help__body">
        <p>
          Процедура объявляет <code>COMPARE</code> с функцией, которая получает две плоские таблицы
          (pandas.DataFrame) — строки BEFORE и AFTER — и возвращает витрину сравнения.
        </p>
        <pre className="proc-help__code mono">{`def compare(before, after):
    ...  # колонки входа: APP_ID, PREFIX, CLASS, SUFFIX, ARRAY_KEY, KEY, PATH, VALUE, ADJUSTED_VALUE
    return out  # APP_ID … PATH, VALUE_BEFORE, VALUE_AFTER, ADJUSTED_BEFORE, ADJUSTED_AFTER, CHANGE_TYPE

COMPARE = {"label": "Моё сравнение", "entrypoint": compare}`}</pre>
        <p className="muted">
          <code>CHANGE_TYPE</code> — <code>SAME</code>, <code>VALUE_CHANGED</code>,{' '}
          <code>ATTRIBUTE_NEW</code> или <code>ATTRIBUTE_LOST</code>; <code>DIFF_FLAG</code> приложение
          ставит само. Своя процедура исполняется в отдельном процессе; если результат не по
          контракту, прогон остановится с понятной ошибкой.
        </p>
      </div>
    )
  }
  return (
    <div className="proc-help__body">
      {kind === 'normalize' ? (
        <p>
          Правила сопоставления массивов между срезами: словарь <code>ARRAY_RULES</code>, где для
          каждого массива указан режим — <code>key</code> (по полям из <code>key</code>),{' '}
          <code>value</code> (по значению) или <code>index</code> (по позиции). Рядом —{' '}
          <code>BUCKETS</code> (границы диапазонов для сравнения и сводной по бакетам) и{' '}
          <code>ID_PATH</code> (где в ответе id заявки).
        </p>
      ) : (
        <p>
          Факты (подсчёты) опираются на карту полей для разрезов: <code>FIELD_MAP</code> — для каждого поля
          разреза путь в JSON-ответе, массив помечается <code>[]</code>. Здесь же{' '}
          <code>INPUT_PREFIXES</code> — какие пути считаются входом, а не логикой.
        </p>
      )}
      <p className="muted">
        Код процедуры исполняется в отдельном процессе, разбор берёт из него эти переменные. Скопируйте
        встроенную процедуру, поправьте и выберите копию в форме «Новый прогон» → «Как считаем». На
        один прогон правило массива можно перекрыть и в конфигурации (<code>array_rules</code>,{' '}
        <code>array_modes</code>).
      </p>
    </div>
  )
}
