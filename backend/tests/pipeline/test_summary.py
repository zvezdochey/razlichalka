"""Тесты итогов: мини-CSV руками (выдуманные данные) и настоящий датасет (если он есть)."""

import json

import pytest

from pipeline.compare import COLUMNS as CMP_COLUMNS, compare_csv
from pipeline.csvio import read_csv, write_csv
from pipeline.errors import BadFile
from pipeline.normalize import normalize_dataset
from pipeline.segments import COLUMNS as SEG_COLUMNS, build_segments
from pipeline.summary import APPS_COLUMNS, build_summary, decision_change, normalize_decision
from tests.real_dataset import REAL


@pytest.mark.parametrize("raw,expected", [
    ("APPROVE", "approve"), (" approve ", "approve"), ("Reject", "reject"),
    ("VERIFICATION", "other"), ("", "other"), (None, "other"),
])
def test_normalize_decision(raw, expected):
    assert normalize_decision(raw) == expected


@pytest.mark.parametrize("b,a,expected", [
    ("APPROVE", "approve", "same"), ("", "VERIFICATION", "same"),
    ("APPROVE", "REJECT", "approve_to_reject"), ("reject", "Approve", "reject_to_approve"),
    ("APPROVE", "VERIFICATION", "decision_other"), ("", "REJECT", "decision_other"),
])
def test_decision_change(b, a, expected):
    assert decision_change(b, a) == expected


def _seg(app, before, after, **kw):
    row = dict.fromkeys(SEG_COLUMNS, "")
    row.update(APP_ID=app, DECISION_BEFORE=before, DECISION_AFTER=after, **kw)
    return row


def _cmp(app, path, change):
    row = dict.fromkeys(CMP_COLUMNS, "")
    row.update(APP_ID=app, PATH=path, CHANGE_TYPE=change, DIFF_FLAG="0" if change == "SAME" else "1")
    return row


def _mini(tmp_path):
    seg = tmp_path / "segments.csv"
    cmp_ = tmp_path / "comparison.csv"
    write_csv(seg, SEG_COLUMNS, [
        _seg("A1", "APPROVE", "REJECT", PD_MODEL_BEFORE="M1", REJECT_REASON_AFTER="CUTOFF", CHANGE_SOURCE="data"),
        _seg("A2", "REJECT", "APPROVE", CHANGE_SOURCE="logic"),
        _seg("A3", "APPROVE", "APPROVE", CHANGE_SOURCE="logic"),  # решение то же — в change_sources не идёт
        _seg("A4", "APPROVE", "VERIFICATION", CHANGE_SOURCE="logic"),
        _seg("A5", "REJECT", "REJECT", CHANGE_SOURCE="none"),  # в витрине строк нет
    ])
    write_csv(cmp_, CMP_COLUMNS, [
        _cmp("A1", "x", "VALUE_CHANGED"), _cmp("A1", "y", "ATTRIBUTE_NEW"), _cmp("A1", "z", "SAME"),
        _cmp("A2", "x", "ATTRIBUTE_LOST"),
        _cmp("A3", "x", "SAME"),
        _cmp("A4", "x", "VALUE_CHANGED"), _cmp("A4", "y", "VALUE_CHANGED"),
    ])
    return cmp_, seg


def test_mini_counts(tmp_path):
    cmp_, seg = _mini(tmp_path)
    out_json, out_apps = tmp_path / "summary.json", tmp_path / "apps.csv"
    summary = build_summary(cmp_, seg, out_json, out_apps)

    assert summary == {
        "applications": 5,
        "applications_changed": 3,
        "applications_changed_share": 0.6,
        "decision_changed": 3,
        "decision_changes": {"same": 2, "approve_to_reject": 1, "reject_to_approve": 1, "decision_other": 1},
        "attributes": {"VALUE_CHANGED": 3, "ATTRIBUTE_NEW": 1, "ATTRIBUTE_LOST": 1},
        "change_sources": {"logic": 2, "data": 1, "both": 0, "none": 0},
    }
    assert json.loads(out_json.read_text(encoding="utf-8")) == summary

    apps = read_csv(out_apps)
    assert list(apps.columns) == APPS_COLUMNS
    by_id = apps.set_index("app_id")
    assert list(by_id["attributes_changed"]) == ["2", "1", "0", "2", "0"]
    assert by_id.loc["A1", "decision_change"] == "approve_to_reject"
    assert by_id.loc["A4", "decision_after"] == "other"
    assert by_id.loc["A1", "pd_model_before"] == "M1"
    assert by_id.loc["A1", "reject_reason_after"] == "CUTOFF"
    assert by_id.loc["A2", "reject_reason_after"] == ""  # пустое остаётся пустым
    assert list(by_id["change_source"]) == ["data", "logic", "logic", "logic", "none"]


def test_change_sources_sum_is_decision_changed(tmp_path):
    cmp_, seg = _mini(tmp_path)
    s = build_summary(cmp_, seg, tmp_path / "s.json", tmp_path / "a.csv")
    assert sum(s["change_sources"].values()) == s["decision_changed"]


def test_change_source_empty_on_decision_change_is_error(tmp_path):
    """Разрезы построены без витрины (CHANGE_SOURCE пустой) — итоги не врут молча нулями."""
    seg, cmp_ = tmp_path / "s.csv", tmp_path / "c.csv"
    write_csv(seg, SEG_COLUMNS, [_seg("A1", "APPROVE", "REJECT")])
    write_csv(cmp_, CMP_COLUMNS, [_cmp("A1", "x", "VALUE_CHANGED")])
    with pytest.raises(BadFile, match="CHANGE_SOURCE"):
        build_summary(cmp_, seg, tmp_path / "s.json", tmp_path / "a.csv")


def test_share_rounded(tmp_path):
    seg, cmp_ = tmp_path / "s.csv", tmp_path / "c.csv"
    write_csv(seg, SEG_COLUMNS, [_seg(f"A{i}", "APPROVE", "APPROVE") for i in range(3)])
    write_csv(cmp_, CMP_COLUMNS, [_cmp("A0", "x", "VALUE_CHANGED")])
    s = build_summary(cmp_, seg, tmp_path / "s.json", tmp_path / "a.csv")
    assert s["applications_changed_share"] == 0.333


def test_missing_columns(tmp_path):
    bad = tmp_path / "bad.csv"
    write_csv(bad, ["APP_ID"], [{"APP_ID": "1"}])
    with pytest.raises(BadFile):
        build_summary(bad, bad, tmp_path / "s.json", tmp_path / "a.csv")


def test_log_called(tmp_path):
    cmp_, seg = _mini(tmp_path)
    msgs = []
    build_summary(cmp_, seg, tmp_path / "s.json", tmp_path / "a.csv", log=lambda lvl, m: msgs.append((lvl, m)))
    assert msgs and msgs[0][0] == "info"


@pytest.mark.skipif(not (REAL / "manifest.json").exists(), reason="нет настоящего датасета")
def test_real_dataset(tmp_path):
    """Весь конвейер на настоящем датасете: числа решений — из docs/api.md п. 7.1."""
    nb, na, cmp_ = tmp_path / "nb.csv", tmp_path / "na.csv", tmp_path / "cmp.csv"
    seg = tmp_path / "seg.csv"
    cfg = {"ignore_paths": ["appData.request_id", "appData.createDateTime"]}  # иначе вход «другой» у всех
    normalize_dataset(REAL, "BEFORE", nb, cfg)
    normalize_dataset(REAL, "AFTER", na, cfg)
    compare_csv(nb, na, cmp_)
    build_segments(REAL, seg, comparison_csv=cmp_)

    s = build_summary(cmp_, seg, tmp_path / "summary.json", tmp_path / "apps.csv")
    print("\nREAL SUMMARY:", json.dumps(s, ensure_ascii=False))
    assert s["applications"] == 2002
    assert s["decision_changed"] == 385
    assert s["decision_changes"] == {
        "same": 1617, "approve_to_reject": 273, "reject_to_approve": 112, "decision_other": 0}
    # E10: у 167 смен решения поменялся вход (ext_data[] score_okb), у 218 — только то, что посчитала СПР
    assert s["change_sources"] == {"logic": 218, "data": 167, "both": 0, "none": 0}
    assert len(read_csv(tmp_path / "apps.csv")) == 2002
