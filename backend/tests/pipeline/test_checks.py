"""Тесты Mart и запуска проверок. Мини-витрина выдуманная; на настоящем датасете — с skipif."""

import time
from pathlib import Path

import pytest

from pipeline.checks_runner import (RESULT_COLUMNS, load_check, run_checks, validate_check_code,
                                    write_checks_csv)
from pipeline.compare import compare_csv
from pipeline.csvio import read_csv, write_csv
from pipeline.errors import BadFile
from pipeline.mart import Mart
from pipeline.normalize import normalize_dataset
from pipeline.segments import build_segments
from tests.real_dataset import REAL

CHECKS_DIR = next((p for p in [REAL.parents[1] / "checks"] if p.is_dir()), None)

COMP_COLS = ["APP_ID", "PREFIX", "CLASS", "SUFFIX", "ARRAY_KEY", "KEY", "PATH", "VALUE_BEFORE", "VALUE_AFTER",
             "ADJUSTED_BEFORE", "ADJUSTED_AFTER", "DIFF_FLAG", "CHANGE_TYPE"]


def comp_row(app, path, vb, va, ct, ak=""):
    key = path.split(".")[-1]
    return {"APP_ID": app, "PREFIX": path.split(".")[0], "CLASS": "", "SUFFIX": "", "ARRAY_KEY": ak, "KEY": key,
            "PATH": path, "VALUE_BEFORE": vb, "VALUE_AFTER": va, "ADJUSTED_BEFORE": vb, "ADJUSTED_AFTER": va,
            "DIFF_FLAG": "0" if ct == "SAME" else "1", "CHANGE_TYPE": ct}


@pytest.fixture
def mart(tmp_path):
    rows = [
        comp_row("1", "a.x", "1", "1", "SAME"),
        comp_row("1", "a.y", "1", "2", "VALUE_CHANGED"),
        comp_row("2", "a.y", "5", "6", "VALUE_CHANGED"),
        comp_row("2", "b.z[].v", "", "7", "ATTRIBUTE_NEW", ak="K1"),
        comp_row("3", "b.z[].v", "8", "", "ATTRIBUTE_LOST", ak="K2"),
        comp_row("3", "a.x", "1", "1", "SAME"),
    ]
    comp, seg = tmp_path / "c.csv", tmp_path / "s.csv"
    write_csv(comp, COMP_COLS, rows)
    write_csv(seg, ["APP_ID", "DECISION_BEFORE", "DECISION_AFTER", "DECISION_CHANGED", "PRODUCTS"], [
        {"APP_ID": "1", "DECISION_BEFORE": "APPROVE", "DECISION_AFTER": "REJECT", "DECISION_CHANGED": "1", "PRODUCTS": "P1|P2"},
        {"APP_ID": "2", "DECISION_BEFORE": "REJECT", "DECISION_AFTER": "REJECT", "DECISION_CHANGED": "0", "PRODUCTS": "P1"},
        {"APP_ID": "3", "DECISION_BEFORE": "APPROVE", "DECISION_AFTER": "APPROVE", "DECISION_CHANGED": "0", "PRODUCTS": ""},
    ])
    return Mart(comp, seg)


# --- Mart -----------------------------------------------------------------------

def test_no_filters_returns_everything(mart):
    assert mart.count() == 6 and len(mart.rows()) == 6
    assert mart.total_apps() == 3
    assert mart.app_ids() == ["1", "2", "3"]


def test_rows_are_dicts_with_upper_keys_in_file_order(mart):
    rows = mart.rows()
    assert list(rows[0]) == COMP_COLS
    assert [r["APP_ID"] for r in rows] == ["1", "1", "2", "2", "3", "3"]


@pytest.mark.parametrize("filters,expected", [
    ({"path": "a.y"}, 2),
    ({"path": ["a.x", "a.y"]}, 4),
    ({"path_prefix": "b."}, 2),
    ({"path_prefix": "a"}, 4),
    ({"key": "v"}, 2),
    ({"array_key": "K1"}, 1),
    ({"diff_flag": 1}, 4),
    ({"diff_flag": 0}, 2),
    ({"change_type": "SAME"}, 2),
    ({"change_type": ["ATTRIBUTE_NEW", "ATTRIBUTE_LOST"]}, 2),
    ({"value_before": "1"}, 3),
    ({"value_after": "7"}, 1),
    ({"value_before": ""}, 1),
    ({"app_ids": ["1", "3"]}, 4),
    ({"app_ids": "2", "path": "a.y"}, 1),
    ({"path": "a.y", "change_type": "SAME"}, 0),
    ({"path": "нет такого"}, 0),
])
def test_filters(mart, filters, expected):
    assert mart.count(**filters) == expected
    assert len(list(mart.rows(**filters))) == expected


def test_app_ids_sorted_unique(mart):
    assert mart.app_ids(path="a.x") == ["1", "3"]
    assert mart.app_ids(diff_flag=1) == ["1", "2", "3"]


def test_unknown_filter_is_error(mart):
    with pytest.raises(TypeError):
        mart.rows(pathh="a.x")


def test_rows_are_copies(mart):
    mart.rows(path="a.x")[0]["VALUE_BEFORE"] = "испорчено"
    assert mart.rows(path="a.x")[0]["VALUE_BEFORE"] == "1"


def test_segments_fixups_for_checks(mart):
    segs = {s["APP_ID"]: s for s in mart.segments()}
    assert segs["1"]["DECISION_CHANGED"] == 1 and segs["2"]["DECISION_CHANGED"] == 0
    assert segs["1"]["PRODUCTS"] == "P1;P2"


# --- загрузка и проверка кода ---------------------------------------------------

GOOD = '''
def run(mart, params):
    n = mart.count(diff_flag=1)
    return [{"LABEL": "t", "SOURCE": "AFTER", "ARGUMENT": "all", "CNT": n, "TOTAL": mart.total_apps(),
             "METRIC": 0.5, "APP_IDS": mart.app_ids(diff_flag=1)[: params["limit"]], "RESULT": "FAIL",
             "CONFIDENCE": "HIGH"}]
CHECK = {"id": "good", "label": "Хорошая", "params": {"limit": 2}, "entrypoint": run}
'''


def test_load_check_from_code():
    check = load_check(GOOD, "code")
    assert check["id"] == "good" and callable(check["entrypoint"])


def test_load_check_from_file(tmp_path):
    f = tmp_path / "c.py"
    f.write_text(GOOD, encoding="utf-8")
    assert load_check(f, "file")["label"] == "Хорошая"


@pytest.mark.parametrize("code", ["def run(:", "x = 1", "CHECK = {'id': 'a'}",
                                  "raise ValueError('x')\nCHECK = {'id': 1, 'label': 1, 'params': {}, 'entrypoint': print}"])
def test_load_check_bad(code):
    with pytest.raises(BadFile):
        load_check(code, "code")


def test_load_check_infinite_loop_does_not_hang():
    started = time.time()
    code = "while True:\n    pass\nCHECK = {'id': 'a', 'label': 'b', 'params': {}, 'entrypoint': print}"
    with pytest.raises(BadFile, match="не загрузился"):
        load_check(code, "code", timeout=3)
    assert time.time() - started < 30


def test_load_check_runs_only_in_child_without_secrets(monkeypatch):
    # код отработал при загрузке, но не в этом процессе и без секретов окружения
    monkeypatch.setenv("MY_LOAD_SECRET", "abc")
    code = ("import os\nSECRET = os.environ.get('MY_LOAD_SECRET')\n"
            "def run(m, p):\n    return []\n"
            "CHECK = {'id': 'a', 'label': str(SECRET), 'params': {}, 'entrypoint': run}")
    assert load_check(code, "code")["label"] == "None"


def test_load_check_side_effect_not_in_parent(tmp_path):
    marker = tmp_path / "ran.txt"
    code = (f"import os\nopen({str(marker)!r}, 'w').write(str(os.getpid()))\n"
            "CHECK = {'id': 'a', 'label': 'b', 'params': {}, 'entrypoint': print}")
    load_check(code, "code")
    import os
    assert marker.read_text() != str(os.getpid())


def test_validate_entrypoint_not_a_function():
    code = 'CHECK = {"id": "a", "label": "b", "params": {}, "entrypoint": 5}\n'
    assert "функцией" in validate_check_code(code)[0]["message"]
    lam = 'CHECK = {"id": "a", "label": "b", "params": {}, "entrypoint": lambda m, p: []}\n'
    assert validate_check_code(lam) == []


def test_validate_ok():
    assert validate_check_code(GOOD) == []


def test_validate_syntax_error_has_line():
    problems = validate_check_code("x = 1\ndef run(:\n    pass\n")
    assert len(problems) == 1 and problems[0]["line"] == 2


def test_validate_no_check():
    assert validate_check_code("def run(mart, params):\n    return []\n")[0]["message"].startswith("Нет объекта CHECK")


def test_validate_missing_key_and_function():
    code = 'CHECK = {"id": "a", "label": "b", "entrypoint": go}\n'
    messages = [p["message"] for p in validate_check_code(code)]
    assert any("params" in m for m in messages)


# --- запуск ---------------------------------------------------------------------

def test_run_in_subprocess_and_params_override(mart):
    check = load_check(GOOD, "code")
    rows = run_checks(mart, [check], {"good": {"limit": 1}})
    assert len(rows) == 1 and rows[0]["APP_IDS"] == ["1"] and rows[0]["CNT"] == 4


def test_failing_check_does_not_break_run(mart):
    bad = load_check('def run(m, p):\n    raise RuntimeError("бум")\n'
                     'CHECK = {"id": "bad", "label": "Падающая", "params": {}, "entrypoint": run}', "code")
    logs = []
    rows = run_checks(mart, [bad, load_check(GOOD, "code")], log=lambda lvl, msg: logs.append((lvl, msg)))
    assert rows[0]["RESULT"] == "FAIL" and rows[0]["CONFIDENCE"] == "LOW" and "бум" in rows[0]["ARGUMENT"]
    assert rows[0]["LABEL"] == "Падающая"
    assert rows[1]["LABEL"] == "t"  # следующая проверка отработала
    assert any(lvl == "error" for lvl, _ in logs)


def test_hanging_check_is_killed_and_next_runs(mart):
    hang = load_check('import time\ndef run(m, p):\n    time.sleep(600)\n'
                      'CHECK = {"id": "h", "label": "Зависшая", "params": {}, "entrypoint": run}', "code")
    started = time.time()
    rows = run_checks(mart, [hang, load_check(GOOD, "code")], timeout=3)
    assert time.time() - started < 60
    assert "не уложилась" in rows[0]["ARGUMENT"] and rows[0]["RESULT"] == "FAIL"
    assert rows[1]["LABEL"] == "t"


def test_user_code_does_not_see_env_secrets(mart, monkeypatch):
    monkeypatch.setenv("MY_SECRET_TOKEN", "abc")
    spy = load_check('import os\ndef run(m, p):\n'
                     '    return [{"LABEL": "env", "ARGUMENT": str(os.environ.get("MY_SECRET_TOKEN")), "RESULT": "PASS"}]\n'
                     'CHECK = {"id": "e", "label": "env", "params": {}, "entrypoint": run}', "code")
    assert run_checks(mart, [spy])[0]["ARGUMENT"] == "None"


def test_missing_columns_are_filled(mart):
    sparse = load_check('def run(m, p):\n    return [{"ARGUMENT": "x", "APP_IDS": ["a", "b"]}]\n'
                        'CHECK = {"id": "s", "label": "Редкая", "params": {}, "entrypoint": run}', "code")
    row = run_checks(mart, [sparse])[0]
    assert set(row) == set(RESULT_COLUMNS) and row["LABEL"] == "Редкая"


def test_write_checks_csv(tmp_path, mart):
    rows = run_checks(mart, [load_check(GOOD, "code")])
    out = tmp_path / "checks.csv"
    assert write_checks_csv(rows, out) == 1
    df = read_csv(out)
    assert list(df.columns) == RESULT_COLUMNS
    assert df.loc[0, "APP_IDS"] == "1|2"


# --- настоящие проверки организаторов на настоящем датасете ---------------------

@pytest.mark.slow
@pytest.mark.skipif(not (REAL / "manifest.json").exists() or CHECKS_DIR is None, reason="нет настоящего датасета")
def test_five_real_checks(tmp_path):
    cfg = {"ignore_paths": ["appData.request_id", "appData.createDateTime"]}
    for s in ("BEFORE", "AFTER"):
        normalize_dataset(REAL, s, tmp_path / f"n_{s}.csv", cfg)
    compare_csv(tmp_path / "n_BEFORE.csv", tmp_path / "n_AFTER.csv", tmp_path / "comparison.csv")
    build_segments(REAL, tmp_path / "segments.csv")

    t = time.time()
    mart = Mart(tmp_path / "comparison.csv", tmp_path / "segments.csv")
    load_time = time.time() - t
    files = sorted(CHECKS_DIR.glob("check_*.py"))
    assert len(files) == 5
    t = time.time()
    rows = run_checks(mart, [load_check(f, "file") for f in files])
    print(f"\nMart загружен за {load_time:.1f} с, 5 проверок за {time.time() - t:.1f} с, строк {len(rows)}")
    assert rows and all(set(r) == set(RESULT_COLUMNS) for r in rows)
    assert not any(str(r["ARGUMENT"]).startswith(("RuntimeError", "TypeError", "KeyError")) for r in rows)
    assert {r["LABEL"] for r in rows} >= {load_check(f, "file")["label"] for f in files}
