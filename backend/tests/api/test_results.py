import json
import time

import pytest
from fastapi.testclient import TestClient

from app import pipeline_stub, settings
from app.main import create_app
from pipeline.csvio import read_csv, write_csv
from pipeline.summary import build_summary

OWNER = {"X-User": "ann"}
RESULT_PATHS = ("summary", "apps", "apps/MINI-001/attributes")


def test_legacy_run_classifies_only_known_unchanged_apps(client, ready_run):
    from app.services import warmup
    path = settings.DATA_DIR / "runs" / ready_run.rsplit("/", 1)[1] / "apps.csv"
    rows = read_csv(path).drop(columns="change_source")
    write_csv(path, list(rows.columns), rows.to_dict("records"))
    warmup.reset()
    known = rows[(rows["decision_change"] == "same") & (rows["attributes_changed"] == "0")]
    response = client.get(ready_run + "/apps", params={"change_source": "none"}).json()
    assert response["total"] == len(known)
    assert {row["app_id"] for row in response["apps"]} == set(known["app_id"])


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATASETS_DIR", tmp_path / "missing")
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(settings, "USE_STUB_PIPELINE", True)
    monkeypatch.setattr(pipeline_stub, "STAGE_SECONDS", 0)
    return TestClient(create_app(), headers=OWNER)


def start_run(client):
    datasets = client.get("/api/datasets").json()["datasets"]
    assert [(ds["id"], ds["applications"]) for ds in datasets] == [("RUN-MINI", 6)]
    config = client.post("/api/configs", json={"name": "Мини", "dataset": "RUN-MINI"})
    assert config.status_code == 201
    run = client.post("/api/runs", json={"config_id": config.json()["id"]})
    assert run.status_code == 202
    return f"/api/runs/{run.json()['id']}"


@pytest.fixture
def ready_run(client):
    url = start_run(client)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = client.get(url).json()
        if status["status"] == "ready":
            return url
        assert status["status"] != "error", status
        time.sleep(0.02)
    pytest.fail("Запуск не дошёл до ready")


def test_summary_serves_exact_artifact(client, ready_run):
    artifact = settings.STUB_RUN_DIR / "summary.json"
    response = client.get(f"{ready_run}/summary")
    assert response.status_code == 200
    assert response.content == artifact.read_bytes()

    run_dir = settings.DATA_DIR / "runs" / ready_run.rsplit("/", 1)[-1]
    for name in ("comparison.csv", "segments.csv", "apps.csv", "summary.json"):
        assert (run_dir / name).read_bytes() == (settings.STUB_RUN_DIR / name).read_bytes()
    restarted = TestClient(create_app(), headers=OWNER)
    assert restarted.get(f"{ready_run}/summary").json() == response.json()


def test_summary_of_old_run_gets_zero_unpaired(client, ready_run):
    """Запуск до E15: в summary.json нет счётчиков заявок без пары — ручка отдаёт нули."""
    run_dir = settings.DATA_DIR / "runs" / ready_run.rsplit("/", 1)[-1]
    old = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    old.pop("applications_only_before"), old.pop("applications_only_after")
    (run_dir / "summary.json").write_text(json.dumps(old), encoding="utf-8")
    body = client.get(f"{ready_run}/summary").json()
    assert body["applications_only_before"] == 0 and body["applications_only_after"] == 0
    assert body["applications"] == old["applications"]

def test_fixture_matches_pipeline_contract(tmp_path):
    fixture = settings.STUB_RUN_DIR
    summary = build_summary(
        fixture / "comparison.csv", fixture / "segments.csv",
        tmp_path / "summary.json", tmp_path / "apps.csv",
    )
    assert summary == json.loads((fixture / "summary.json").read_bytes())
    assert read_csv(tmp_path / "apps.csv").equals(read_csv(fixture / "apps.csv"))


@pytest.mark.parametrize(("params", "expected"), [
    ({"decision_change": "approve_to_reject"}, ["MINI-001", "MINI-005"]),
    ({"decision_change": "approve_to_reject,reject_to_approve"}, ["MINI-001", "MINI-002", "MINI-005"]),
    ({"has_attr_change": "1"}, ["MINI-001", "MINI-002", "MINI-004", "MINI-005"]),
    ({"change_source": "logic"}, ["MINI-002", "MINI-005"]),
    ({"change_source": "logic,data"}, ["MINI-001", "MINI-002", "MINI-004", "MINI-005"]),
    ({"change_source": "data", "decision_change": "approve_to_reject"}, ["MINI-001"]),
    ({"change_source": "unknown"}, []),
    ({"search": "logic"}, []),
    ({"search": "mini-002"}, ["MINI-002"]),
    ({"search": "mOdEl_V2"}, ["MINI-001", "MINI-003"]),
    ({"search": "bRoKeR"}, ["MINI-002", "MINI-004"]),
    ({"search": ".*"}, []),
])
def test_apps_filters(client, ready_run, params, expected):
    response = client.get(f"{ready_run}/apps", params=params)
    assert response.status_code == 200
    data = response.json()
    assert [row["app_id"] for row in data["apps"]] == expected
    assert (data["page"], data["size"], data["total"]) == (1, 50, len(expected))


def test_apps_sort_and_paginate(client, ready_run):
    url = f"{ready_run}/apps"
    params = {"size": 2, "sort": "-attributes_changed"}
    first, second, empty = [
        client.get(url, params={**params, "page": page}).json()
        for page in (1, 2, 4)
    ]
    assert [data["total"] for data in (first, second, empty)] == [6, 6, 6]
    assert [row["attributes_changed"] for row in first["apps"]] == [12, 2]
    assert [row["attributes_changed"] for row in second["apps"]] == [1, 1]
    assert empty["apps"] == []
    by_id = client.get(url, params={"sort": "-app_id", "size": 2})
    assert [row["app_id"] for row in by_id.json()["apps"]] == ["MINI-006", "MINI-005"]
    assert first["apps"][0]["reject_reason_before"] is None
    assert set(first["apps"][0]) == {
        "app_id", "decision_before", "decision_after", "decision_change", "attributes_changed",
        "pd_model_before", "pd_model_after", "cutoff_before", "cutoff_after",
        "reject_reason_before", "reject_reason_after", "change_source",
    }
    assert [row["change_source"] for row in first["apps"]] == ["data", "logic"]
    assert client.get(url, params={"search": "MINI-006"}).json()["apps"][0]["pd_model_after"] is None


def test_attributes_sort_filter_and_paginate(client, ready_run):
    url = f"{ready_run}/apps/MINI-001/attributes"
    response = client.get(url)
    assert response.status_code == 200
    data = response.json()
    assert (data["app_id"], data["page"], data["size"], data["total"]) == ("MINI-001", 1, 100, 14)
    rows = data["attributes"]
    assert rows == sorted(rows, key=lambda row: (-row["diff_flag"], row["path"]))
    assert type(rows[0]["diff_flag"]) is int and rows[0]["array_key"] is None
    assert set(rows[0]) == {
        "path", "array_key", "key", "value_before", "value_after",
        "adjusted_before", "adjusted_after", "diff_flag", "change_type",
    }
    new = next(row for row in rows if row["change_type"] == "ATTRIBUTE_NEW")
    lost = next(row for row in rows if row["change_type"] == "ATTRIBUTE_LOST")
    assert new["value_before"] is new["adjusted_before"] is None
    assert lost["value_after"] is lost["adjusted_after"] is None
    assert new["array_key"] == lost["array_key"] == "101"

    params = {"only_diff": "1", "search": "PRODUCT_TRIALS[]", "size": 2}
    first, second = [client.get(url, params={**params, "page": page}).json() for page in (1, 2)]
    assert first["total"] == second["total"] == 4
    assert first["attributes"] + second["attributes"] == [
        row for row in rows if row["diff_flag"] == 1 and "product_trials[]" in row["path"]
    ]


@pytest.mark.parametrize(("path", "params", "code"), [
    ("apps", {"sort": "-unknown"}, "bad_file"),
    ("apps", {"page": 0}, "bad_request"),
    ("apps", {"size": 501}, "bad_request"),
    ("apps/MINI-001/attributes", {"size": 501}, "bad_request"),
])
def test_invalid_results_query(client, ready_run, path, params, code):
    response = client.get(f"{ready_run}/{path}", params=params)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["message"]


def test_foreign_run_and_unknown_application(client, ready_run):
    for path in RESULT_PATHS:
        response = client.get(f"{ready_run}/{path}", headers={"X-User": "bob"})
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    for url in (f"{ready_run}/apps/unknown/attributes", "/api/runs/r_missing/summary"):
        response = client.get(url)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


def test_results_require_ready(client, monkeypatch):
    monkeypatch.setattr(pipeline_stub, "STAGE_SECONDS", 5)
    url = start_run(client)
    try:
        for path in RESULT_PATHS:
            response = client.get(f"{url}/{path}")
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "not_ready"
    finally:
        client.post(f"{url}/cancel")
