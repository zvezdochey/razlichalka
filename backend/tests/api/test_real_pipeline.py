"""Запуск с настоящим пайплайном (S5): мини-датасет и настоящий датасет организаторов."""
import json
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import settings
from app.main import create_app
from tests.real_dataset import REAL

ANN = {"X-User": "ann"}
MINI = Path(__file__).resolve().parents[1] / "fixtures" / "dataset_mini"
RUN_FILES = {"run.json", "normalized_BEFORE.csv", "normalized_AFTER.csv", "comparison.csv",
             "segments.csv", "apps.csv", "summary.json"}


def make_client(tmp_path, monkeypatch, dataset: Path):
    ds = tmp_path / "datasets"
    ds.mkdir()
    shutil.copytree(dataset, ds / dataset.name)
    monkeypatch.setattr(settings, "DATASETS_DIR", ds)
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(settings, "USE_STUB_PIPELINE", False)
    return TestClient(create_app())


def start(client):
    dataset = client.get("/api/datasets", headers=ANN).json()["datasets"][0]["id"]
    cfg = client.post("/api/configs", json={"name": "c", "dataset": dataset}, headers=ANN).json()
    r = client.post("/api/runs", json={"config_id": cfg["id"]}, headers=ANN)
    assert r.status_code == 202
    return r.json()["id"]


def wait(client, run_id, statuses, timeout=300):
    end = time.time() + timeout
    while time.time() < end:
        data = client.get(f"/api/runs/{run_id}", headers=ANN).json()
        if data["status"] in statuses:
            return data
        time.sleep(0.05)
    raise AssertionError(f"не дождались {statuses}, сейчас {data}")


def test_mini_run_to_ready(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, MINI)
    rid = start(client)
    data = wait(client, rid, {"ready", "error"}, timeout=60)
    assert data["status"] == "ready", data["error"]
    assert data["progress"]["done"] == data["progress"]["total"]

    run_dir = settings.DATA_DIR / "runs" / rid
    assert {p.name for p in run_dir.iterdir()} >= RUN_FILES
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["applications"] == 3

    stages = client.get(f"/api/runs/{rid}/stages", headers=ANN).json()["stages"]
    assert [s["status"] for s in stages] == ["ready"] * 4
    assert stages[0]["code_ref"]["path"] == "procedures/builtin_normalize.py"
    assert stages[3]["code_ref"] is None
    assert any("Проверки не подключены" in e["message"] for e in stages[3]["log"])


def test_ready_run_is_warm(tmp_path, monkeypatch):
    """E11: к статусу ready витрина уже в кэше — первый вызов сводной не читает CSV с диска."""
    from app.services import facts, results, warmup
    client = make_client(tmp_path, monkeypatch, MINI)
    rid = start(client)
    assert wait(client, rid, {"ready", "error"}, timeout=60)["status"] == "ready"

    run_dir = settings.DATA_DIR / "runs" / rid
    reads = []
    monkeypatch.setattr(results, "read_csv", lambda path: reads.append(path))
    monkeypatch.setattr(facts, "read_csv", lambda path: reads.append(path))
    assert client.get(f"/api/runs/{rid}/facts?dims=PATH", headers=ANN).status_code == 200
    assert client.get(f"/api/runs/{rid}/apps", headers=ANN).status_code == 200
    assert reads == []
    # GET /runs/{id} готового запуска ставит прогрев в фон (после перезапуска кэши пустые)
    warmup._started.discard(run_dir)
    assert client.get(f"/api/runs/{rid}", headers=ANN).status_code == 200
    assert run_dir in warmup._started


def test_cancel_stops_run(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, MINI)
    from pipeline import normalize
    real = normalize.normalize_dataset

    def slow(*a, is_cancelled=None, **kw):
        while not is_cancelled():  # «долгий» этап: ждём, пока нажмут Стоп
            time.sleep(0.02)
        return real(*a, is_cancelled=is_cancelled, **kw)

    from app.services import stages
    monkeypatch.setattr(stages, "normalize_dataset", slow)
    rid = start(client)
    wait(client, rid, {"running"}, timeout=10)
    client.post(f"/api/runs/{rid}/cancel", headers=ANN)
    data = wait(client, rid, {"error"}, timeout=10)
    # тот же текст, что в docs/api.md п. 5.4, хотя Cancelled бросил сам pipeline
    assert data["error"] == {"code": "cancelled", "message": "Остановлено пользователем"}


@pytest.mark.skipif(not (REAL / "manifest.json").exists(), reason="нет настоящего датасета")
def test_real_dataset_run(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, REAL)
    rid = start(client)
    t0 = time.time()
    data = wait(client, rid, {"ready", "error"})
    print(f"\nвесь запуск: {time.time() - t0:.1f} с")
    assert data["status"] == "ready", data["error"]
    assert data["progress"] == {"done": 4004, "total": 4004}
    for s in client.get(f"/api/runs/{rid}/stages", headers=ANN).json()["stages"]:
        print(s["name"], s["started_at"], s["finished_at"])
    summary = json.loads((settings.DATA_DIR / "runs" / rid / "summary.json").read_text(encoding="utf-8"))
    assert summary["decision_changed"] == 385
