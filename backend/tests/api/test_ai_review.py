"""«Мнение ИИ» (docs/api.md п. 12): модель подменяем, в сеть тесты не ходят."""
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app import pipeline_stub, settings
from app.main import create_app
from app.services import ai_review

OPINION = "Итог: решение изменилось у 3 заявок.\nЧто выглядит подозрительно:\n- <script>alert(1)</script>"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATASETS_DIR", tmp_path / "missing")
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(settings, "USE_STUB_PIPELINE", True)
    monkeypatch.setattr(pipeline_stub, "STAGE_SECONDS", 0)
    monkeypatch.setattr(ai_review.time, "sleep", lambda _s: None)  # паузы между повторами не ждём
    ai_review.reset()
    return TestClient(create_app(), headers={"X-User": "ann"})


def start_run(client):
    config = client.post("/api/configs", json={"name": "t", "dataset": "RUN-MINI"})
    return client.post("/api/runs", json={"config_id": config.json()["id"]}).json()["id"]


def wait_ready(client, run_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if client.get(f"/api/runs/{run_id}").json()["status"] == "ready":
            return
        time.sleep(0.02)
    pytest.fail("Запуск не дошёл до ready")


def get_opinion(client, run_id):
    """Ждём, пока фон досчитает: pending -> ready/error."""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        body = client.get(f"/api/runs/{run_id}/ai-review").json()
        if body["status"] != "pending":
            return body
        time.sleep(0.02)
    pytest.fail("Мнение осталось pending")


@pytest.fixture
def ready_id(client):
    run_id = start_run(client)
    wait_ready(client, run_id)
    return run_id


@pytest.fixture
def model(monkeypatch):
    """Ключ задан, httpx.post подменён: calls — все запросы к «модели», reply — что она вернёт."""
    monkeypatch.setattr(settings, "OLLAMA_API_KEY", "test-key")
    state = {"calls": [], "reply": lambda: httpx.Response(200, json={"message": {"content": OPINION}})}

    def post(url, json=None, headers=None, timeout=None):
        state["calls"].append({"url": url, "json": json, "headers": headers})
        reply = state["reply"]()
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(ai_review.httpx, "post", post)
    return state


def test_input_has_only_aggregates(client, ready_id):
    run_dir = settings.DATA_DIR / "runs" / ready_id
    data, inputs = ai_review.build_input(run_dir, settings.DATASETS_DIR / "missing")
    assert inputs[0] == "summary" and "top_changed_attributes" in inputs
    assert data["decision_changed"] == 3 and data["decision_changes"]["approve_to_reject"] == 2
    assert all(row["apps"] >= 1 for row in data["top_changed_attributes"])
    text = json.dumps(data, ensure_ascii=False)
    for forbidden in ("app_ids_ref", "apps_ref", "value_before", "value_after", "APP-"):
        assert forbidden not in text
    assert len(text.encode("utf-8")) < 4096


def test_opinion_is_generated_and_cached(client, model):
    run_id = start_run(client)
    wait_ready(client, run_id)
    body = get_opinion(client, run_id)
    assert body["status"] == "ready"
    assert body["text"] == OPINION
    assert body["model"] == settings.OLLAMA_MODEL
    assert "summary" in body["inputs"] and body["generated_at"].endswith("Z")
    assert len(model["calls"]) == 1
    call = model["calls"][0]
    assert call["url"].endswith("/api/chat") and call["headers"] == {"Authorization": "Bearer test-key"}
    assert call["json"]["stream"] is False
    assert [m["role"] for m in call["json"]["messages"]] == ["system", "user"]
    # повторные запросы берут кэш: модель больше не зовут
    assert client.get(f"/api/runs/{run_id}/ai-review").json() == body
    assert len(model["calls"]) == 1


def test_report_shows_escaped_opinion(client, model):
    run_id = start_run(client)
    wait_ready(client, run_id)
    get_opinion(client, run_id)
    page = client.get(f"/api/runs/{run_id}/report").text
    assert "Мнение ИИ" in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page and "<script>alert(1)</script>" not in page


@pytest.mark.parametrize("reply", [
    httpx.ReadTimeout("slow"),
    httpx.Response(500),
    httpx.Response(429),
    httpx.Response(401),
    httpx.Response(200, json={"message": {"content": "  "}}),
    httpx.Response(200, json={"oops": 1}),
])
def test_model_failure_keeps_run_and_report(client, model, reply):
    model["reply"] = lambda: reply
    run_id = start_run(client)
    wait_ready(client, run_id)
    body = get_opinion(client, run_id)
    assert body["status"] == "error" and body["error"]["code"] == "unavailable"
    assert "test-key" not in json.dumps(body)
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "ready"
    page = client.get(f"/api/runs/{run_id}/report")
    assert page.status_code == 200 and "Мнение ИИ недоступно" in page.text


def test_retries_then_succeeds(client, model):
    answers = iter([httpx.Response(503), httpx.ConnectError("down"), httpx.Response(200, json={"message": {"content": "ок"}})])
    model["reply"] = lambda: next(answers)
    run_id = start_run(client)
    wait_ready(client, run_id)
    assert get_opinion(client, run_id)["text"] == "ок"
    assert len(model["calls"]) == 3


def test_auth_error_is_not_retried(client, model):
    model["reply"] = lambda: httpx.Response(403)
    run_id = start_run(client)
    wait_ready(client, run_id)
    get_opinion(client, run_id)
    assert len(model["calls"]) == 1


def test_no_key_skips_network(client, ready_id, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("без ключа в сеть ходить нельзя")

    monkeypatch.setattr(ai_review.httpx, "post", boom)
    body = client.get(f"/api/runs/{ready_id}/ai-review").json()
    assert body["status"] == "error" and body["error"]["code"] == "unavailable"


def test_error_is_retried_after_a_minute(client, model, monkeypatch):
    model["reply"] = lambda: httpx.Response(500)
    run_id = start_run(client)
    wait_ready(client, run_id)
    assert get_opinion(client, run_id)["status"] == "error"
    calls = len(model["calls"])
    assert client.get(f"/api/runs/{run_id}/ai-review").json()["status"] == "error"
    assert len(model["calls"]) == calls  # сразу повторно не ходим
    monkeypatch.setattr(ai_review, "RETRY_AFTER", 0)
    model["reply"] = lambda: httpx.Response(200, json={"message": {"content": "ок"}})
    assert get_opinion(client, run_id)["text"] == "ок"


def test_requires_ready_and_owner(client, monkeypatch, ready_id):
    assert client.get("/api/runs/r_unknown/ai-review").status_code == 404
    assert client.get(f"/api/runs/{ready_id}/ai-review", headers={"X-User": "bob"}).status_code == 404
    monkeypatch.setattr(pipeline_stub, "STAGE_SECONDS", 5)
    slow = start_run(client)
    try:
        response = client.get(f"/api/runs/{slow}/ai-review")
        assert response.status_code == 409 and response.json()["error"]["code"] == "not_ready"
    finally:
        client.post(f"/api/runs/{slow}/cancel")
