"""Замеры (E11): сколько идёт каждый шаг конвейера и сколько отвечают ручки готового отчёта.

Запуск (из папки backend/):
    python -m pipeline.tools.bench <папка_датасета> [--out <папка>]

1. Прогоняет шаги конвейера по очереди, как этапы запуска: normalize BEFORE, normalize AFTER, compare,
   segments, summary. Время каждого шага — отдельно.
2. Кладёт результат как готовый запуск в DATA_DIR и поднимает приложение через TestClient (без сети).
   Каждую ручку вызывает дважды: первый вызов — «холодный» (приложение только что поднялось, кэшей нет),
   второй — повторный.
3. Печатает таблицу markdown, сверху — железо.

Это инструмент разработчика, а не часть конвейера: только он из `pipeline/` трогает `app/`
(и только внутри функции замера ручек).
"""

import argparse
import json
import os
import platform
import shutil
import sys
import tempfile
import time
from pathlib import Path

from pipeline.compare import compare_csv
from pipeline.normalize import normalize_dataset
from pipeline.segments import build_segments
from pipeline.summary import build_summary

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROCEDURES_DIR = BACKEND_DIR / "procedures"
RUN_ID = "r_bench"
USER = "bench"


def memory_gb() -> str:
    """Объём памяти машины без лишних библиотек: Windows — через WinAPI, Linux — /proc/meminfo."""
    try:
        if sys.platform == "win32":
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                            ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                            ("pf_total", ctypes.c_ulonglong), ("pf_avail", ctypes.c_ulonglong),
                            ("v_total", ctypes.c_ulonglong), ("v_avail", ctypes.c_ulonglong),
                            ("v_ext", ctypes.c_ulonglong)]

            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return f"{status.total / 2**30:.1f} ГБ"
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return f"{int(line.split()[1]) / 2**20:.1f} ГБ"
    except Exception:
        pass
    return "?"


def hardware() -> list[str]:
    return [
        f"- Платформа: `{platform.platform()}`",
        f"- Процессор: `{platform.processor() or platform.machine()}`, логических ядер: {os.cpu_count()}",
        f"- Память: {memory_gb()}",
        f"- Python {platform.python_version()}",
    ]


def timed(func):
    start = time.perf_counter()
    result = func()
    return time.perf_counter() - start, result


def parse_cfg(dataset_dir: Path) -> dict:
    """Тот же конфиг разбора, что у запуска с настройками по умолчанию (services/stages.py)."""
    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    return {
        "ignore_paths": manifest.get("technical_fields_always_differ", []),
        "array_modes": {}, "array_rules": {}, "buckets": {},
        "procedures_dir": PROCEDURES_DIR,
    }


def bench_pipeline(dataset_dir: Path, run_dir: Path) -> list[tuple[str, float]]:
    cfg = parse_cfg(dataset_dir)
    steps = []
    for source in ("BEFORE", "AFTER"):
        seconds, _ = timed(lambda: normalize_dataset(dataset_dir, source, run_dir / f"normalized_{source}.csv", cfg))
        steps.append((f"normalize {source}", seconds))
    seconds, _ = timed(lambda: compare_csv(run_dir / "normalized_BEFORE.csv", run_dir / "normalized_AFTER.csv",
                                           run_dir / "comparison.csv"))
    steps.append(("compare", seconds))
    seconds, _ = timed(lambda: build_segments(dataset_dir, run_dir / "segments.csv", procedures_dir=PROCEDURES_DIR,
                                              comparison_csv=run_dir / "comparison.csv"))
    steps.append(("segments", seconds))
    seconds, _ = timed(lambda: build_summary(run_dir / "comparison.csv", run_dir / "segments.csv",
                                             run_dir / "summary.json", run_dir / "apps.csv"))
    steps.append(("summary", seconds))
    return steps


def _run_json(dataset_dir: Path) -> dict:
    """Готовый запуск, который приложение подхватит при старте (runs.recover)."""
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "id": RUN_ID, "owner": USER, "status": "ready", "config_id": "c_bench", "config": {},
        "dataset": dataset_dir.name, "dataset_folder": dataset_dir.name,
        "created_at": now, "finished_at": now, "progress": {"done": 1, "total": 1},
        "current_stage": None, "error": None, "stages": [],
    }


def bench_api(dataset_dir: Path, data_dir: Path) -> list[tuple[str, float, float]]:
    # app импортируем здесь: остальной pipeline про app не знает (CONTRACTS §1)
    from fastapi.testclient import TestClient

    from app import settings
    from app.main import create_app

    run_dir = data_dir / "runs" / RUN_ID
    (run_dir / "run.json").write_text(json.dumps(_run_json(dataset_dir), ensure_ascii=False), encoding="utf-8")
    settings.DATA_DIR = data_dir
    settings.DATASETS_DIR = dataset_dir.parent
    settings.USE_STUB_PIPELINE = False

    from app.services import warmup

    headers = {"X-User": USER}
    base = f"/api/runs/{RUN_ID}"
    with TestClient(create_app()) as client:
        # id заявки с наибольшим числом различий — как переход к заявке из топа отчёта
        app_id = client.get(f"{base}/apps?sort=-attributes_changed&size=1", headers=headers).json()["apps"][0]["app_id"]
        urls = [
            "/summary",
            "/apps?size=500",
            "/apps?decision_change=approve_to_reject",
            f"/apps/{app_id}/attributes",
            "/facts?dims=PATH,CHANGE_TYPE",
            "/facts?dims=ARRAY_KEY_1",
            "/report",
        ]

        def call(url: str) -> float:
            seconds, response = timed(lambda: client.get(base + url, headers=headers))
            if response.status_code != 200:
                raise RuntimeError(f"{url}: {response.status_code} {response.text[:200]}")
            return seconds

        # «до»: кэши пустые, как сразу после старта сервера без прогрева
        _clear_caches()
        cold = [(call(url), call(url)) for url in urls]
        # «после»: тот же порядок вызовов, но сначала прогрев (так делает конец запуска и GET /runs/{id})
        _clear_caches()
        warm_seconds, _ = timed(lambda: warmup.warm(run_dir))
        warm = [call(url) for url in urls]
    rows = [(url, before_first, after_first, again)
            for url, (before_first, again), after_first in zip(urls, cold, warm)]
    return rows, warm_seconds


def _clear_caches() -> None:
    from app.services import facts, results

    for cached in (results._apps, results._segments, results._attributes, facts._facts_base):
        cached.cache_clear()


def table(steps, api_rows, warm_seconds) -> str:
    lines = ["| Шаг конвейера | Время, с |", "|---|---:|"]
    lines += [f"| {name} | {seconds:.2f} |" for name, seconds in steps]
    lines.append(f"| **всего** | **{sum(s for _, s in steps):.2f}** |")
    lines += ["", f"Прогрев кэшей отчёта: {warm_seconds:.2f} с", "",
              "| Ручка | Первый вызов без прогрева, мс | Первый вызов после прогрева, мс | Повторный, мс |",
              "|---|---:|---:|---:|"]
    lines += [f"| `{url}` | {cold * 1000:.0f} | {warm * 1000:.0f} | {again * 1000:.0f} |"
              for url, cold, warm, again in api_rows]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Замеры конвейера и ручек отчёта")
    parser.add_argument("dataset_dir", type=Path, help="папка с manifest.json")
    parser.add_argument("--out", type=Path, help="куда класть результаты (по умолчанию — временная папка)")
    args = parser.parse_args(argv)

    data_dir = args.out or Path(tempfile.mkdtemp(prefix="bench_"))
    run_dir = data_dir / "runs" / RUN_ID
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)

    sys.stdout.reconfigure(encoding="utf-8")  # консоль Windows по умолчанию не в UTF-8
    steps = bench_pipeline(args.dataset_dir, run_dir)
    api_rows, warm_seconds = bench_api(args.dataset_dir, data_dir)
    print("\n".join(hardware()))
    print()
    print(table(steps, api_rows, warm_seconds))
    if not args.out:
        shutil.rmtree(data_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
