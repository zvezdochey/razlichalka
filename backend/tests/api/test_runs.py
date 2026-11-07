import json
import time

import pytest
from fastapi.testclient import TestClient

from app import pipeline_stub, settings
from app.main import create_app
from app.services import runs

ANN = {"X-User": "ann"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    ds = tmp_path / "datasets"
    (ds / "RUN-T-1").mkdir(parents=True)
    (ds / "RUN-T-1" / "manifest.json").write_text(json.dumps({
        "run_id": "RUN-T-1", "applications": 3,
        "srez": {"BEFORE": {"label": "MASTER", "dir": "b"}, "AFTER": {"label": "BETA", "dir": "a"}},
        "technical_fields_always_differ": [],
    }), encoding="utf-8")
    monkeypatch.setattr(settings, "DATASETS_DIR", ds)
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(settings, "USE_STUB_PIPELINE", True)
    monkeypatch.setattr(pipeline_stub, "STAGE_SECONDS", 0.3)
    return TestClient(create_app())


def new_run(client, user=ANN):
    cfg = client.post("/api/configs", json={"name": "c", "dataset": "RUN-T-1"}, headers=user).json()
    r = client.post("/api/runs", json={"config_id": cfg["id"]}, headers=user)
    assert r.status_code == 202
    return cfg, r.json()


def wait_for(client, run_id, statuses, user=ANN, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        data = client.get(f"/api/runs/{run_id}", headers=user).json()
        if data["status"] in statuses:
            return data
        time.sleep(0.05)
    raise AssertionError(f"не дождались {statuses}, сейчас {data}")


def test_run_to_ready(client):
    cfg, started = new_run(client)
    assert started["status"] == "pending" and started["config_id"] == cfg["id"]
    assert started["id"].startswith("r_")

    data = wait_for(client, started["id"], {"ready"})
    assert data["progress"] == {"done": 6, "total": 6}  # 2 × 3 заявки
    assert data["current_stage"] is None and data["error"] is None and data["finished_at"]
    assert set(data) == {"id", "status", "config_id", "dataset", "created_at", "finished_at",
                         "progress", "current_stage", "error"}

    stages = client.get(f"/api/runs/{started['id']}/stages", headers=ANN).json()["stages"]
    assert [s["name"] for s in stages] == ["normalize", "compare", "aggregate", "checks"]
    assert all(s["status"] == "ready" and s["started_at"] and s["finished_at"] for s in stages)
    assert stages[0]["procedure_id"] == "builtin_normalize" and stages[1]["procedure_id"] is None
    assert stages[0]["log"] and "error" not in stages[0]

    lst = client.get("/api/runs", headers=ANN).json()["runs"]
    assert [r["id"] for r in lst] == [started["id"]] and lst[0]["status"] == "ready"


def test_progress_and_current_stage_while_running(client):
    _, started = new_run(client)
    data = wait_for(client, started["id"], {"running"})
    assert data["current_stage"] in {"normalize", "compare", "aggregate", "checks"}
    wait_for(client, started["id"], {"ready"})


def test_cancel_in_the_middle(client):
    _, started = new_run(client)
    wait_for(client, started["id"], {"running"})
    r = client.post(f"/api/runs/{started['id']}/cancel", headers=ANN)
    assert r.status_code == 200
    assert r.json() == {"id": started["id"], "status": "error",
                        "error": {"code": "cancelled", "message": "Остановлено пользователем"}}
    stages = client.get(f"/api/runs/{started['id']}/stages", headers=ANN).json()["stages"]
    assert stages[-1]["status"] == "pending"
    # запуск уже остановлен — повторный cancel это 409
    again = client.post(f"/api/runs/{started['id']}/cancel", headers=ANN)
    assert again.status_code == 409 and again.json()["error"]["code"] == "conflict"


def test_cancel_finished_run_is_conflict(client):
    _, started = new_run(client)
    wait_for(client, started["id"], {"ready"})
    r = client.post(f"/api/runs/{started['id']}/cancel", headers=ANN)
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"


def test_other_user_gets_not_found(client):
    cfg, started = new_run(client)
    bob = {"X-User": "bob"}
    for r in (
        client.get(f"/api/runs/{started['id']}", headers=bob),
        client.post(f"/api/runs/{started['id']}/cancel", headers=bob),
        client.get(f"/api/runs/{started['id']}/stages", headers=bob),
        client.get(f"/api/runs/{started['id']}/stages/normalize/log", headers=bob),
        client.post("/api/runs", json={"config_id": cfg["id"]}, headers=bob),
    ):
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert client.get("/api/runs", headers=bob).json() == {"runs": []}
    wait_for(client, started["id"], {"ready"})


def test_unknown_config(client):
    r = client.post("/api/runs", json={"config_id": "cfg_нет"}, headers=ANN)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_run_survives_restart(client):
    _, started = new_run(client)
    wait_for(client, started["id"], {"ready"})
    again = TestClient(create_app())  # «перезапуск» сервера
    data = again.get(f"/api/runs/{started['id']}", headers=ANN).json()
    assert data["status"] == "ready" and data["progress"]["done"] == 6
    assert [r["id"] for r in again.get("/api/runs", headers=ANN).json()["runs"]] == [started["id"]]


def test_cancel_after_restart(client):
    _, started = new_run(client)
    wait_for(client, started["id"], {"ready"})
    again = TestClient(create_app())
    r = again.post(f"/api/runs/{started['id']}/cancel", headers=ANN)
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"


def test_broken_run_json_does_not_stop_server(client, tmp_path):
    _, started = new_run(client)
    wait_for(client, started["id"], {"ready"})
    for name, text in (("r_bad1", "{не json"), ("r_bad2", '{"id": "r_bad2", "status": "running"}'), ("r_bad3", "[]")):
        (tmp_path / "data" / "runs" / name).mkdir()
        (tmp_path / "data" / "runs" / name / "run.json").write_text(text, encoding="utf-8")
    again = TestClient(create_app())
    assert [r["id"] for r in again.get("/api/runs", headers=ANN).json()["runs"]] == [started["id"]]


def test_run_knows_dataset_folder(client, tmp_path, monkeypatch):
    # имя папки не совпадает с run_id из манифеста — этап всё равно знает, где файлы
    (tmp_path / "datasets" / "RUN-T-1").rename(tmp_path / "datasets" / "папка")
    seen = []
    monkeypatch.setattr(runs, "PIPELINE", [("normalize", "Приведение ответов", lambda ctx: seen.append(ctx.dataset_dir))])
    _, started = new_run(client)
    wait_for(client, started["id"], {"ready"})
    assert seen == [tmp_path / "datasets" / "папка"]
    assert "dataset_folder" not in client.get(f"/api/runs/{started['id']}", headers=ANN).json()


def test_restart_keeps_run_when_save_fails(client, tmp_path, monkeypatch):
    _, started = new_run(client)
    wait_for(client, started["id"], {"ready"})
    path = tmp_path / "data" / "runs" / started["id"] / "run.json"
    run = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**run, "status": "running"}), encoding="utf-8")

    def broken_write(*args):
        raise OSError("диск только на чтение")

    monkeypatch.setattr(runs, "_write", broken_write)
    again = TestClient(create_app())
    data = again.get(f"/api/runs/{started['id']}", headers=ANN).json()
    assert data["status"] == "error" and data["error"]["code"] == "internal"


def test_unfinished_run_becomes_error_after_restart(client, monkeypatch):
    monkeypatch.setattr(pipeline_stub, "STAGE_SECONDS", 5)
    _, started = new_run(client)
    wait_for(client, started["id"], {"running"})
    old_flag = runs._cancel[started["id"]]
    again = TestClient(create_app())
    data = again.get(f"/api/runs/{started['id']}", headers=ANN).json()
    assert data["status"] == "error"
    assert data["error"] == {"code": "internal", "message": "Сервер перезапускали во время запуска"}
    old_flag.set()  # останавливаем старый фоновый поток, чтобы он не мешал другим тестам


def test_stage_error(client, monkeypatch):
    def boom(ctx):
        ctx.log("info", "начали")
        raise RuntimeError("сломалось")

    monkeypatch.setattr(runs, "PIPELINE", [
        ("normalize", "Приведение ответов", pipeline_stub.stage_normalize),
        ("compare", "Сравнение срезов", boom),
        ("aggregate", "Факты counts", pipeline_stub.stage_aggregate),
        ("checks", "Проверки", pipeline_stub.stage_checks),
    ])
    _, started = new_run(client)
    data = wait_for(client, started["id"], {"error"})
    assert data["error"]["code"] == "internal" and "сломалось" not in data["error"]["message"]
    stages = client.get(f"/api/runs/{started['id']}/stages", headers=ANN).json()["stages"]
    assert [s["status"] for s in stages] == ["ready", "error", "pending", "pending"]
    assert stages[1]["log"][-1]["level"] == "error"


def test_full_log_with_after(client):
    _, started = new_run(client)
    wait_for(client, started["id"], {"ready"})
    url = f"/api/runs/{started['id']}/stages/normalize/log"
    full = client.get(url, headers=ANN).json()
    assert full["next"] == len(full["entries"]) >= 2
    assert set(full["entries"][0]) == {"at", "level", "message"}
    tail = client.get(url + "?after=1", headers=ANN).json()
    assert tail["entries"] == full["entries"][1:] and tail["next"] == full["next"]
    assert client.get(url + "?after=999", headers=ANN).json() == {"entries": [], "next": 999}
    assert client.get(f"/api/runs/{started['id']}/stages/нет/log", headers=ANN).status_code == 404


def test_stages_log_is_last_50(client, monkeypatch):
    def chatty(ctx):
        for i in range(70):
            ctx.log("info", f"строка {i}")

    monkeypatch.setattr(runs, "PIPELINE", [("normalize", "Приведение ответов", chatty)] +
                        runs.PIPELINE[1:])
    _, started = new_run(client)
    wait_for(client, started["id"], {"ready"})
    first = client.get(f"/api/runs/{started['id']}/stages", headers=ANN).json()["stages"][0]["log"]
    assert len(first) == 50 and first[-1]["message"] == "строка 69"
    full = client.get(f"/api/runs/{started['id']}/stages/normalize/log", headers=ANN).json()
    assert len(full["entries"]) == 70


def test_cancel_queued_run_is_instant(client, monkeypatch):
    monkeypatch.setattr(pipeline_stub, "STAGE_SECONDS", 3)
    ids = [new_run(client)[1]["id"] for _ in range(3)]  # два потока заняты, третий в очереди
    r = client.post(f"/api/runs/{ids[2]}/cancel", headers=ANN)
    assert r.json()["status"] == "error" and r.json()["error"]["code"] == "cancelled"
    for i in ids[:2]:
        client.post(f"/api/runs/{i}/cancel", headers=ANN)
