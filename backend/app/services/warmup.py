"""Прогрев кэшей отчёта (E11).

Узкое место отклика — первое чтение витрины: comparison.csv на 290 тыс. строк читается и приводится к типам
~0,5 с для сводной (`/facts`) и ещё ~0,2 с для атрибутов заявки. Повторные вызовы берут готовое из `lru_cache`.
Поэтому всё, что ручки отчёта читают с диска, загружаем заранее:
- в конце запуска, до статуса `ready` (services/runs.py) — первое открытие готового отчёта уже быстрое;
- в фоне при `GET /runs/{id}` готового запуска — после перезапуска сервера кэши пустые, а страницу запуска
  открывают раньше, чем сводную.
"""
import logging
import threading
from pathlib import Path

from app.errors import ApiError
from app.services import facts, results

log = logging.getLogger("razlichalka")
_lock = threading.Lock()  # два прогрева одновременно не нужны: второй возьмёт готовое из кэша
_started: set[Path] = set()  # какие запуски уже прогревали в этом процессе (GET /runs/{id} зовут часто)
_started_lock = threading.Lock()


def warm(run_dir: Path) -> None:
    """Загружает в кэш все таблицы, которые читают ручки отчёта. Уже загруженное берётся из кэша мгновенно."""
    with _started_lock:
        _started.add(run_dir)
    with _lock:
        try:
            results._apps(run_dir)
            results._segments(run_dir)
            results._attributes(run_dir)
            facts._facts_base(run_dir)
        except (ApiError, OSError, ValueError, KeyError) as exc:
            # нет файла или старый формат — ручка сама скажет об этом пользователю, прогрев просто пропускаем
            log.warning("Прогрев кэша %s пропущен: %s", run_dir.name, exc)


def reset() -> None:
    """Забыть всё прочитанное (дождавшись идущего прогрева). Нужно, только если файлы готового запуска
    переписали руками — в работе приложения они не меняются; так делают тесты."""
    with _lock:
        for cached in (results._apps, results._segments, results._attributes, facts._facts_base):
            cached.cache_clear()
        with _started_lock:
            _started.clear()


def warm_in_background(run_dir: Path) -> None:
    """Прогрев в отдельном потоке — ответ на запрос не ждёт. Один раз на запуск за жизнь процесса."""
    with _started_lock:  # не _lock: запрос не должен ждать идущий прогрев
        if run_dir in _started:
            return
        _started.add(run_dir)
    threading.Thread(target=warm, args=(run_dir,), daemon=True, name=f"warm-{run_dir.name}").start()
