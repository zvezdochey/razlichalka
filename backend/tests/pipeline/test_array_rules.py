"""Тесты правил массивов. JSON — выдуманные, не данные организаторов."""


import pytest

from pipeline.array_rules import default_array_rules, merge_array_rules
from pipeline.flatten import flatten_response
from tests.real_dataset import REAL

DEFAULT_ARRAY_RULES = default_array_rules()


def test_nine_rules():
    assert len(DEFAULT_ARRAY_RULES) == 9


def test_merge_changes_only_mode():
    path = "decisionResult.product_trials[]"
    merged = merge_array_rules(DEFAULT_ARRAY_RULES, {path: "index"})
    assert merged[path]["mode"] == "index"
    assert merged[path]["key"] == ["product_id"]  # ключ остался
    assert DEFAULT_ARRAY_RULES[path]["mode"] == "key"  # исходные правила не испорчены


def test_merge_path_without_trailing_brackets():
    # путь из примера конфига в docs/api.md — без последних []
    merged = merge_array_rules(DEFAULT_ARRAY_RULES, {"decisionResult.scoring[].value": "value"})
    assert merged["decisionResult.scoring[].value[]"]["mode"] == "value"
    assert "decisionResult.scoring[].value" not in merged


def test_rules_live_in_procedure_file():
    # правила — данные процедуры, а не код pipeline
    from pipeline.procedures import load_builtin_value
    assert load_builtin_value("builtin_normalize", "ARRAY_RULES") == DEFAULT_ARRAY_RULES


def test_buckets_and_id_path_live_in_procedure_file():
    # границы бакетов и путь к id заявки — тоже данные процедуры; конфигурация перекрывает бакеты по пути
    from pipeline.array_rules import default_buckets, id_path
    from pipeline.buckets import merge_buckets
    buckets = default_buckets()
    assert "characteristics.score_okb" in buckets and id_path() == "appData.application_id"
    merged = merge_buckets(buckets, {"characteristics.score_okb[]": [], "x.y": [1]})
    assert "characteristics.score_okb" not in merged and merged["characteristics.score_okb[]"] == [] and merged["x.y"] == [1]


def test_array_rules_override_key():
    path = "decisionResult.product_trials[]"
    merged = merge_array_rules(DEFAULT_ARRAY_RULES, {}, {path: {"mode": "key", "key": ["code"]}})
    assert merged[path] == {"mode": "key", "key": ["code"]}
    assert DEFAULT_ARRAY_RULES[path]["key"] == ["product_id"]


def test_array_rules_new_array_matched_by_config_key():
    # массива нет в процедуре — правило только из конфигурации, путь без последних []
    rules = merge_array_rules(DEFAULT_ARRAY_RULES, {}, {"limits": {"mode": "key", "key": ["kind"]}})
    doc = {"limits": [{"kind": "day", "amount": 1}, {"kind": "month", "amount": 30}]}
    rows = flatten_response(doc, "A1", "BEFORE", rules)
    got = {r["ARRAY_KEY"]: r["VALUE"] for r in rows if r["KEY"] == "amount"}
    assert got == {"day": "1", "month": "30"}


def test_array_modes_new_path_without_brackets_gets_them():
    # неизвестный путь без [] приводим к пути массива: flatten ищет правила только по путям с []
    merged = merge_array_rules(DEFAULT_ARRAY_RULES, {"tags": "value"})
    assert merged["tags[]"] == {"mode": "value"} and "tags" not in merged
    rows = flatten_response({"tags": ["b", "a"]}, "A1", "BEFORE", merged)
    assert len(rows) == 2


def test_load_builtin_from_other_folder(tmp_path):
    from pipeline.errors import BadFile
    from pipeline.procedures import load_builtin
    (tmp_path / "builtin_normalize.py").write_text('ARRAY_RULES = {"x[]": {"mode": "index"}}', encoding="utf-8")
    assert default_array_rules(tmp_path) == {"x[]": {"mode": "index"}}
    (tmp_path / "two.py").write_text("A = {}\nB = {}", encoding="utf-8")
    with pytest.raises(BadFile, match="одна переменная"):
        load_builtin("two", tmp_path)


def test_array_modes_applied_after_array_rules():
    path = "decisionResult.product_trials[]"
    merged = merge_array_rules(DEFAULT_ARRAY_RULES, {path: "index"}, {path: {"mode": "key", "key": ["code"]}})
    assert merged[path] == {"mode": "index", "key": ["code"]}


def test_two_offers_same_product_give_different_rows():
    doc = {"decisionResult": {"available_offers": [
        {"product_id": "p1", "type": "standard", "amount": 100},
        {"product_id": "p1", "type": "manual", "amount": 200},
    ]}}
    rows = flatten_response(doc, "A1", "BEFORE", DEFAULT_ARRAY_RULES)
    got = {(r["ARRAY_KEY"], r["KEY"]): r["VALUE"] for r in rows if r["KEY"] == "amount"}
    assert got == {("p1:standard", "amount"): "100", ("p1:manual", "amount"): "200"}


DATASET = REAL / "RESULTS"


@pytest.mark.skipif(not DATASET.exists(), reason="нет настоящего датасета (DATASET_DIR)")
def test_real_dataset_no_errors():
    from pipeline.tools.check_dataset import main
    for срез in ("BEFORE_MASTER", "AFTER_BETA"):
        assert main(DATASET / срез) == 0
