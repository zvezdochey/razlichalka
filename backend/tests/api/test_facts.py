import csv
import io
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import pipeline_stub, settings
from app.main import create_app
from app.services import facts as facts_service
from app.services import warmup
from app.services.facts import make_apps_ref
from pipeline.csvio import read_csv, write_csv

OWNER = {"X-User": "ann"}
ENDPOINTS = ("facts?dims=PATH", "facts/f_missing/apps", "export.csv")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATASETS_DIR", tmp_path / "missing")
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(settings, "USE_STUB_PIPELINE", True)
    monkeypatch.setattr(pipeline_stub, "STAGE_SECONDS", 0)
    return TestClient(create_app(), headers=OWNER)


def start_run(client, dataset="RUN-MINI"):
    config = client.post("/api/configs", json={"name": "Факты", "dataset": dataset})
    assert config.status_code == 201
    started = client.post("/api/runs", json={"config_id": config.json()["id"]})
    assert started.status_code == 202
    return started.json()["id"]


def wait_ready(client, run_id):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}").json()
        if response["status"] == "ready":
            return
        assert response["status"] != "error", response
        time.sleep(0.02)
    pytest.fail("Запуск не дошёл до ready")


@pytest.fixture
def run(client):
    run_id = start_run(client)
    wait_ready(client, run_id)
    return run_id


def get_facts(client, run, **params):
    response = client.get(f"/api/runs/{run}/facts", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_groups_count_rows_and_limit(client, run):
    with (settings.STUB_RUN_DIR / "comparison.csv").open(encoding="utf-8-sig") as f:
        expected = Counter(row["CHANGE_TYPE"] for row in csv.DictReader(f, delimiter=";"))
    actual = get_facts(client, run, dims="CHANGE_TYPE")
    assert actual["dims"] == ["CHANGE_TYPE"]
    assert actual["total_groups"] == len(expected)
    assert {r["CHANGE_TYPE"]: r["counts"] for r in actual["rows"]} == expected
    assert [r["counts"] for r in actual["rows"]] == sorted(expected.values(), reverse=True)
    limited = get_facts(client, run, dims="CHANGE_TYPE", limit=1)
    assert limited == {**actual, "rows": actual["rows"][:1]}


def test_group_links_apply_all_conditions_and_survive_restart(client, run):
    params = {
        "dims": "DECISION_CHANGED,DIFF_FLAG",
        "filter": "DIFF_FLAG:1;CHANGE_TYPE:VALUE_CHANGED,ATTRIBUTE_NEW",
        "measure": "counts_distinct_apps",
    }
    data = get_facts(client, run, **params)
    group = next(r for r in data["rows"] if r["DECISION_CHANGED"] == "1")
    assert group["DIFF_FLAG"] == 1 and group["counts"] == 3
    assert group["app_ids_ref"].startswith("f_") and len(group["app_ids_ref"]) == 14
    assert get_facts(client, run, **params) == data

    restarted = TestClient(create_app(), headers=OWNER)
    url = f"/api/runs/{run}/facts/{group['app_ids_ref']}/apps"
    first = restarted.get(url, params={"size": 2}).json()
    second = restarted.get(url, params={"size": 2, "page": 2}).json()
    assert first["total"] == second["total"] == 3
    assert first["apps"] + second["apps"] == ["MINI-001", "MINI-002", "MINI-005"]


def test_empty_values_are_null_and_drillable(client, run):
    data = get_facts(client, run, dims="ARRAY_KEY_1", filter="ARRAY_KEY_1:")
    assert data["total_groups"] == 1
    group = data["rows"][0]
    assert group["ARRAY_KEY_1"] is None
    ref = group["app_ids_ref"]
    assert client.get(f"/api/runs/{run}/facts/{ref}/apps").json()["total"] == 6


def test_explicit_app_ids_and_concurrent_ref_writes(client, run):
    run_dir = settings.DATA_DIR / "runs" / run
    ids = [[f"MINI-{index:03}", "MINI-002", "MINI-002"] for index in range(1, 7)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        refs = list(pool.map(lambda group: make_apps_ref(run_dir, group), ids))
    for ref, group in zip(refs, ids):
        data = client.get(f"/api/runs/{run}/facts/{ref}/apps").json()
        assert data["apps"] == sorted(set(group))


@pytest.mark.parametrize("params", [
    {"dims": "UNKNOWN"},
    {"dims": "PATH,PATH"},
    {"dims": "PATH,KEY,CLASS,PREFIX"},
    {"dims": "PATH", "filter": "UNKNOWN:1"},
    {"dims": "PATH", "filter": "PATH"},
    {"dims": "PATH", "filter": "PATH:a;"},
    {"dims": "PATH", "filter": "DIFF_FLAG:2"},
    {"dims": "PATH", "filter": "DIFF_FLAG:1,2"},
    {"dims": "PATH", "filter": "DIFF_FLAG:"},
    {"dims": "PATH", "measure": "invalid"},
    {"dims": "PATH", "limit": 5001},
])
def test_bad_facts_queries(client, run, params):
    response = client.get(f"/api/runs/{run}/facts", params=params)
    assert response.status_code == 400
    # limit вне диапазона ловит проверка запроса FastAPI, остальное — сервис фактов
    expected = "bad_request" if params.get("limit") == 5001 else "bad_file"
    assert response.json()["error"]["code"] == expected


def test_results_require_owner_and_ready(client, monkeypatch):
    monkeypatch.setattr(pipeline_stub, "STAGE_SECONDS", 5)
    run_id = start_run(client)
    try:
        for endpoint in ENDPOINTS:
            url = f"/api/runs/{run_id}/{endpoint}"
            assert client.get(url).json()["error"]["code"] == "not_ready"
            assert client.get(url, headers={"X-User": "bob"}).status_code == 404
            assert client.get(f"/api/runs/r_unknown/{endpoint}").status_code == 404
    finally:
        client.post(f"/api/runs/{run_id}/cancel")


def test_csv_reuses_app_filters_and_ignores_pagination(client, run):
    url = f"/api/runs/{run}"
    params = {
        "decision_change": "approve_to_reject",
        "has_attr_change": 1,
        "search": "standard",
        "sort": "-attributes_changed",
    }
    apps = client.get(f"{url}/apps", params=params).json()["apps"]
    response = client.get(f"{url}/export.csv", params={**params, "size": 1, "page": 2})
    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == f'attachment; filename="apps-{run}.csv"'
    assert response.content.startswith(b"\xef\xbb\xbf")
    records = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
    assert [row["app_id"] for row in records] == [app["app_id"] for app in apps] == ["MINI-001", "MINI-005"]
    assert [int(row["attributes_changed"]) for row in records] == [12, 1]
    assert client.get(f"{url}/export.csv", params={"sort": "unknown"}).status_code == 400

    missing = client.get(f"{url}/facts/f_missing/apps")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_facts_read_artifacts_of_real_pipeline(client, monkeypatch):
    monkeypatch.setattr(settings, "DATASETS_DIR", settings.BACKEND_DIR / "tests" / "fixtures")
    monkeypatch.setattr(settings, "USE_STUB_PIPELINE", False)
    run_id = start_run(client, "MINI-0001")
    wait_ready(client, run_id)
    data = get_facts(client, run_id, dims="ARRAY_KEY_1,DECISION_CHANGED", measure="counts_distinct_apps")
    assert data["total_groups"] > 0
    assert all(1 <= row["counts"] <= 3 for row in data["rows"])


def test_csv_exports_formula_like_cells_as_text(client, run):
    path = settings.DATA_DIR / "runs" / run / "apps.csv"
    apps = read_csv(path)
    apps.loc[0, "pd_model_before"] = " =1+1"
    write_csv(path, list(apps.columns), apps.to_dict("records"))
    warmup.reset()  # файл готового запуска переписали — кэш, прогретый к ready, устарел

    url = f"/api/runs/{run}"
    response = client.get(f"{url}/export.csv")
    rows = csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";")
    assert next(rows)["pd_model_before"] == "' =1+1"
    assert client.get(f"{url}/apps").json()["apps"][0]["pd_model_before"] == " =1+1"


def test_empty_filter_matches_unfiltered_facts(client, run):
    assert get_facts(client, run, dims="PATH", filter="") == get_facts(client, run, dims="PATH")


def test_ref_storage_keeps_recent_groups_and_explicit_ids(client, run, monkeypatch):
    monkeypatch.setattr(facts_service, "_MAX_GROUP_REFS", 2)
    run_dir = settings.DATA_DIR / "runs" / run
    durable = make_apps_ref(run_dir, ["MINI-002"])

    def ref_for(change_type):
        data = get_facts(client, run, dims="CHANGE_TYPE", filter=f"CHANGE_TYPE:{change_type}")
        return data["rows"][0]["app_ids_ref"]

    same = ref_for("SAME")
    changed = ref_for("VALUE_CHANGED")
    assert ref_for("SAME") == same
    new = ref_for("ATTRIBUTE_NEW")

    url = f"/api/runs/{run}/facts"
    assert client.get(f"{url}/{changed}/apps").status_code == 404
    for ref in (same, new, durable):
        assert client.get(f"{url}/{ref}/apps").status_code == 200
    assert client.get(f"{url}/{durable}/apps").json()["apps"] == ["MINI-002"]
    assert not (run_dir / "facts_refs.json").exists()


def test_legacy_json_refs_still_work(client, run):
    run_dir = settings.DATA_DIR / "runs" / run
    ref = "f_000000000001"
    (run_dir / "facts_refs.json").write_text(
        json.dumps({ref: {"app_ids": ["MINI-001"]}}), encoding="utf-8",
    )

    get_facts(client, run, dims="CHANGE_TYPE")
    response = client.get(f"/api/runs/{run}/facts/{ref}/apps")
    assert response.status_code == 200
    assert response.json()["apps"] == ["MINI-001"]
