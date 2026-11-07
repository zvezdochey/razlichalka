import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

import pytest
from fastapi.testclient import TestClient

from app import pipeline_stub, settings
from app.main import create_app
from app.services import app_card, reasons

OWNER = {"X-User": "ann"}
DATASET = "MINI-0001"


def test_card_fields_reuses_map_until_procedure_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROCEDURES_DIR", tmp_path)
    procedure = tmp_path / "builtin_segments.py"
    procedure.write_text("FIELD_MAP = {'PD_VALUE': 'custom.path'}\n", encoding="utf-8")

    fields = app_card.card_fields()
    assert fields["PD_VALUE"] == "custom.path"
    assert app_card.card_fields() is fields

    procedure.write_text("FIELD_MAP = {'PD_VALUE': 'updated.custom.path'}\n", encoding="utf-8")
    assert app_card.card_fields()["PD_VALUE"] == "updated.custom.path"


def product(product_id, decision, *, model=None, pd=None, cutoff=None, reason=None, code=None, rules=()):
    return {
        "product_id": product_id,
        "decision": decision,
        "scoring": {"pd": {"modelName": model, "value": pd}},
        "cutOff": {"name": cutoff[0], "value": cutoff[1]} if cutoff else None,
        "rejectReason": reason,
        "rejectReasonCode": code,
        "rules": [{"name": name, "hit": hit} for name, hit in rules],
    }


def write_response(folder, app_id, decision, products, *, offers=(), input_score=10):
    doc = {
        "appData": {"application_id": app_id, "input_score": input_score},
        "decisionResult": {
            "decision": decision,
            "product_trials": products,
            "available_offers": [
                {"product_id": product_id, "type": kind, "rank": rank}
                for rank, (product_id, kind) in enumerate(offers, 1)
            ],
        },
    }
    (folder / f"{app_id}.json").write_text(json.dumps(doc), encoding="utf-8")


@pytest.fixture
def dataset(tmp_path):
    target = tmp_path / "datasets" / "другое-имя"
    shutil.copytree(settings.BACKEND_DIR / "tests" / "fixtures" / "dataset_mini", target)
    before, after = (target / "RESULTS" / name for name in ("BEFORE", "AFTER"))
    write_response(before, "A1", "REJECT", [
        product(1, "REJECT", model="V1", rules=[("STOP_A1", True), ("NOT_RUN", None)]),
        product(2, "REJECT"),
    ])
    write_response(after, "A1", "APPROVE", [
        product("1", "APPROVE", model="V1", rules=[("STOP_A1", False)]),
        product(2, "APPROVE"),
        product("001", "APPROVE"),
    ], offers=[(1, "standard"), (1, "manual"), ("001", "standard")])
    write_response(before, "A2", "APPROVE", [
        product(1, "APPROVE", model="V1", pd=0.4, cutoff=("OLD", 0.55)),
        product(2, "APPROVE", model="V2", pd=0.4, cutoff=("CUT_HIGH", 0.62)),
        product(3, "APPROVE", rules=[("STOP_A2", False)]),
    ])
    write_response(after, "A2", "REJECT", [
        product(1, "REJECT", model="V2", pd=0.7, cutoff=("CUT_HIGH", 0.62), reason="CUTOFF", code="CUT_HIGH"),
        product(2, "REJECT", model="V2", pd=0.7, cutoff=("CUT_HIGH", 0.62), reason="CUTOFF", code="CUT_HIGH"),
        product(3, "REJECT", reason="HARDCHECK", code="STOP_A2", rules=[("STOP_A2", True)]),
    ], input_score=11)
    write_response(before, "A3", "APPROVE", [product(1, "OTHER")])
    write_response(after, "A3", "REJECT", [product(1, "OTHER")])
    return target


@pytest.fixture
def client(tmp_path, monkeypatch, dataset):
    monkeypatch.setattr(settings, "DATASETS_DIR", dataset.parent)
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(settings, "USE_STUB_PIPELINE", False)
    return TestClient(create_app(), headers=OWNER)


def start(client):
    config = client.post("/api/configs", json={"name": "I3", "dataset": DATASET})
    assert config.status_code == 201, config.text
    response = client.post("/api/runs", json={"config_id": config.json()["id"]})
    assert response.status_code == 202, response.text
    return f"/api/runs/{response.json()['id']}"


@pytest.fixture
def run(client):
    url = start(client)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = client.get(url).json()
        if state["status"] == "ready":
            return url
        assert state["status"] != "error", state
        time.sleep(0.02)
    pytest.fail("Запуск не дошёл до ready")


def test_app_card_keeps_offers_and_fields_for_each_product(client, run):
    response = client.get(f"{run}/apps/A1")
    assert response.status_code == 200, response.text
    card = response.json()
    assert card["app_id"] == "A1" and card["decision_change"] == "reject_to_approve"
    assert card["before"]["decision"] == "reject" and card["after"]["decision"] == "approve"
    assert card["after"]["offers"] == [
        {"product_id": 1, "type": "standard"},
        {"product_id": 1, "type": "manual"},
        {"product_id": "001", "type": "standard"},
    ]
    first, second = card["before"]["products"]
    assert first["rules"] == [{"name": "STOP_A1", "hit": True}, {"name": "NOT_RUN", "hit": None}]
    assert first["pd_model"] == "V1" and second["pd_model"] is None
    assert first["cutoff"] == {"name": None, "value": None}
    assert first["reject_reason_code"] is None
    assert card["after"]["products"][0]["rules"] == [{"name": "STOP_A1", "hit": False}]
    assert card["reasons"] == [
        {"text": "Стоп-фактор STOP_A1 сработал в BEFORE, в AFTER не сработал", "source": "rule", "confidence": "high"},
        {"text": "Продукт 001 появился в AFTER", "source": "product", "confidence": "high"},
    ]


def test_cutoff_model_crossing_data_and_unknown(client, run):
    response = client.get(f"{run}/apps/A2")
    assert response.status_code == 200, response.text
    card = response.json()
    assert card["decision_change"] == "approve_to_reject"
    changes = {(reason["source"], reason["text"]): reason["confidence"] for reason in card["reasons"]}
    assert changes["cutoff", "Порог OLD → CUT_HIGH (0.55 → 0.62)"] == "high"
    assert changes["score", "Модель PD сменилась: V1 → V2"] == "high"
    assert changes["score", "PD 0.4 → 0.7 при пороге 0.62"] == "high"
    assert any(source == "data" and confidence == "low" for (source, _), confidence in changes.items())

    unknown = client.get(f"{run}/apps/A3").json()["reasons"]
    assert len(unknown) == 1 and unknown[0]["source"] == "unknown" and unknown[0]["confidence"] == "low"


def test_aggregate_counts_products_and_links_unique_apps(client, run):
    response = client.get(f"{run}/reasons")
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["unexplained"] == 1
    assert report["by_source"] == {"logic": 2, "data": 1, "both": 0}
    cutoff, rule = report["reasons"]
    assert cutoff["rule"] == "CUT_HIGH" and cutoff["affected"] == 2 and cutoff["share"] == 0.667
    assert rule["rule"] == "STOP_A2" and rule["affected"] == 1 and rule["share"] == 0.333
    for item in (cutoff, rule):
        path = f"{run}/facts/{item['app_ids_ref']}/apps"
        assert client.get(path).json() == {"page": 1, "size": 50, "total": 1, "apps": ["A2"]}


def test_concurrent_reasons_requests_read_each_slice_once(client, run, monkeypatch):
    first_read = Event()
    second_request = Event()
    finish_read = Event()
    lock = Lock()
    reads = []
    read_slice = app_card.read_slice

    class ObservedLock:
        def __enter__(self):
            if lock.locked():
                second_request.set()
            lock.acquire()

        def __exit__(self, *_):
            lock.release()

    def paused_read(path, fields):
        reads.append(path.stem)
        first_read.set()
        assert finish_read.wait(5)
        return read_slice(path, fields)

    monkeypatch.setattr(reasons, "_lock", ObservedLock())
    monkeypatch.setattr(app_card, "read_slice", paused_read)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.get, f"{run}/reasons")
        try:
            assert first_read.wait(5)
            second = pool.submit(client.get, f"{run}/reasons")
            assert second_request.wait(5)
        finally:
            finish_read.set()
        responses = [request.result(timeout=5) for request in (first, second)]

    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    assert reads == ["A2", "A3"]


def test_not_found_for_foreign_unknown_or_missing_slice(client, run, dataset):
    for suffix in ("apps/A1", "reasons"):
        response = client.get(f"{run}/{suffix}", headers={"X-User": "bob"})
        assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"
    assert client.get(f"{run}/apps/not-in-run").status_code == 404
    (dataset / "RESULTS" / "AFTER" / "A1.json").unlink()
    response = client.get(f"{run}/apps/A1")
    assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"


def test_card_and_reasons_wait_until_ready(client, monkeypatch):
    monkeypatch.setattr(settings, "USE_STUB_PIPELINE", True)
    monkeypatch.setattr(pipeline_stub, "STAGE_SECONDS", 5)
    run = start(client)
    try:
        for suffix in ("apps/A1", "reasons"):
            response = client.get(f"{run}/{suffix}")
            assert response.status_code == 409 and response.json()["error"]["code"] == "not_ready"
    finally:
        client.post(f"{run}/cancel")
