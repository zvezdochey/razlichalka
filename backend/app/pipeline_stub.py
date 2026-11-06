"""Заглушки этапов (S4): «работают» пару секунд, шлют прогресс и пишут лог. Настоящие функции подключит S5."""
import time
from shutil import copyfile

from app.settings import STUB_RUN_DIR

STAGE_SECONDS = 2.5  # сколько «работает» каждый этап (в тестах уменьшаем)
STEPS = 10


def _work(ctx, title: str) -> None:
    ctx.log("info", f"Начинаю этап «{title}»")
    for i in range(1, STEPS + 1):
        deadline = time.monotonic() + STAGE_SECONDS / STEPS
        while time.monotonic() < deadline:
            if ctx.is_cancelled():
                return  # менеджер этапов сам увидит флаг и поставит cancelled
            time.sleep(0.02)
        ctx.progress(i, STEPS)
    ctx.log("info", f"Этап «{title}» закончен")


def stage_normalize(ctx) -> None:
    _work(ctx, "Приведение ответов")


def stage_compare(ctx) -> None:
    _work(ctx, "Сравнение срезов")


def stage_aggregate(ctx) -> None:
    _work(ctx, "Факты counts")
    if ctx.is_cancelled():
        return
    for name in ("comparison.csv", "segments.csv", "apps.csv", "summary.json"):
        copyfile(STUB_RUN_DIR / name, ctx.run_dir / name)


def stage_checks(ctx) -> None:
    _work(ctx, "Проверки")
