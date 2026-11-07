"""Тесты разворота JSON в плоские строки. JSON внутри — выдуманные, не данные организаторов."""

import pytest

from pipeline.errors import BadFile, PipelineError
from pipeline.flatten import flatten_response

RULES = {
    "trials[]": {"mode": "key", "key": ["product_id", "type"]},
    "tags[]": {"mode": "value"},
    "scores[]": {"mode": "index"},
    "trials[].offers[]": {"mode": "key", "key": ["body.action"]},
}


def flat(doc, **kw):
    return flatten_response(doc, "A1", "BEFORE", kw.pop("rules", RULES), **kw)


def by_path(rows):
    return {(r["PATH"], r["ARRAY_KEY"]): r["VALUE"] for r in rows}


def test_simple_nested_dict():
    rows = flat({"decisionResult": {"decision": "APPROVE", "pd": {"value": 0.694}}})
    assert by_path(rows) == {
        ("decisionResult.decision", ""): "APPROVE",
        ("decisionResult.pd.value", ""): "0.694",
    }
    r = rows[1]
    assert (r["APP_ID"], r["SOURCE"]) == ("A1", "BEFORE")
    assert (r["PREFIX"], r["CLASS"], r["SUFFIX"], r["KEY"]) == ("decisionResult", "pd", "", "value")
    assert r["ADJUSTED_VALUE"] == r["VALUE"]


def test_split_path_variants():
    rows = flat({"a": 1, "b": {"c": 2}, "d": {"e": {"f": {"g": 3}}}})
    got = {r["PATH"]: (r["PREFIX"], r["CLASS"], r["SUFFIX"], r["KEY"]) for r in rows}
    assert got["a"] == ("", "", "", "a")
    assert got["b.c"] == ("b", "", "", "c")
    assert got["d.e.f.g"] == ("d", "e", "f", "g")


def test_array_by_key_order_independent():
    a = {"trials": [{"product_id": 1, "type": "x", "v": 10}, {"product_id": 2, "type": "x", "v": 20}]}
    b = {"trials": [{"product_id": 2, "type": "x", "v": 20}, {"product_id": 1, "type": "x", "v": 10}]}
    assert by_path(flat(a)) == by_path(flat(b))
    assert ("trials[].v", "1:x") in by_path(flat(a))


def test_composite_key_does_not_merge():
    doc = {"trials": [{"product_id": 15210, "type": "standard", "v": 1},
                      {"product_id": 15210, "type": "premium", "v": 2}]}
    got = by_path(flat(doc))
    assert got[("trials[].v", "15210:standard")] == "1"
    assert got[("trials[].v", "15210:premium")] == "2"


def test_index_array():
    rows = flat({"scores": [0.452, 0.593, 0.637]})
    assert [(r["PATH"], r["ARRAY_KEY"], r["VALUE"]) for r in rows] == [
        ("scores[]", "0", "0.452"), ("scores[]", "1", "0.593"), ("scores[]", "2", "0.637")]


def test_value_array():
    rows = flat({"tags": ["b", "a"]})
    assert {(r["ARRAY_KEY"], r["VALUE"]) for r in rows} == {("a", "a"), ("b", "b")}


def test_nested_array_key_with_pipe_and_dotted_key():
    doc = {"trials": [{"product_id": 1, "type": "x", "offers": [{"body": {"action": "AGELOW@21"}, "n": 5}]}]}
    got = by_path(flat(doc))
    assert got[("trials[].offers[].n", "1:x|AGELOW@21")] == "5"


def test_ignore_paths():
    doc = {"appData": {"request_id": "r", "keep": 1}, "trials": [{"product_id": 1, "type": "x", "t": 1, "v": 2}]}
    rows = flat(doc, ignore_paths=["appData.request_id", "trials[].t"])
    assert set(by_path(rows)) == {("appData.keep", ""), ("trials[].v", "1:x"),
                                  ("trials[].product_id", "1:x"), ("trials[].type", "1:x")}
    # без [] тоже подходит, и префикс срабатывает
    assert set(by_path(flat(doc, ignore_paths=["appData", "trials"]))) == set()


def test_ignore_whole_array_with_brackets():
    # массив без правила и пустой массив, заданные путём с [], не дают ни листьев, ни ошибки
    doc = {"keep": 1, "noRule": [{"a": 1}], "empty": []}
    rows = flat(doc, ignore_paths=["noRule[]", "empty[]"])
    assert set(by_path(rows)) == {("keep", "")}


def test_null_bool_empty_and_numbers():
    rows = flat({"a": None, "b": True, "c": False, "d": [], "e": {}, "f": 20.0, "g": 1e-05, "h": 7})
    got = {r["PATH"]: r["VALUE"] for r in rows}
    assert got == {"a": "null", "b": "true", "c": "false", "d": "[]", "e": "{}",
                   "f": "20", "g": "0.00001", "h": "7"}


def test_adjust_applied():
    rows = flat({"pd": 0.7}, adjust=lambda p, v: "high" if p == "pd" else v)
    assert rows[0]["VALUE"] == "0.7" and rows[0]["ADJUSTED_VALUE"] == "high"


def test_unknown_array_gets_default_rule():
    # Нет правила ни в процедуре, ни в конфигурации — список объектов идёт по позиции, а не падает
    rows = flat({"unknown": [{"x": 1}, {"x": 2}]})
    assert {r["ARRAY_KEY"] for r in rows} == {"0", "1"}


def test_unknown_scalar_array_matches_by_value():
    rows = flat({"extra": ["web", "mobile"]})
    assert {r["ARRAY_KEY"] for r in rows} == {"web", "mobile"}


def test_unknown_scalar_array_with_duplicates_falls_back_to_index():
    rows = flat({"extra": ["web", "web"]})
    assert {r["ARRAY_KEY"] for r in rows} == {"0", "1"}


def test_duplicate_key_is_error():
    doc = {"trials": [{"product_id": 1, "type": "x"}, {"product_id": 1, "type": "x"}]}
    with pytest.raises(BadFile) as e:
        flat(doc)
    assert "trials[]" in e.value.message and "1:x" in e.value.message


def test_key_must_be_scalar():
    doc = {"trials": [{"product_id": {"a": 1}, "type": "x"}]}
    with pytest.raises(BadFile) as e:
        flat(doc)
    assert "trials[]" in e.value.message


@pytest.mark.parametrize("bad", ["a:b", "a|b"])
def test_key_with_separator_is_error(bad):
    # «a:b» + «c» и «a» + «b:c» склеились бы в один ключ — запрещаем разделители в значениях
    with pytest.raises(BadFile):
        flat({"trials": [{"product_id": bad, "type": "x"}]})
    with pytest.raises(BadFile):
        flat({"tags": [bad]})


def test_soft_builtin_rule_falls_back_when_key_missing():
    # ext_data[] из встроенной процедуры ждёт body.action; у чужого формата его нет — берём умолчание
    rows = flatten_response({"ext_data": [{"source": "BKI"}, {"source": "FNS"}]}, "A1", "BEFORE",
                            {"ext_data[]": {"mode": "key", "key": ["body.action"]}}, soft_paths=["ext_data[]"])
    assert {r["ARRAY_KEY"] for r in rows} == {"0", "1"}


def test_configured_rule_stays_strict_when_key_missing():
    with pytest.raises(BadFile) as e:
        flatten_response({"ext_data": [{"source": "BKI"}]}, "A1", "BEFORE",
                         {"ext_data[]": {"mode": "key", "key": ["body.action"]}})
    assert "нет поля ключа" in e.value.message
