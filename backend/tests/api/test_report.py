import time

import pytest
from fastapi.testclient import TestClient

from app import pipeline_stub, settings
from app.main import create_app
from app.services import warmup
from pipeline.csvio import read_csv, write_csv

CONFIG_NAME = "<script>alert(1)</script>"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATASETS_DIR", tmp_path / "missing")
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(settings, "USE_STUB_PIPELINE", True)
    monkeypatch.setattr(pipeline_stub, "STAGE_SECONDS", 0)
    return TestClient(create_app(), headers={"X-User": "ann"})


def start_run(client):
    config = client.post("/api/configs", json={"name": CONFIG_NAME, "dataset": "RUN-MINI"})
    assert config.status_code == 201
    started = client.post("/api/runs", json={"config_id": config.json()["id"]})
    assert started.status_code == 202
    return started.json()["id"]


@pytest.fixture
def ready_id(client):
    run_id = start_run(client)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = client.get(f"/api/runs/{run_id}").json()
        if status["status"] == "ready":
            return run_id
        assert status["status"] != "error", status
        time.sleep(0.02)
    pytest.fail("Запуск не дошёл до ready")


def test_report_view_and_download(client, ready_id):
    url = f"/api/runs/{ready_id}/report"
    headers = {
        "Host": "backend:8000",
        "X-Forwarded-Host": "localhost:3000, backend:8000",
        "X-Forwarded-Proto": "http, http",
    }
    page = client.get(url, headers=headers)
    download = client.get(url + ".html", headers=headers)
    assert page.status_code == download.status_code == 200
    assert page.headers["content-type"] == download.headers["content-type"] == "text/html; charset=utf-8"
    assert "content-disposition" not in page.headers
    assert download.headers["content-disposition"] == f'attachment; filename="report-{ready_id}.html"'
    assert page.headers["cache-control"] == "private, no-store"
    assert page.content == download.content
    assert f'href="http://localhost:3000/runs/{ready_id}"' in page.text
    assert "RUN-MINI · BEFORE = MASTER, AFTER = BETA" in page.text
    assert '<dd class="value">6</dd>' in page.text
    assert '<dd class="value">4</dd>' in page.text
    assert '<dd class="value">3</dd>' in page.text
    assert '<dd class="value">16</dd>' in page.text
    assert "66,7 % от прогона" in page.text
    assert "Проверки не подключены" in page.text
    assert CONFIG_NAME not in page.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page.text


def test_report_links_use_forwarded_scheme_and_reject_malformed_host(client, ready_id):
    url = f"/api/runs/{ready_id}/report"
    secure = client.get(url, headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "example.org"})
    assert f'href="https://example.org/runs/{ready_id}"' in secure.text

    malformed = client.get(url, headers={
        "Host": "localhost:3000",
        "X-Forwarded-Proto": "javascript",
        "X-Forwarded-Host": 'example.org" onmouseover="alert(1)',
    })
    assert malformed.status_code == 200
    assert f'href="http://localhost:3000/runs/{ready_id}"' in malformed.text
    assert "onmouseover" not in malformed.text


def test_report_uses_only_top_20_apps(client, ready_id):
    path = settings.DATA_DIR / "runs" / ready_id / "apps.csv"
    row = read_csv(path).iloc[0].to_dict()
    write_csv(path, list(row), [
        {**row, "app_id": f"APP-{count:02d}", "attributes_changed": count}
        for count in range(25)
    ])
    warmup.reset()  # файл готового запуска переписали — кэш, прогретый к ready, устарел
    page = client.get(f"/api/runs/{ready_id}/report")
    assert page.status_code == 200
    expected = [f"<code>APP-{count:02d}</code>" for count in range(24, 4, -1)]
    positions = [page.text.index(label) for label in expected]
    assert positions == sorted(positions)
    assert "<code>APP-04</code>" not in page.text
    assert '<dd class="value">16</dd>' in page.text


def test_report_includes_fail_after_first_500_checks(client, ready_id):
    columns = ["LABEL", "SOURCE", "ARGUMENT", "CNT", "TOTAL", "METRIC", "RESULT", "CONFIDENCE", "APP_IDS"]
    row = dict(zip(columns, ["PASS", "AFTER", "", "1", "1", "", "PASS", "HIGH", ""]))
    rows = [{**row, "LABEL": f"PASS-{i}"} for i in range(500)]
    rows.append({**row, "LABEL": "LAST-FAIL", "RESULT": "FAIL"})
    write_csv(settings.DATA_DIR / "runs" / ready_id / "checks.csv", columns, rows)
    page = client.get(f"/api/runs/{ready_id}/report")
    assert page.status_code == 200
    assert "LAST-FAIL" in page.text and "PASS-499" in page.text
    assert page.text.index("LAST-FAIL") < page.text.index("PASS-0")


@pytest.mark.parametrize("suffix", ("report", "report.html"))
def test_report_requires_owner(client, ready_id, suffix):
    for run_id in (ready_id, "r_unknown"):
        response = client.get(f"/api/runs/{run_id}/{suffix}", headers={"X-User": "bob"})
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
        assert "content-disposition" not in response.headers


def test_report_requires_ready(client, monkeypatch):
    monkeypatch.setattr(pipeline_stub, "STAGE_SECONDS", 5)
    url = f"/api/runs/{start_run(client)}"
    try:
        for suffix in ("report", "report.html"):
            response = client.get(f"{url}/{suffix}")
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "not_ready"
            assert "content-disposition" not in response.headers
    finally:
        client.post(f"{url}/cancel")


def test_report_shows_dataset_labels(client, ready_id, monkeypatch):
    # у загруженного датасета метки срезов свои — в отчёте они, а не зашитые MASTER/BETA
    from app.services import datasets
    real = datasets.get_dataset
    monkeypatch.setattr(datasets, "get_dataset", lambda ds_id: {**real(ds_id), "sources": {"BEFORE": "v1", "AFTER": "v2"}})
    page = client.get(f"/api/runs/{ready_id}/report")
    assert "RUN-MINI · BEFORE = v1, AFTER = v2" in page.text
    assert "MASTER" not in page.text
