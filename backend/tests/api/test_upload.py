import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import settings
from app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(settings, "DATASETS_DIR", tmp_path / "none")
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path / "var")
    return TestClient(create_app(), raise_server_exceptions=False)


def app_json(app_id, decision, request_id):
    return json.dumps({"appData": {"application_id": app_id, "request_id": request_id},
                       "decisionResult": {"decision": decision, "available_offers": []}})


def app_xml(app_id, decision, request_id):
    return (f"<r><appData><application_id>{app_id}</application_id><request_id>{request_id}</request_id></appData>"
            f"<decisionResult><decision>{decision}</decision><available_offers/></decisionResult></r>")


def app_csv(app_id, decision, request_id):
    return (f"path;value\nappData.application_id;{app_id}\nappData.request_id;{request_id}\n"
            f"decisionResult.decision;{decision}\ndecisionResult.available_offers;[]\n")


def test_upload_mixed_formats_creates_dataset_listed_in_api(client):
    before = [(f"I{n}.json", app_json(f"I{n}", "APPROVE", f"b{n}"), "application/json") for n in range(1, 4)]
    after = [("I1.xml", app_xml("I1", "REJECT", "a1"), "text/xml"), ("I2.csv", app_csv("I2", "APPROVE", "a2"), "text/csv"),
             ("I3.json", app_json("I3", "APPROVE", "a3"), "application/json")]
    files = [("before", f) for f in before] + [("after", f) for f in after]
    r = client.post("/api/datasets/upload", files=files, data={"before_label": "MASTER", "after_label": "BETA"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["dataset"]["applications"] == 3
    assert body["dataset"]["sources"] == {"BEFORE": "MASTER", "AFTER": "BETA"}
    assert body["dataset"]["technical_fields"] == ["appData.request_id"]  # отличается у всех трёх пар
    assert body["received"]["AFTER"] == {"applications": 3, "json": 1, "xml": 1, "csv": 1}
    assert body["applications_only_before"] == 0

    ids = [d["id"] for d in client.get("/api/datasets").json()["datasets"]]
    assert body["dataset"]["id"] in ids


def test_upload_zip_and_only_one_side_apps(client):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for n in (1, 2):
            zf.writestr(f"x/I{n}.json", app_json(f"I{n}", "APPROVE", f"b{n}"))
    after = ("I1.json", app_json("I1", "APPROVE", "a1"), "application/json")
    r = client.post("/api/datasets/upload", files=[("before", ("b.zip", buf.getvalue(), "application/zip")), ("after", after)])
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body["applications_only_before"], body["applications_only_after"]) == (1, 0)
    assert body["dataset"]["sources"] == {"BEFORE": "BEFORE", "AFTER": "AFTER"}
    assert body["dataset"]["technical_fields"] == []  # пар меньше трёх — не угадываем


def test_upload_writes_dataset_in_the_organizers_layout(client):
    client.post("/api/datasets/upload", files=[("before", ("I1.json", app_json("I1", "APPROVE", "b"), "application/json")),
                                               ("after", ("I1.xml", app_xml("I1", "REJECT", "a"), "text/xml"))])
    folder = next(p for p in settings.UPLOADS_DIR.iterdir())
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["srez"]["AFTER"]["dir"] == "RESULTS/AFTER_AFTER"
    doc = json.loads((folder / "RESULTS/AFTER_AFTER/I1.json").read_text(encoding="utf-8"))
    assert doc["decisionResult"] == {"decision": "REJECT", "available_offers": []}


@pytest.mark.parametrize("files, code, text", [
    ([("before", ("I1.json", "{}", "x"))], "bad_request", "after"),
    ([("before", ("I1.txt", "x", "x")), ("after", ("I1.json", "{}", "x"))], "bad_request", "нужен .json"),
    ([("before", ("I1.json", "{oops", "x")), ("after", ("I1.json", "{}", "x"))], "bad_file", "I1.json"),
    ([("before", ("a.json", app_json("I1", "A", "1"), "x")), ("before", ("b.json", app_json("I1", "A", "1"), "x")),
      ("after", ("I1.json", "{}", "x"))], "bad_file", "дважды"),
])
def test_upload_errors(client, files, code, text):
    r = client.post("/api/datasets/upload", files=files)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == code
    assert text in r.json()["error"]["message"]
    assert not settings.UPLOADS_DIR.exists() or list(settings.UPLOADS_DIR.iterdir()) == []  # ничего не сохранили


def test_run_on_uploaded_dataset_finds_its_folder(client):
    """Регресс: запуск искал датасет только в DATASETS_DIR и не находил загруженный."""
    from app.services import runs
    body = client.post("/api/datasets/upload", files=[("before", ("I1.json", app_json("I1", "APPROVE", "b"), "x")),
                                                      ("after", ("I1.xml", app_xml("I1", "REJECT", "a"), "x"))]).json()
    ds_id = body["dataset"]["id"]
    run = {"dataset": ds_id, "dataset_folder": ds_id}
    assert runs.dataset_path(run) == settings.UPLOADS_DIR / ds_id
    assert (runs.dataset_path(run) / "manifest.json").is_file()


def test_same_labels_are_rejected(client):
    r = client.post("/api/datasets/upload", files=[("before", ("I1.json", "{}", "x")), ("after", ("I1.json", "{}", "x"))],
                    data={"before_label": "X", "after_label": "X"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_request"


def test_xml_single_tag_is_list_when_other_side_has_list(client):
    # appData.tags — список из одного элемента в JSON и одиночный тег в XML: без общего правила срезы не сравнятся
    before = {"appData": {"application_id": "I1", "tags": ["web"]}, "decisionResult": {"decision": "APPROVE"}}
    after = ('<response><appData><application_id>I1</application_id><tags>web</tags></appData>'
             '<decisionResult><decision>APPROVE</decision></decisionResult></response>')
    r = client.post("/api/datasets/upload", files=[
        ("before", ("I1.json", json.dumps(before), "application/json")),
        ("after", ("I1.xml", after, "text/xml")),
    ])
    assert r.status_code == 201, r.text
    folder = next(p for p in settings.UPLOADS_DIR.iterdir())
    doc = json.loads((folder / "RESULTS/AFTER_AFTER/I1.json").read_text(encoding="utf-8"))
    assert doc["appData"]["tags"] == ["web"]
