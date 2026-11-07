"""Регрессия на эталон организаторов (G2): цифры приёмки по настоящему датасету.

Числа зашиты в тест, файлы эталона не читаем и не коммитим. Запуск: `pytest -m slow`.
Если тест упал — цифры не подгоняем, а сообщаем владельцу последнего коммита в backend/pipeline/.
"""

import pytest

from tests.api.test_real_pipeline import ANN, make_client, wait
from tests.real_dataset import REAL

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (REAL / "manifest.json").exists(), reason="нет настоящего датасета"),
]


def test_summary_matches_reference(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, REAL)
    dataset = client.get("/api/datasets", headers=ANN).json()["datasets"][0]["id"]
    cfg = client.post("/api/configs", json={"name": "эталон", "dataset": dataset}, headers=ANN).json()
    rid = client.post("/api/runs", json={"config_id": cfg["id"]}, headers=ANN).json()["id"]
    data = wait(client, rid, {"ready", "error"}, timeout=600)
    assert data["status"] == "ready", data["error"]

    summary = client.get(f"/api/runs/{rid}/summary", headers=ANN).json()
    assert summary["applications"] == 2002
    assert summary["applications_changed"] == 502
    assert summary["decision_changed"] == 385
    assert summary["decision_changes"]["approve_to_reject"] == 273
    assert summary["decision_changes"]["reject_to_approve"] == 112
