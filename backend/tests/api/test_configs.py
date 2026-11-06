import json

import pytest
from fastapi.testclient import TestClient

from app import settings
from app.main import create_app

BODY = {"name": "Прогон", "dataset": "RUN-T-1"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Мини-датасет и пустое хранилище во временных папках."""
    ds = tmp_path / "datasets"
    (ds / "RUN-T-1").mkdir(parents=True)
    (ds / "RUN-T-1" / "manifest.json").write_text(json.dumps({
        "run_id": "RUN-T-1", "applications": 3,
        "srez": {"BEFORE": {"label": "MASTER", "dir": "b"}, "AFTER": {"label": "BETA", "dir": "a"}},
        "technical_fields_always_differ": ["appData.request_id"],
    }), encoding="utf-8")
    (ds / "BROKEN").mkdir()
    (ds / "BROKEN" / "manifest.json").write_text("{не json", encoding="utf-8")
    (ds / "no-manifest").mkdir()
    monkeypatch.setattr(settings, "DATASETS_DIR", ds)
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path / "data")
    return TestClient(create_app())


def as_user(name):
    return {"X-User": name}


def test_datasets_list_skips_broken(client):
    r = client.get("/api/datasets")
    assert r.status_code == 200
    assert r.json() == {"datasets": [{
        "id": "RUN-T-1", "applications": 3,
        "sources": {"BEFORE": "MASTER", "AFTER": "BETA"},
        "technical_fields": ["appData.request_id"],
    }]}


def test_datasets_no_folder(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DATASETS_DIR", tmp_path / "нет-такой")
    r = client.get("/api/datasets")
    assert r.status_code == 200 and r.json() == {"datasets": []}


def test_config_full_cycle(client):
    r = client.post("/api/configs", json=BODY, headers=as_user("ann"))
    assert r.status_code == 201
    cfg = r.json()
    assert cfg["id"].startswith("cfg_")
    assert cfg["ignore_paths"] == ["appData.request_id"]  # умолчание — технические поля
    assert cfg["normalize"] == "builtin_normalize" and cfg["aggregate"] == "builtin_aggregate"
    assert cfg["checks"] == [] and "owner" not in cfg and cfg["updated_at"]

    assert client.get(f"/api/configs/{cfg['id']}", headers=as_user("ann")).json() == cfg
    lst = client.get("/api/configs", headers=as_user("ann")).json()["configs"]
    assert lst == [{"id": cfg["id"], "name": "Прогон", "dataset": "RUN-T-1", "updated_at": cfg["updated_at"]}]

    new = {**BODY, "name": "Новое имя", "buckets": {"a.b": [0.3, 0.6]}, "array_modes": {"x[]": "index"}}
    r = client.put(f"/api/configs/{cfg['id']}", json=new, headers=as_user("ann"))
    assert r.status_code == 200
    assert r.json()["id"] == cfg["id"] and r.json()["name"] == "Новое имя"
    assert r.json()["buckets"] == {"a.b": [0.3, 0.6]}

    assert client.delete(f"/api/configs/{cfg['id']}", headers=as_user("ann")).status_code == 204
    assert client.get(f"/api/configs/{cfg['id']}", headers=as_user("ann")).status_code == 404
    assert client.get("/api/configs", headers=as_user("ann")).json() == {"configs": []}


def test_other_user_sees_nothing(client):
    cid = client.post("/api/configs", json=BODY, headers=as_user("ann")).json()["id"]
    assert client.get("/api/configs", headers=as_user("bob")).json() == {"configs": []}
    for method in ("get", "delete"):
        r = getattr(client, method)(f"/api/configs/{cid}", headers=as_user("bob"))
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = client.put(f"/api/configs/{cid}", json=BODY, headers=as_user("bob"))
    assert r.status_code == 404
    # у владельца всё на месте
    assert client.get(f"/api/configs/{cid}", headers=as_user("ann")).status_code == 200


def test_unknown_dataset(client):
    r = client.post("/api/configs", json={**BODY, "dataset": "нет"})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize("patch", [
    {"name": "   "},
    {"buckets": {"p": [0.6, 0.3]}},
    {"buckets": {"p": [0.3, 0.3]}},
    {"array_modes": {"p": "random"}},
])
def test_bad_body_is_bad_code(client, patch):
    r = client.post("/api/configs", json={**BODY, **patch})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_code"
    assert r.json()["error"]["message"]


def test_configs_survive_restart(client):
    cid = client.post("/api/configs", json=BODY, headers=as_user("ann")).json()["id"]
    fresh = TestClient(create_app())  # «перезапуск»: новое приложение, те же файлы
    assert fresh.get(f"/api/configs/{cid}", headers=as_user("ann")).status_code == 200


def test_store_roundtrip(client):
    from app import store
    store.save("things", "t_1", {"a": 1})
    assert store.load("things", "t_1") == {"a": 1}
    assert store.list("things") == [{"a": 1}]
    assert store.delete("things", "t_1") is True and store.delete("things", "t_1") is False
    assert store.load("things", "../evil") is None
