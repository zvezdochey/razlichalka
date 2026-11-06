"""Настоящие этапы запуска (S5): вызываем функции из `pipeline/` (CONTRACTS §4).

У каждого этапа тот же интерфейс `(ctx) -> None`, что и у заглушек в `app/pipeline_stub.py`.
Ошибки `PipelineError` (в том числе `Cancelled`) наверх не обрабатываем: их превращает в
`{code, message}` менеджер этапов в `services/runs.py`.
"""
import json
from pathlib import Path

from pipeline.checks_runner import load_check, run_checks, write_checks_csv
from pipeline.compare import compare_csv
from pipeline.dataset import list_source_files
from pipeline.errors import BadFile
from pipeline.mart import Mart
from pipeline.normalize import normalize_dataset
from pipeline.segments import build_segments
from pipeline.summary import build_summary

from app import settings
from app.errors import ApiError
from app.services import procedures

# Имена файлов запуска — CONTRACTS §3
NORMALIZED = {"BEFORE": "normalized_BEFORE.csv", "AFTER": "normalized_AFTER.csv"}
COMPARISON = "comparison.csv"
SEGMENTS = "segments.csv"
SUMMARY = "summary.json"
APPS = "apps.csv"
CHECKS = "checks.csv"
CHECKS_INDEX = "checks_index.json"  # название проверки -> id процедуры (в checks.csv есть только LABEL)

# Откуда «открыть код» встроенной процедуры (docs/api.md п. 6)
CODE_REFS = {
    "normalize": {"procedure_id": "builtin_normalize", "source": "file",
                  "path": "procedures/builtin_normalize.py", "line": 1},
    "aggregate": {"procedure_id": "builtin_aggregate", "source": "file",
                  "path": "procedures/builtin_segments.py", "line": 1},
}


def _parse_cfg(config: dict) -> dict:
    """Поля конфигурации, которые касаются разбора (CONTRACTS §5)."""
    return {
        "ignore_paths": config.get("ignore_paths") or [],
        "array_modes": config.get("array_modes") or {},
        "array_rules": config.get("array_rules") or {},
        "procedures_dir": settings.PROCEDURES_DIR,  # встроенные процедуры — backend/procedures/
        "buckets": config.get("buckets") or {},
    }


def _need_file(path: Path, stage: str, previous: str) -> None:
    """Понятная ошибка вместо FileNotFoundError, если прошлый этап не оставил файл."""
    if not path.is_file():
        raise BadFile(f"Для этапа «{stage}» нет файла {path.name}: сначала должен завершиться этап «{previous}»")


def stage_normalize(ctx) -> None:
    cfg = _parse_cfg(ctx.config)
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
    compare_csv(ctx.run_dir / NORMALIZED["BEFORE"], ctx.run_dir / NORMALIZED["AFTER"],
                ctx.run_dir / COMPARISON, log=ctx.log)
    ctx.progress(1, 1)


def stage_aggregate(ctx) -> None:
    _need_file(ctx.run_dir / COMPARISON, "Факты counts", "Сравнение срезов")
    # Две подстадии в одном этапе: сначала слой разрезов (половина прогресса), потом итоги
    ctx.log("info", "Строю слой разрезов (segments.csv)")
    files = len(list_source_files(ctx.dataset_dir, "BEFORE"))
    # карта полей — только из файла процедуры builtin_segments; поля в конфигурации для неё пока нет
    build_segments(ctx.dataset_dir, ctx.run_dir / SEGMENTS, procedures_dir=settings.PROCEDURES_DIR,
                   on_progress=lambda n: ctx.progress(n, 2 * files),
                   log=ctx.log, is_cancelled=ctx.is_cancelled)
    if ctx.is_cancelled():
        return
    ctx.log("info", "Считаю итоги (summary.json, apps.csv)")
    build_summary(ctx.run_dir / COMPARISON, ctx.run_dir / SEGMENTS,
                  ctx.run_dir / SUMMARY, ctx.run_dir / APPS, log=ctx.log)
    ctx.progress(1, 1)


def stage_checks(ctx) -> None:
    """Подключённые проверки -> checks.csv. Сломанная проверка пользователя не валит запуск:
    в журнале ошибка, в таблице строка FAIL с текстом (так делает run_checks)."""
    for name in (COMPARISON, SEGMENTS):
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
        rows += run_checks(Mart(ctx.run_dir / COMPARISON, ctx.run_dir / SEGMENTS), loaded, log=ctx.log)
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
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
