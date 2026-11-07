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


# --- проверка процентов (QA №1) ---

SHARES = {
    "applications": 2002, "decision_changed": 385, "decision_changed_share": 0.192,
    "applications_changed": 502, "applications_changed_share": 0.251,
    "reasons": {"top": [{"share_of_product_rows": 0.4}]},
}


def test_check_percents_removes_wrong_share_of_385():
    text = "Итог: решение сменили 385 заявок — 25,1% от 2002.\nДоля data 40%."
    assert ai_review.check_percents(text, SHARES) == "Доля data 40%."


def test_check_percents_keeps_correct_numbers():
    text = "Итог: решение сменили 385 заявок (19,2%), различия у 502 (25,1%).\nПричина — 40,0% строк."
    assert ai_review.check_percents(text, SHARES) == text


def test_check_percents_accepts_rounded_integer_and_sentence_end():
    assert ai_review.check_percents("Решение сменили 385 заявок (19 %).", SHARES) == "Решение сменили 385 заявок (19 %)."
    assert ai_review.check_percents("Это около 19 % заявок, всего 385.", SHARES) != ""
    assert ai_review.check_percents("Решение сменили 385 — 25,1 %.", SHARES) == ""
    assert ai_review.check_percents("Сменили 385, это 25 %.", SHARES) == ""


def test_check_percents_drops_only_bad_sentence_in_line():
    text = "Решение сменили 385 заявок (19,2%). Это 77% всех заявок."
    assert ai_review.check_percents(text, SHARES) == "Решение сменили 385 заявок (19,2%)."


def test_check_percents_cleans_raw_names_fractions_and_codes():
    text = ("Итог: Решение изменилось у 385 заявок (decision_changed_share 0.192).\n"
            "Подозрительно: логика объясняет 0.566 смен. Переход approve_to_reject у 273 заявок. "
            "Атрибутов ATTRIBUTE_NEW много (4108).\n"
            "Доля заявок со сменой решения — 19,2 %.")
    cleaned = ai_review.check_percents(text, SHARES)
    assert "decision_changed_share" not in cleaned and "0.192" not in cleaned and "0.566" not in cleaned
    assert "Переход Одобрение → отказ у 273 заявок." in cleaned
    assert "Атрибутов Атрибут появился много (4108)." in cleaned
    assert "19,2 %" in cleaned


def test_model_gets_percent_strings_and_russian_labels():
    shown = ai_review.for_model({
        "decision_changed_share": 0.192, "decision_changes": {"approve_to_reject": 273, "same": 5},
        "reasons": {"top": [{"share_of_product_rows": 0.425}], "by_source_share_of_decision_changed": {"logic": 0.566}},
    })
    text = json.dumps(shown, ensure_ascii=False)
    assert "19,2 %" in text and "42,5 %" in text and "56,6 %" in text
    assert "approve_to_reject" not in text and "Одобрение → отказ" in text and "_share" not in text
    assert "0.192" not in text


def test_input_has_ready_shares(client, ready_id):
    run_dir = settings.DATA_DIR / "runs" / ready_id
    data, _ = ai_review.build_input(run_dir, settings.DATASETS_DIR / "missing")
    assert data["decision_changed_share"] == round(data["decision_changed"] / data["applications"], 3)
    assert "applications_changed_share" in data
    assert "не вычисляй проценты" in ai_review.SYSTEM_PROMPT.lower()
