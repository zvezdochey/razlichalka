"""Свои процедуры этапов (приведение, сравнение, факты) правда исполняются в запуске, а не только выбираются."""
import json

from app import settings
from tests.api.test_real_pipeline import ANN, MINI, make_client, wait

BUILTIN_COMPARE = (settings.PROCEDURES_DIR / "builtin_compare.py").read_text(encoding="utf-8")
BUILTIN_SEGMENTS = (settings.PROCEDURES_DIR / "builtin_segments.py").read_text(encoding="utf-8")


def _procedure(client, kind, code):
    r = client.post("/api/procedures", json={"kind": kind, "name": f"моя {kind}", "source": "inline", "code": code},
                    headers=ANN)
    assert r.status_code == 201, r.json()
    return r.json()["id"]


def _run(client, **stages):
    dataset = client.get("/api/datasets", headers=ANN).json()["datasets"][0]["id"]
    r = client.post("/api/configs", json={"name": "c", "dataset": dataset, **stages}, headers=ANN)
    assert r.status_code == 201, r.json()
    rid = client.post("/api/runs", json={"config_id": r.json()["id"]}, headers=ANN).json()["id"]
    return rid, wait(client, rid, {"ready", "error"}, timeout=120)


def test_broken_data_procedure_is_rejected_on_save(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, MINI)
    r = client.post("/api/procedures", json={"kind": "normalize", "name": "x", "source": "inline",
                                             "code": "raise RuntimeError('boom')\nARRAY_RULES = {}\n"}, headers=ANN)
    assert r.status_code == 400 and "boom" in r.json()["error"]["message"]
    r = client.post("/api/procedures", json={"kind": "aggregate", "name": "x", "source": "inline",
                                             "code": "X = 1\n"}, headers=ANN)
    assert r.status_code == 400 and "FIELD_MAP" in r.json()["error"]["message"]


def test_own_compare_changes_the_result(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, MINI)
    _, base = _run(client)
    base_summary = client.get(f"/api/runs/{base['id']}/summary", headers=ANN).json()
    assert base_summary["applications_changed"] > 0

    # «Ничего не различается»: та же процедура, но все строки — SAME
    code = BUILTIN_COMPARE.replace('    return out\n', '    out["CHANGE_TYPE"] = "SAME"\n    return out\n')
    proc_id = _procedure(client, "compare", code)
    rid, data = _run(client, compare=proc_id)
    assert data["status"] == "ready", data["error"]
    assert client.get(f"/api/runs/{rid}/summary", headers=ANN).json()["applications_changed"] == 0

    stage = client.get(f"/api/runs/{rid}/stages", headers=ANN).json()["stages"][1]
    assert stage["procedure_id"] == proc_id and stage["code_ref"]["procedure_id"] == proc_id


def test_own_compare_breaking_contract_fails_the_run(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, MINI)
    code = "def compare(before, after):\n    return before\n\nCOMPARE = {'entrypoint': compare}\n"
    _, data = _run(client, compare=_procedure(client, "compare", code))
    assert data["status"] == "error" and "нет колонок" in data["error"]["message"]


def test_own_normalize_and_aggregate_are_used(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, MINI)
    _, base = _run(client)
    assert client.get(f"/api/runs/{base['id']}/summary", headers=ANN).json()["decision_changed"] > 0
    normalize = _procedure(client, "normalize", "ARRAY_RULES = {}\n")
    # Факты: без пути решения колонка DECISION пустая — видно, что карта полей взята из своей процедуры
    aggregate = _procedure(client, "aggregate",
                           BUILTIN_SEGMENTS.replace('"DECISION": "decisionResult.decision"', '"DECISION": ""'))
    rid, data = _run(client, normalize=normalize, aggregate=aggregate)
    assert data["status"] == "ready", data["error"]

    folder = settings.DATA_DIR / "runs" / rid / "procedures"
    assert "ARRAY_RULES = {}" in (folder / "builtin_normalize.py").read_text(encoding="utf-8")
    summary = json.loads((settings.DATA_DIR / "runs" / rid / "summary.json").read_text(encoding="utf-8"))
    assert summary["decision_changed"] == 0
    stages = client.get(f"/api/runs/{rid}/stages", headers=ANN).json()["stages"]
    assert stages[0]["code_ref"]["procedure_id"] == normalize and stages[2]["code_ref"]["procedure_id"] == aggregate


def test_stage_procedure_must_have_its_kind(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, MINI)
    dataset = client.get("/api/datasets", headers=ANN).json()["datasets"][0]["id"]
    r = client.post("/api/configs", json={"name": "c", "dataset": dataset, "compare": "builtin_normalize"}, headers=ANN)
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_code"


def test_compare_from_server_file(tmp_path, monkeypatch):
    """Процедура сравнения — размещённый на сервере файл .py (procedures/example_compare_by_bucket.py)."""
    client = make_client(tmp_path, monkeypatch, MINI)
    r = client.post("/api/procedures", json={"kind": "compare", "name": "по бакетам", "source": "file",
                                             "path": "procedures/example_compare_by_bucket.py"}, headers=ANN)
    assert r.status_code == 201, r.json()
    rid, data = _run(client, compare=r.json()["id"])
    assert data["status"] == "ready", data["error"]
    stage = client.get(f"/api/runs/{rid}/stages", headers=ANN).json()["stages"][1]
    assert stage["code_ref"] == {"procedure_id": r.json()["id"], "source": "file",
                                 "path": "procedures/example_compare_by_bucket.py", "line": 1}


ECHO_CHECK = """DEFAULTS = {"threshold": 1, "app_ids_limit": 20}


def run(mart, params):
    return [{"LABEL": CHECK["label"], "SOURCE": "AFTER", "ARGUMENT": f"{params['threshold']}/{params['app_ids_limit']}",
             "CNT": 0, "TOTAL": 0, "METRIC": 0, "APP_IDS": [], "RESULT": "PASS", "CONFIDENCE": "HIGH"}]


CHECK = {"id": "echo", "label": "Эхо", "params": DEFAULTS, "entrypoint": run}
"""


def test_check_params_from_config(tmp_path, monkeypatch):
    """Параметры проверки задаются в конфигурации, без правки кода; app_ids_limit по умолчанию — все заявки."""
    client = make_client(tmp_path, monkeypatch, MINI)
    check = _procedure(client, "check", ECHO_CHECK)
    procs = client.get("/api/procedures?kind=check", headers=ANN).json()["procedures"]
    assert next(p for p in procs if p["id"] == check)["params"] == {"threshold": 1, "app_ids_limit": 20}
    assert next(p for p in procs if p["id"] == "builtin_attribute_new_loss")["params"]["min_share"] == 0.001

    def argument(**extra):
        rid, data = _run(client, checks=[check], **extra)
        assert data["status"] == "ready", data["error"]
        return client.get(f"/api/runs/{rid}/checks", headers=ANN).json()["rows"][0]["argument"]

    assert argument() == "1/100000"
    assert argument(check_params={check: {"threshold": 7, "app_ids_limit": 5}}) == "7/5"


def test_check_params_need_connected_check(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch, MINI)
    dataset = client.get("/api/datasets", headers=ANN).json()["datasets"][0]["id"]
    r = client.post("/api/configs", json={"name": "c", "dataset": dataset, "checks": [],
                                          "check_params": {"builtin_attribute_new_loss": {"min_share": 1}}}, headers=ANN)
    assert r.status_code == 400 and "check_params" in r.json()["error"]["message"]


def test_own_id_path_is_used(tmp_path, monkeypatch):
    """Путь к id заявки — из процедуры приведения (ID_PATH), а не из кода приложения."""
    client = make_client(tmp_path, monkeypatch, MINI)
    proc = _procedure(client, "normalize", 'ARRAY_RULES = {}\nID_PATH = "appData.no_such_field"\n')
    _, data = _run(client, normalize=proc)
    assert data["status"] == "error" and "appData.no_such_field" in data["error"]["message"]


def test_apps_filtered_by_group_ref(tmp_path, monkeypatch):
    """Список заявок сужается до группы клетки сводной (`ref`)."""
    client = make_client(tmp_path, monkeypatch, MINI)
    rid, _ = _run(client)
    facts = client.get(f"/api/runs/{rid}/facts?dims=DECISION_CHANGED&measure=counts_distinct_apps", headers=ANN).json()
    row = facts["rows"][0]
    apps = client.get(f"/api/runs/{rid}/apps?ref={row['app_ids_ref']}", headers=ANN).json()
    assert apps["total"] == row["counts"]
    assert client.get(f"/api/runs/{rid}/apps?ref=f_nope", headers=ANN).status_code == 404
