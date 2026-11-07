"""Процедуры и проверки (S10): ручки /api/procedures, этап checks и GET /runs/{id}/checks."""
import json
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import settings
from app.main import create_app

ANN = {"X-User": "ann"}
BOB = {"X-User": "bob"}
MINI = Path(__file__).resolve().parents[1] / "fixtures" / "dataset_mini"

GOOD_CHECK = '''
def run(mart, params):
    return [{"LABEL": "Моя проверка", "SOURCE": "AFTER", "ARGUMENT": "", "CNT": 1,
             "TOTAL": mart.total_apps(), "METRIC": 0.5, "APP_IDS": [], "RESULT": "FAIL", "CONFIDENCE": "LOW"}]

CHECK = {"id": "mine", "label": "Моя проверка", "params": {}, "entrypoint": run}
'''
BROKEN_CHECK = '''
def run(mart, params):
    raise ValueError("сломано")

CHECK = {"id": "broken", "label": "Сломанная", "params": {}, "entrypoint": run}
'''
BUILTIN_FILE = '''
def run(mart, params):
    return [{"LABEL": "Встроенная", "SOURCE": "AFTER", "ARGUMENT": "", "CNT": 0, "TOTAL": 3,
             "METRIC": "", "APP_IDS": [], "RESULT": "PASS", "CONFIDENCE": "HIGH"}]

CHECK = {"id": "demo", "label": "Встроенная", "params": {}, "entrypoint": run}
'''


@pytest.fixture
def client(tmp_path, monkeypatch):
    ds = tmp_path / "datasets"
    ds.mkdir()
    shutil.copytree(MINI, ds / MINI.name)
    checks = tmp_path / "checks"
    checks.mkdir()
    (checks / "check_demo.py").write_text(BUILTIN_FILE, encoding="utf-8")
    monkeypatch.setattr(settings, "DATASETS_DIR", ds)
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(settings, "CHECKS_DIR", checks)
    monkeypatch.setattr(settings, "USE_STUB_PIPELINE", False)
    return TestClient(create_app())


def new_check(client, code, name="Моя", user=ANN):
    return client.post("/api/procedures", headers=user,
                       json={"kind": "check", "name": name, "source": "inline", "code": code})


def test_list_has_builtins(client):
    procs = client.get("/api/procedures", headers=ANN).json()["procedures"]
    ids = {p["id"] for p in procs}
    assert {"builtin_normalize", "builtin_aggregate", "builtin_demo"} <= ids
    only_checks = client.get("/api/procedures?kind=check", headers=ANN).json()["procedures"]
    assert [p["id"] for p in only_checks] == ["builtin_demo"]
    assert only_checks[0]["name"] == "Встроенная" and only_checks[0]["builtin"] is True


def test_create_validate_update_delete(client):
    r = new_check(client, GOOD_CHECK)
    assert r.status_code == 201
    proc = r.json()
    assert proc["builtin"] is False and "code" not in proc and "owner" not in proc

    assert client.get(f"/api/procedures/{proc['id']}", headers=ANN).json()["code"] == GOOD_CHECK
    assert client.get(f"/api/procedures/{proc['id']}", headers=BOB).status_code == 404
    assert proc["id"] not in {p["id"] for p in client.get("/api/procedures", headers=BOB).json()["procedures"]}

    r = client.put(f"/api/procedures/{proc['id']}", headers=ANN,
                   json={"kind": "check", "name": "Новое имя", "source": "inline", "code": GOOD_CHECK})
    assert r.status_code == 200 and r.json()["name"] == "Новое имя"

    assert client.delete(f"/api/procedures/{proc['id']}", headers=ANN).status_code == 204
    assert client.get(f"/api/procedures/{proc['id']}", headers=ANN).status_code == 404


def test_bad_code(client):
    r = new_check(client, "def run(:\n")
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_code"
    v = client.post("/api/procedures/validate", json={"kind": "check", "source": "inline", "code": "x = 1"}).json()
    assert v["ok"] is False and v["errors"][0]["line"] == 1
    ok = client.post("/api/procedures/validate", json={"kind": "check", "source": "inline", "code": GOOD_CHECK}).json()
    assert ok == {"ok": True, "errors": []}


def test_builtin_not_deletable_and_code_readable(client):
    r = client.delete("/api/procedures/builtin_demo", headers=ANN)
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    code = client.get("/api/procedures/builtin_demo", headers=ANN).json()["code"]
    assert "CHECK" in code
    assert "ARRAY_RULES" in client.get("/api/procedures/builtin_normalize", headers=ANN).json()["code"]


def test_file_source_cannot_escape_folder(client):
    for path in ("checks/../../etc/passwd.py", "/etc/passwd.py", "checks/missing.py", "other/x.py"):
        r = client.post("/api/procedures", headers=ANN,
                        json={"kind": "check", "name": "x", "source": "file", "path": path})
        assert r.status_code == 400, path
    ok = client.post("/api/procedures", headers=ANN,
                     json={"kind": "check", "name": "x", "source": "file", "path": "checks/check_demo.py"})
    assert ok.status_code == 201


def wait_ready(client, rid):
    end = time.time() + 60
    while time.time() < end:
        data = client.get(f"/api/runs/{rid}", headers=ANN).json()
        if data["status"] in ("ready", "error"):
            return data
        time.sleep(0.05)
    raise AssertionError("запуск не завершился")


def test_run_with_checks(client):
    mine = new_check(client, GOOD_CHECK).json()["id"]
    broken = new_check(client, BROKEN_CHECK, name="Сломанная").json()["id"]
    gone = new_check(client, GOOD_CHECK, name="Удалённая").json()["id"]
    ds = client.get("/api/datasets", headers=ANN).json()["datasets"][0]["id"]
    cfg = client.post("/api/configs", headers=ANN, json={
        "name": "c", "dataset": ds, "checks": ["builtin_demo", mine, broken, gone]}).json()
    client.delete(f"/api/procedures/{gone}", headers=ANN)  # после сохранения конфигурации процедуру удалили
    rid = client.post("/api/runs", json={"config_id": cfg["id"]}, headers=ANN).json()["id"]
    data = wait_ready(client, rid)
    assert data["status"] == "ready", data["error"]  # сломанная проверка запуск не валит

    stage = client.get(f"/api/runs/{rid}/stages", headers=ANN).json()["stages"][3]
    errors = [e["message"] for e in stage["log"] if e["level"] == "error"]
    assert any(gone in m for m in errors) and any("Сломанная" in m for m in errors)

    table = client.get(f"/api/runs/{rid}/checks", headers=ANN).json()
    assert table["total"] == 4
    by_name = {r["check_name"]: r for r in table["rows"]}
    assert by_name["Встроенная"]["result"] == "PASS" and by_name["Встроенная"]["check_id"] == "builtin_demo"
    assert by_name["Моя проверка"]["numbers"] == "1 / 3" and by_name["Моя проверка"]["faint"] is True
    assert by_name["Моя проверка"]["metric"] == 0.5 and by_name["Моя проверка"]["apps_ref"] is None
    assert by_name["Сломанная"]["result"] == "FAIL"
    assert by_name[gone]["result"] == "FAIL" and "не найден" in by_name[gone]["argument"]

    fails = client.get(f"/api/runs/{rid}/checks?result=FAIL", headers=ANN).json()
    assert fails["total"] == 3
    assert client.get(f"/api/runs/{rid}/checks?result=MAYBE", headers=ANN).status_code == 400

    summary = client.get(f"/api/runs/{rid}/summary", headers=ANN).json()
    assert summary["checks_fail"] == 3


def test_report_has_checks_block(client):
    ds = client.get("/api/datasets", headers=ANN).json()["datasets"][0]["id"]
    cfg = client.post("/api/configs", headers=ANN, json={"name": "c", "dataset": ds, "checks": ["builtin_demo"]}).json()
    rid = client.post("/api/runs", json={"config_id": cfg["id"]}, headers=ANN).json()["id"]
    assert wait_ready(client, rid)["status"] == "ready"
    html = client.get(f"/api/runs/{rid}/report.html", headers=ANN)
    assert html.status_code == 200
    assert "Встроенная" in html.text and "PASS" in html.text


def test_config_checks_are_validated(client):
    ds = client.get("/api/datasets", headers=ANN).json()["datasets"][0]["id"]
    def post(checks, user=ANN):
        return client.post("/api/configs", headers=user, json={"name": "c", "dataset": ds, "checks": checks})
    assert post(["builtin_demo"]).status_code == 201
    assert post(["zzz"]).status_code == 404
    assert post(["builtin_normalize"]).status_code == 400
    mine = new_check(client, GOOD_CHECK).json()["id"]
    assert post([mine]).status_code == 201
    assert post([mine], BOB).status_code == 404  # чужая проверка
