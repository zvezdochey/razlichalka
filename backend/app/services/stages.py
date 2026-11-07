"""Настоящие этапы запуска (S5): вызываем функции из `pipeline/` (CONTRACTS §4).

У каждого этапа тот же интерфейс `(ctx) -> None`, что и у заглушек в `app/pipeline_stub.py`.
Ошибки `PipelineError` (в том числе `Cancelled`) наверх не обрабатываем: их превращает в
`{code, message}` менеджер этапов в `services/runs.py`.
"""
import json
import os
from pathlib import Path

from pipeline.checks_runner import load_check, run_checks, write_checks_csv
from pipeline.compare import compare_csv
from pipeline.dataset import list_source_files
from pipeline.errors import BadFile
from pipeline.mart import Mart
from pipeline.normalize import normalize_dataset
from pipeline.procedures import load_builtin_value
from pipeline.union import build_union
from pipeline.user_procedures import load_constants, run_compare, write_data_procedure
from pipeline.segments import build_segments, segment_field_map
from pipeline.summary import build_summary

from app import settings, store
from app.errors import ApiError
from app.services import app_card, procedures

# Имена файлов запуска — CONTRACTS §3
NORMALIZED = {"BEFORE": "normalized_BEFORE.csv", "AFTER": "normalized_AFTER.csv"}
COMPARISON = "comparison.csv"
UNION = "union.csv"  # вертикальная витрина BEFORE + AFTER с полем SOURCE (pipeline/union.py)
SEGMENTS = "segments.csv"
SUMMARY = "summary.json"
UNPAIRED = "unpaired.json"  # заявки без пары (E15): пишет compare, читает summary
APPS = "apps.csv"
CHECKS = "checks.csv"
CHECKS_INDEX = "checks_index.json"  # название проверки -> id процедуры (в checks.csv есть только LABEL)

RUN_PROCEDURES = "procedures"  # папка запуска с файлами процедур-данных, которые читает разбор

# Процедура-данные этапа: какой файл читает разбор и какие переменные в нём нужны
DATA_PROCEDURES = {
    "normalize": ("builtin_normalize", "Правила приведения ответов", ["ARRAY_RULES", "BUCKETS", "ID_PATH"]),
    "aggregate": ("builtin_segments", "Карта полей для разрезов", ["FIELD_MAP", "INPUT_PREFIXES"]),
}


def stage_procedure(config: dict, stage: str, user: str) -> dict:
    """Процедура, выбранная для этапа в конфигурации (в старых конфигурациях `compare` нет — встроенная)."""
    return procedures.find(config.get(stage) or procedures.STAGE_DEFAULTS[stage], user)


def _procedures_dir(ctx, stage: str) -> Path:
    """Папка с файлом процедуры-данных для разбора.

    Встроенная процедура — папка `backend/procedures/` как есть. Своя — её код исполняется в отдельном процессе
    (pipeline/user_procedures.py), а нужные переменные записываются файлом в `runs/<id>/procedures/`:
    так разбор читает ровно то, что выбрал пользователь, и не исполняет чужой код у себя.
    """
    proc = stage_procedure(ctx.config, stage, ctx.owner)
    if proc.get("builtin"):
        return Path(settings.PROCEDURES_DIR)
    file_name, title, names = DATA_PROCEDURES[stage]
    ctx.log("info", f"Процедура «{proc['name']}» ({proc['id']}): исполняю код")
    found = load_constants(stage, procedures.code_of(proc), proc["name"])
    values = {}
    for name in names:
        if name in found:
            values[name] = found[name]
        else:  # необязательная настройка (INPUT_PREFIXES) — берём из встроенной процедуры
            values[name] = load_builtin_value(file_name, name, settings.PROCEDURES_DIR)
            ctx.log("info", f"В процедуре нет {name} — беру из встроенной")
    folder = ctx.run_dir / RUN_PROCEDURES
    write_data_procedure(folder / f"{file_name}.py", f"{title}: «{proc['name']}» ({proc['id']})", values)
    return folder


def _parse_cfg(config: dict) -> dict:
    """Поля конфигурации, которые касаются разбора (CONTRACTS §5)."""
    return {
        "ignore_paths": config.get("ignore_paths") or [],
        "array_modes": config.get("array_modes") or {},
        "array_rules": config.get("array_rules") or {},
        "procedures_dir": settings.PROCEDURES_DIR,  # встроенные процедуры — backend/procedures/ (этап заменит на свою)
        "buckets": config.get("buckets") or {},
    }


def _need_file(path: Path, stage: str, previous: str) -> None:
    """Понятная ошибка вместо FileNotFoundError, если прошлый этап не оставил файл."""
    if not path.is_file():
        raise BadFile(f"Для этапа «{stage}» нет файла {path.name}: сначала должен завершиться этап «{previous}»")


def stage_normalize(ctx) -> None:
    cfg = _parse_cfg(ctx.config)
    cfg["procedures_dir"] = _procedures_dir(ctx, "normalize")
    # Общий прогресс этапа: сначала файлы BEFORE, потом AFTER (счётчик второго идёт со смещением)
    sizes = {s: len(list_source_files(ctx.dataset_dir, s)) for s in ("BEFORE", "AFTER")}
    total, offset = sum(sizes.values()), 0
    for source in ("BEFORE", "AFTER"):
        base = offset
        normalize_dataset(
            ctx.dataset_dir, source, ctx.run_dir / NORMALIZED[source], cfg,
            on_progress=lambda n, base=base: ctx.progress(base + n, total),
            log=ctx.log, is_cancelled=ctx.is_cancelled,
        )
        offset += sizes[source]


def stage_compare(ctx) -> None:
    for name in NORMALIZED.values():
        _need_file(ctx.run_dir / name, "Сравнение срезов", "Приведение ответов")
    proc = stage_procedure(ctx.config, "compare", ctx.owner)
    compare_fn = None  # встроенная процедура — procedures/builtin_compare.py, в этом процессе
    if not proc.get("builtin"):
        ctx.log("info", f"Процедура сравнения «{proc['name']}» ({proc['id']}): исполняю в отдельном процессе")
        code = procedures.code_of(proc)
        compare_fn = lambda before, after: run_compare(code, before, after, proc["name"])  # noqa: E731
    compare_csv(ctx.run_dir / NORMALIZED["BEFORE"], ctx.run_dir / NORMALIZED["AFTER"],
                ctx.run_dir / COMPARISON, log=ctx.log, unpaired_json=ctx.run_dir / UNPAIRED, compare_fn=compare_fn)
    rows = build_union(ctx.run_dir / NORMALIZED["BEFORE"], ctx.run_dir / NORMALIZED["AFTER"],
                       ctx.run_dir / COMPARISON, ctx.run_dir / UNION)
    ctx.log("info", f"Вертикальная витрина union.csv (BEFORE + AFTER, срез в SOURCE): {rows} строк")
    ctx.progress(1, 1)


def stage_aggregate(ctx) -> None:
    _need_file(ctx.run_dir / COMPARISON, "Факты counts", "Сравнение срезов")
    # Две подстадии в одном этапе: сначала слой разрезов (половина прогресса), потом итоги
    ctx.log("info", "Строю слой разрезов (segments.csv)")
    files = len(list_source_files(ctx.dataset_dir, "BEFORE"))
    # карта полей — из выбранной процедуры фактов (встроенная — builtin_segments.py)
    # витрина нужна для CHANGE_SOURCE (логика или входные данные, E10)
    folder = _procedures_dir(ctx, "aggregate")
    fields = segment_field_map(procedures_dir=folder)
    build_segments(ctx.dataset_dir, ctx.run_dir / SEGMENTS, field_map=fields, procedures_dir=folder,
                   comparison_csv=ctx.run_dir / COMPARISON,
                   on_progress=lambda n: ctx.progress(n, 2 * files),
                   log=ctx.log, is_cancelled=ctx.is_cancelled)
    if ctx.is_cancelled():
        return
    store.write_json(ctx.run_dir / app_card.CARD_FIELDS_FILE, fields)
    ctx.log("info", "Считаю итоги (summary.json, apps.csv)")
    build_summary(ctx.run_dir / COMPARISON, ctx.run_dir / SEGMENTS,
                  ctx.run_dir / SUMMARY, ctx.run_dir / APPS, log=ctx.log,
                  unpaired_json=ctx.run_dir / UNPAIRED)
    ctx.progress(1, 1)


FULL_APP_IDS = 100_000  # «все заявки»: больше, чем заявок в любом датасете


def _check_overrides(loaded: list[dict], config: dict, log) -> dict:
    """Параметры проверок на этот прогон: `check_params` конфигурации поверх CHECK["params"].

    Если у проверки есть `app_ids_limit`, по умолчанию просим все заявки, а не первые 20: из строки отчёта
    пользователь переходит ко всем заявкам, которые она насчитала. Конфигурация может задать свой лимит.
    """
    overrides = {}
    for check in loaded:
        params = {}
        if "app_ids_limit" in (check.get("params") or {}):
            params["app_ids_limit"] = FULL_APP_IDS
        own = (config.get("check_params") or {}).get(check["id"]) or {}
        if own:
            log("info", f"Параметры проверки «{check['label']}» из конфигурации: {own}")
        overrides[check["id"]] = {**params, **own}
    return overrides


def stage_checks(ctx) -> None:
    """Подключённые проверки -> checks.csv. Сломанная проверка пользователя не валит запуск:
    в журнале ошибка, в таблице строка FAIL с текстом (так делает run_checks)."""
    for name in (COMPARISON, SEGMENTS, SUMMARY):
        _need_file(ctx.run_dir / name, "Проверки", "Факты counts")
    loaded, rows = [], []
    if not ctx.config.get("checks"):
        ctx.log("info", "Проверки не подключены")
    index = {}  # название проверки -> id процедуры (в checks.csv есть только LABEL)
    for proc_id in ctx.config.get("checks") or []:
        try:
            proc = procedures.find(proc_id, ctx.owner)
            kind, source = procedures.check_source(proc)
            check = load_check(source, kind)
            check["id"] = proc_id  # id строки результата = id процедуры, а не CHECK["id"] из кода
            if check["label"] in index:
                ctx.log("warn", f"Две проверки с названием «{check['label']}»: в таблице у них один check_id")
            index.setdefault(check["label"], proc_id)
            loaded.append(check)
        except (ApiError, BadFile) as exc:
            text = getattr(exc, "message", str(exc))
            ctx.log("error", f"Проверка «{proc_id}» не загружена: {text}")
            # в таблице она тоже видна: FAIL с текстом ошибки, как у упавшей при исполнении
            rows.append({"LABEL": proc_id, "SOURCE": "AFTER", "ARGUMENT": text, "RESULT": "FAIL", "CONFIDENCE": "LOW"})
            index[proc_id] = proc_id
    if loaded:
        rows += run_checks(Mart(ctx.run_dir / COMPARISON, ctx.run_dir / SEGMENTS), loaded,
                           params_override=_check_overrides(loaded, ctx.config, ctx.log), log=ctx.log)
    write_checks_csv(rows, ctx.run_dir / CHECKS)
    (ctx.run_dir / CHECKS_INDEX).write_text(
        json.dumps(index, ensure_ascii=False), encoding="utf-8")
    fails = sum(1 for r in rows if r.get("RESULT") == "FAIL")
    ctx.log("info", f"Проверок: {len(loaded)}, строк результата: {len(rows)}, из них FAIL: {fails}")
    _add_checks_fail(ctx.run_dir / SUMMARY, fails)
    ctx.progress(1, 1)


def _add_checks_fail(summary_path: Path, fails: int) -> None:
    """`checks_fail` — карточка «Проверки с FAIL» на обзоре (docs/api.md п. 7.1)."""
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["checks_fail"] = fails
    # как в summary.py: временный файл + подмена — обрыв посреди записи не оставит половину JSON
    tmp = summary_path.with_name(summary_path.name + ".tmp")
    tmp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, summary_path)
