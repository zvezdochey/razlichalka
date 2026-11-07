"""Запуски (docs/api.md п. 5–6): состояние в памяти + DATA_DIR/runs/<id>/run.json, выполнение в фоне."""
import copy
import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from app import pipeline_stub, settings, store
from app.errors import ApiError
from app.services import datasets, stages, warmup
from pipeline.errors import Cancelled as PipelineCancelled

log = logging.getLogger("razlichalka")

# Этапы по порядку: (имя, заголовок, функция-заглушка (ctx) -> None).
# С USE_STUB_PIPELINE=0 вместо заглушки берём одноимённый этап из services/stages.py.
PIPELINE = [
    ("normalize", "Приведение ответов", pipeline_stub.stage_normalize),
    ("compare", "Сравнение срезов", pipeline_stub.stage_compare),
    ("aggregate", "Факты counts", pipeline_stub.stage_aggregate),
    ("checks", "Проверки", pipeline_stub.stage_checks),
]

LOG_TAIL = 50          # сколько последних записей лога отдаёт GET /stages
SAVE_EVERY = 0.5       # progress пишем на диск не чаще, чем раз в столько секунд
# Без этих полей run.json считаем битым: их читают ручки запусков
# (dataset_folder сюда не входит: в run.json до этого поля его нет, Ctx читает его мягко)
RUN_KEYS = ("id", "owner", "status", "config_id", "config", "dataset", "created_at", "finished_at",
            "progress", "current_stage", "error", "stages")

_lock = threading.RLock()
_runs: dict[str, dict] = {}              # id -> состояние запуска
_cancel: dict[str, threading.Event] = {}  # id -> флаг «Стоп»
_done: dict[str, threading.Event] = {}    # id -> запуск закончился
_dirs: dict[str, Path] = {}              # id -> папка запуска
_last_save: dict[str, float] = {}
_executor = ThreadPoolExecutor(max_workers=2)


class Cancelled(Exception):
    """Внутренний сигнал «пользователь нажал Стоп». Этапы pipeline бросают свой Cancelled — ловим оба."""


CANCELLED = (Cancelled, PipelineCancelled)
CANCELLED_ERROR = {"code": "cancelled", "message": "Остановлено пользователем"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(run_dir: Path, run: dict) -> None:
    """Атомарная запись run.json (см. store.write_json)."""
    store.write_json(run_dir / "run.json", run)


def _save(run: dict) -> None:
    _write(_dirs[run["id"]], run)
    _last_save[run["id"]] = time.monotonic()


def recover() -> None:
    """Старт сервера: читаем запуски с диска; недоделанные помечаем ошибкой."""
    with _lock:
        _runs.clear(), _cancel.clear(), _done.clear(), _dirs.clear(), _last_save.clear()
        root = Path(settings.DATA_DIR) / "runs"
        if not root.is_dir():
            return
        for folder in sorted(root.iterdir()):
            try:
                run = json.loads((folder / "run.json").read_text(encoding="utf-8"))
                if not isinstance(run, dict) or not all(k in run for k in RUN_KEYS):
                    raise ValueError("не хватает полей")
                rid = run["id"]
                unfinished = run["status"] in ("pending", "running")
                if unfinished:
                    error = {"code": "internal", "message": "Сервер перезапускали во время запуска"}
                    run["status"], run["error"], run["current_stage"] = "error", error, None
                    run["finished_at"] = _now()
                    for st in run["stages"]:
                        if st["status"] == "running":
                            st["status"], st["finished_at"], st["error"] = "error", _now(), error
            except Exception as exc:  # один битый запуск не должен мешать серверу стартовать
                log.warning("Запуск в %s пропущен — run.json не читается: %s", folder.name, exc)
                continue
            if unfinished:
                try:
                    _write(folder, run)
                except OSError as exc:  # файл валидный — запуск оставляем в памяти со статусом error
                    log.warning("Не удалось сохранить запуск %s после перезапуска: %s", rid, exc)
            _runs[rid] = run
            _dirs[rid] = folder
            _cancel[rid], _done[rid] = threading.Event(), threading.Event()
            _done[rid].set()


def dataset_path(run: dict) -> Path:
    """Папка исходного датасета из метаданных запуска."""
    # Старые запуски хранят только id. Родительская папка может переехать.
    return Path(settings.DATASETS_DIR) / run.get("dataset_folder", run["dataset"])


class Ctx:
    """Что видит этап: лог, прогресс, флаг «Стоп» и пути к файлам запуска."""

    def __init__(self, run: dict, stage: dict, index: int):
        self._run, self._stage, self._index = run, stage, index
        self.run_dir: Path = _dirs[run["id"]]
        self.config: dict = run["config"]
        self.owner: str = run["owner"]  # чьи пользовательские процедуры подключать в этапе checks
        self.dataset: str = run["dataset"]
        self.dataset_dir = dataset_path(run)

    def log(self, level: str, message: str) -> None:
        with _lock:
            self._stage["log"].append({"at": _now(), "level": level, "message": message})
            if time.monotonic() - _last_save.get(self._run["id"], 0) >= SAVE_EVERY:
                _save(self._run)

    def progress(self, done: int, total: int) -> None:
        """Прогресс этапа done/total; общий прогресс запуска делится между этапами поровну."""
        if total <= 0:
            return
        with _lock:
            prog = self._run["progress"]
            share = (self._index + min(done, total) / total) / len(PIPELINE)
            prog["done"] = max(prog["done"], int(prog["total"] * share))
            if time.monotonic() - _last_save.get(self._run["id"], 0) >= SAVE_EVERY:
                _save(self._run)

    def is_cancelled(self) -> bool:
        return _cancel[self._run["id"]].is_set()


def _error_dict(exc: BaseException) -> dict:
    """Ошибка этапа -> {code, message}; PipelineError (S5) уже несёт code/message."""
    code = getattr(exc, "code", None)
    if code and hasattr(exc, "message"):
        return {"code": code, "message": exc.message}
    log.error("Сбой этапа запуска", exc_info=exc)  # подробности — только в серверный лог
    return {"code": "internal", "message": "Внутренняя ошибка при выполнении этапа"}


def _fail(run: dict, stage: dict | None, error: dict) -> None:
    error = dict(error)  # своя копия: CANCELLED_ERROR общий для всех запусков
    with _lock:
        now = _now()
        if stage is not None:
            stage["status"], stage["finished_at"], stage["error"] = "error", now, error
            stage["log"].append({"at": now, "level": "error", "message": error["message"]})
        run["status"], run["error"], run["finished_at"], run["current_stage"] = "error", error, now, None
        _save(run)


def execute(run: dict) -> None:
    """Фон: идём по PIPELINE; ставим статусы, ловим ошибки. Следующие этапы после ошибки остаются pending."""
    rid = run["id"]
    try:
        with _lock:
            if run["status"] != "pending":  # отменили, пока стояли в очереди
                return
            run["status"] = "running"
            _save(run)
        for index, (name, _title, stub) in enumerate(PIPELINE):
            stage = run["stages"][index]
            if _cancel[rid].is_set():
                raise Cancelled()
            with _lock:
                stage["status"], stage["started_at"] = "running", _now()
                run["current_stage"] = name
                _save(run)
            try:
                func = stub if settings.USE_STUB_PIPELINE else getattr(stages, "stage_" + name)
                func(Ctx(run, stage, index))
                if _cancel[rid].is_set():
                    raise Cancelled()
            except CANCELLED:
                _fail(run, stage, CANCELLED_ERROR)
                return
            except Exception as exc:  # любой сбой этапа не должен ронять фоновый поток
                _fail(run, stage, _error_dict(exc))
                return
            with _lock:
                stage["status"], stage["finished_at"] = "ready", _now()
                _save(run)
        # E11: до статуса ready, чтобы первое открытие сводной не читало витрину с диска (~0,5 с).
        # Прогрев ошибок не бросает; «Стоп» во время прогрева уважаем — проверяем флаг до и после.
        if _cancel[rid].is_set():
            raise Cancelled()
        warmup.warm(_dirs[rid])
        if _cancel[rid].is_set():
            raise Cancelled()
        with _lock:
            run["status"], run["current_stage"], run["finished_at"] = "ready", None, _now()
            run["progress"]["done"] = run["progress"]["total"]
            _save(run)
    except CANCELLED:
        _fail(run, None, CANCELLED_ERROR)
    except Exception as exc:
        _fail(run, None, _error_dict(exc))
    finally:
        _done[rid].set()


def create(config: dict, user: str) -> dict:
    """Создаёт запуск по конфигурации и отдаёт его в фон."""
    ds = datasets.get_dataset(config["dataset"])
    if ds is None:
        raise ApiError("not_found", f"Датасет «{config['dataset']}» не найден")
    rid = "r_" + uuid.uuid4().hex[:6]
    snapshot = {k: v for k, v in copy.deepcopy(config).items() if k != "owner"}
    run = {
        "id": rid, "owner": user, "config_id": config["id"], "config": snapshot,
        "dataset": ds["id"], "dataset_folder": ds["path"].name, "status": "pending", "created_at": _now(), "finished_at": None,
        "progress": {"done": 0, "total": ds["applications"] * 2},
        "current_stage": None, "error": None,
        "stages": [
            {"name": name, "title": title, "status": "pending", "started_at": None, "finished_at": None,
             "procedure_id": snapshot.get(name) if name in ("normalize", "aggregate") else None,
             "code_ref": stages.CODE_REFS.get(name), "log": []}
            for name, title, _ in PIPELINE
        ],
    }
    with _lock:
        _runs[rid] = run
        _dirs[rid] = Path(settings.DATA_DIR) / "runs" / rid
        _cancel[rid], _done[rid] = threading.Event(), threading.Event()
        _save(run)
    _executor.submit(execute, run)
    return run


def get_own(run_id: str, user: str) -> dict:
    with _lock:
        run = _runs.get(run_id)
    if run is None or run["owner"] != user:
        raise ApiError("not_found", "Запуск не найден")
    return run


def ready_dir(run_id: str, user: str) -> Path:
    """Каталог результатов, доступный владельцу только после завершения запуска."""
    with _lock:
        run = get_own(run_id, user)
        if run["status"] != "ready":
            raise ApiError("not_ready", "Результаты появятся, когда запуск завершится")
        return _dirs[run_id]


def cancel(run_id: str, user: str) -> dict:
    run = get_own(run_id, user)
    if run["status"] not in ("pending", "running"):
        raise ApiError("conflict", "Запуск уже завершён, останавливать нечего")
    with _lock:
        _cancel[run_id].set()
        if run["status"] == "pending":  # ещё не стартовал — останавливаем сразу
            _fail(run, None, CANCELLED_ERROR)
            _done[run_id].set()
            return run
    if run["status"] == "running":
        _done[run_id].wait(timeout=3)  # даём фону дойти до ближайшей проверки флага
    return run


def list_own(user: str) -> list[dict]:
    with _lock:
        mine = [r for r in _runs.values() if r["owner"] == user]
    return sorted(mine, key=lambda r: r["created_at"], reverse=True)


def snapshot(run: dict) -> dict:
    """Копия состояния под блокировкой — чтобы не сериализовать то, что фон меняет прямо сейчас."""
    with _lock:
        return copy.deepcopy(run)
