"""Настоящие этапы запуска (S5): вызываем функции из `pipeline/` (CONTRACTS §4).

У каждого этапа тот же интерфейс `(ctx) -> None`, что и у заглушек в `app/pipeline_stub.py`.
Ошибки `PipelineError` (в том числе `Cancelled`) наверх не обрабатываем: их превращает в
`{code, message}` менеджер этапов в `services/runs.py`.
"""
from pathlib import Path

from pipeline.compare import compare_csv
from pipeline.dataset import list_source_files
from pipeline.errors import BadFile
from pipeline.normalize import normalize_dataset
from pipeline.segments import build_segments
from pipeline.summary import build_summary

# Имена файлов запуска — CONTRACTS §3
NORMALIZED = {"BEFORE": "normalized_BEFORE.csv", "AFTER": "normalized_AFTER.csv"}
COMPARISON = "comparison.csv"
SEGMENTS = "segments.csv"
SUMMARY = "summary.json"
APPS = "apps.csv"

# Откуда «открыть код» встроенной процедуры (docs/api.md п. 6)
CODE_REFS = {
    "normalize": {"procedure_id": "builtin_normalize", "source": "file",
                  "path": "backend/pipeline/normalize.py", "line": 1},
    "compare": {"procedure_id": "builtin_compare", "source": "file",
                "path": "backend/pipeline/compare.py", "line": 1},
    "aggregate": {"procedure_id": "builtin_aggregate", "source": "file",
                  "path": "backend/pipeline/summary.py", "line": 1},
}


def _parse_cfg(config: dict) -> dict:
    """Поля конфигурации, которые касаются разбора (CONTRACTS §5)."""
    return {
        "ignore_paths": config.get("ignore_paths") or [],
        "array_modes": config.get("array_modes") or {},
        "array_rules": config.get("array_rules") or {},
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
    build_segments(ctx.dataset_dir, ctx.run_dir / SEGMENTS,
                   on_progress=lambda n: ctx.progress(n, 2 * files),
                   log=ctx.log, is_cancelled=ctx.is_cancelled)
    if ctx.is_cancelled():
        return
    ctx.log("info", "Считаю итоги (summary.json, apps.csv)")
    build_summary(ctx.run_dir / COMPARISON, ctx.run_dir / SEGMENTS,
                  ctx.run_dir / SUMMARY, ctx.run_dir / APPS, log=ctx.log)
    ctx.progress(1, 1)


def stage_checks(ctx) -> None:
    ctx.log("info", "Проверки не подключены")
    ctx.progress(1, 1)
