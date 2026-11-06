"""Тесты слоя разрезов. Мини-датасет собираем в tmp_path — все данные выдуманные."""

import json
from pathlib import Path

import pytest

from pipeline.csvio import read_csv
from pipeline.errors import BadFile, Cancelled
from pipeline.segments import COLUMNS, build_segments
from tests.real_dataset import REAL

MINI = Path(__file__).parent.parent / "fixtures" / "dataset_mini"


def trial(pid, pd_model="M1", cutoff="C1", reason=None, partner="CURRENT", routing="referal"):
    t = {"product_id": pid, "partner_type": partner, "routing_method": routing,
         "scoring": {"pd": {"modelName": pd_model, "value": 0.5}}, "cutOff": {"name": cutoff}}
    if reason:
        t["rejectReason"] = reason
    return t


def doc(app_id, decision, trials, offers=(), okb=None):
    d = {"appData": {"application_id": app_id},
         "decisionResult": {"decision": decision, "available_offers": list(offers), "product_trials": trials}}
    if okb is not None:
        d["characteristics"] = {"score_okb": okb}
    return d


def offer(pid, rank, typ="standard"):
    return {"product_id": pid, "rank": rank, "type": typ}


def make_dataset(tmp_path, pairs):
    """pairs: {app_id: (документ BEFORE, документ AFTER)}."""
    (tmp_path / "B").mkdir()
    (tmp_path / "A").mkdir()
    (tmp_path / "manifest.json").write_text(json.dumps(
        {"srez": {"BEFORE": {"dir": "B"}, "AFTER": {"dir": "A"}}}), encoding="utf-8")
    for app_id, (b, a) in pairs.items():
        (tmp_path / "B" / f"{app_id}.json").write_text(json.dumps(b), encoding="utf-8")
        (tmp_path / "A" / f"{app_id}.json").write_text(json.dumps(a), encoding="utf-8")
    return tmp_path


def run(tmp_path, pairs, **kw):
    (tmp_path / "ds").mkdir()
    ds = make_dataset(tmp_path / "ds", pairs)
    out = tmp_path / "segments.csv"
    n = build_segments(ds, out, **kw)
    return n, read_csv(out).set_index("APP_ID")


def test_columns_and_count(tmp_path):
    out = tmp_path / "s.csv"
    n = build_segments(MINI, out)
    df = read_csv(out)
    assert list(df.columns) == COLUMNS
    assert n == len(df) == 3
    assert df["APP_ID"].is_unique


def test_decision_changed_and_not_changed(tmp_path):
    n, df = run(tmp_path, {
        "X1": (doc("X1", "REJECT", [trial(1)]), doc("X1", "APPROVE", [trial(1)])),
        "X2": (doc("X2", "APPROVE", [trial(1)]), doc("X2", "APPROVE", [trial(1)])),
    })
    assert (df.loc["X1", "DECISION_BEFORE"], df.loc["X1", "DECISION_AFTER"], df.loc["X1", "DECISION_CHANGED"]) \
        == ("REJECT", "APPROVE", "1")
    assert df.loc["X2", "DECISION_CHANGED"] == "0"


def test_top_offer_and_same_product_fields(tmp_path):
    # в выдаче первым стоит продукт 20 (rank 1), хотя в прогонах первым идёт 10
    before = doc("X", "APPROVE", [trial(10, "OLD10", "CO10", partner="OTHER"), trial(20, "OLD20", "CO20", routing="api")],
                 offers=[offer(10, 2), offer(20, 1)], okb=710)
    after = doc("X", "APPROVE", [trial(10, "NEW10", "CN10"), trial(20, "NEW20", "CN20", reason="CUTOFF")],
                offers=[offer(10, 1), offer(20, 2)], okb=655)
    _, df = run(tmp_path, {"X": (before, after)})
    r = df.loc["X"]
    assert (r["TOP_OFFER_BEFORE"], r["TOP_OFFER_AFTER"]) == ("20", "10")
    assert (r["PD_MODEL_BEFORE"], r["PD_MODEL_AFTER"]) == ("OLD20", "NEW10")
    assert (r["CUTOFF_BEFORE"], r["CUTOFF_AFTER"]) == ("CO20", "CN10")
    assert (r["REJECT_REASON_BEFORE"], r["REJECT_REASON_AFTER"]) == ("", "")  # продукт на 1 месте не отказан
    assert (r["PARTNER_TYPE"], r["ROUTING_METHOD"]) == ("CURRENT", "api")  # из BEFORE
    assert (r["SCORE_OKB_BEFORE"], r["SCORE_OKB_AFTER"]) == ("710", "655")
    assert r["PRODUCTS"] == "10|20"


def test_partner_from_slice_with_offers(tmp_path):
    # REJECT->APPROVE: в BEFORE выдачи нет, в AFTER первым стоит не продукт с наименьшим id
    before = doc("X", "REJECT", [trial(1, partner="CURRENT", routing="referal"), trial(2, partner="NEW", routing="api")])
    after = doc("X", "APPROVE", [trial(1, partner="CURRENT", routing="referal"), trial(2, partner="NEW", routing="api")],
                offers=[offer(2, 1)])
    _, df = run(tmp_path, {"X": (before, after)})
    assert (df.loc["X", "PARTNER_TYPE"], df.loc["X", "ROUTING_METHOD"]) == ("NEW", "api")


def test_partner_from_before_when_both_have_offers(tmp_path):
    b = doc("X", "APPROVE", [trial(1, partner="P1", routing="r1"), trial(2, partner="P2", routing="r2")], offers=[offer(1, 1)])
    a = doc("X", "APPROVE", [trial(1, partner="P1", routing="r1"), trial(2, partner="P2", routing="r2")], offers=[offer(2, 1)])
    _, df = run(tmp_path, {"X": (b, a)})
    assert (df.loc["X", "PARTNER_TYPE"], df.loc["X", "ROUTING_METHOD"]) == ("P1", "r1")


def test_no_offers_takes_min_product_id(tmp_path):
    before = doc("X", "REJECT", [trial(30, "M30"), trial(5, "M5", "C5", reason="HARDCHECK")])
    after = doc("X", "REJECT", [trial(30, "M30"), trial(5, "M5b", "C5", reason="CUTOFF")])
    _, df = run(tmp_path, {"X": (before, after)})
    r = df.loc["X"]
    assert (r["TOP_OFFER_BEFORE"], r["TOP_OFFER_AFTER"]) == ("", "")
    assert (r["PD_MODEL_BEFORE"], r["PD_MODEL_AFTER"]) == ("M5", "M5b")
    assert (r["REJECT_REASON_BEFORE"], r["REJECT_REASON_AFTER"]) == ("HARDCHECK", "CUTOFF")
    assert r["PRODUCTS"] == "5|30"  # по возрастанию числа, а не строки


def test_products_numeric_order(tmp_path):
    t = [trial(100), trial(9), trial(15210)]
    _, df = run(tmp_path, {"X": (doc("X", "APPROVE", t), doc("X", "APPROVE", t))})
    assert df.loc["X", "PRODUCTS"] == "9|100|15210"


def test_missing_score_okb_and_fields_are_empty_cells(tmp_path):
    bare = {"appData": {"application_id": "X"}, "decisionResult": {"decision": "APPROVE"}}
    _, df = run(tmp_path, {"X": (bare, doc("X", "APPROVE", [{"product_id": 1}]))})
    r = df.loc["X"]
    assert r["SCORE_OKB_BEFORE"] == r["SCORE_OKB_AFTER"] == ""
    assert r["PD_MODEL_AFTER"] == r["CUTOFF_AFTER"] == r["PARTNER_TYPE"] == ""
    assert r["PRODUCTS"] == "1"
    assert "None" not in r.tolist()


def test_two_offers_of_one_product_standard_and_manual(tmp_path):
    offers = [offer(7, 1, "standard"), offer(7, 1, "manual"), offer(8, 2)]
    d = doc("X", "APPROVE", [trial(7, "M7"), trial(8, "M8")], offers=offers)
    _, df = run(tmp_path, {"X": (d, d)})
    assert df.loc["X", "TOP_OFFER_BEFORE"] == "7"
    assert df.loc["X", "PD_MODEL_BEFORE"] == "M7"


def test_top_offer_product_missing_in_trials(tmp_path):
    d = doc("X", "APPROVE", [trial(1)], offers=[offer(99, 1)])
    _, df = run(tmp_path, {"X": (d, d)})
    assert df.loc["X", "TOP_OFFER_BEFORE"] == "99"
    assert df.loc["X", "PD_MODEL_BEFORE"] == ""  # продукта в прогонах нет — пусто, не падаем


def test_app_missing_in_after_is_bad_file(tmp_path):
    (tmp_path / "ds").mkdir()
    ds = make_dataset(tmp_path / "ds", {"X": (doc("X", "APPROVE", []), doc("X", "APPROVE", []))})
    (ds / "A" / "X.json").unlink()
    with pytest.raises(BadFile):
        build_segments(ds, tmp_path / "s.csv")


def test_cancel_leaves_no_file(tmp_path):
    out = tmp_path / "s.csv"
    with pytest.raises(Cancelled):
        build_segments(MINI, out, is_cancelled=lambda: True)
    assert not out.exists()


def test_field_map_override_reads_renamed_decision(tmp_path):
    # другая версия СПР: решение лежит в result.verdict — меняем только карту полей, не код
    pairs = {"A1": ({"result": {"verdict": "APPROVE"}}, {"result": {"verdict": "REJECT"}})}
    n, df = run(tmp_path, pairs, field_map={"DECISION": "result.verdict"})
    assert n == 1
    assert (df.loc["A1", "DECISION_BEFORE"], df.loc["A1", "DECISION_AFTER"]) == ("APPROVE", "REJECT")
    assert df.loc["A1", "DECISION_CHANGED"] == "1"


def test_field_map_override_products_array(tmp_path):
    # продукты переехали в другой массив и поле id — «тот же продукт» и его поля читаются по новой карте
    fmap = {"PRODUCTS": "offers_eval[].id", "PD_MODEL": "offers_eval[].pd_model",
            "TOP_OFFER": "shown[].id", "OFFER_RANK": "shown[].pos"}
    b = {"decisionResult": {"decision": "APPROVE"},
         "offers_eval": [{"id": 2, "pd_model": "M2"}, {"id": 1, "pd_model": "M1"}], "shown": [{"id": 2, "pos": 1}]}
    a = {"decisionResult": {"decision": "REJECT"}, "offers_eval": [{"id": 2, "pd_model": "M2"}, {"id": 1, "pd_model": "M1"}]}
    _, df = run(tmp_path, {"A1": (b, a)}, field_map=fmap)
    row = df.loc["A1"]
    assert row["PRODUCTS"] == "1|2"
    assert (row["TOP_OFFER_BEFORE"], row["TOP_OFFER_AFTER"]) == ("2", "")
    assert (row["PD_MODEL_BEFORE"], row["PD_MODEL_AFTER"]) == ("M2", "M1")  # без выдачи — наименьший id


def test_field_map_empty_path_gives_empty_column(tmp_path):
    _, df = run(tmp_path, {"A1": (doc("A1", "APPROVE", [trial(1)], okb=700), doc("A1", "APPROVE", [trial(1)], okb=710))},
                field_map={"SCORE_OKB": ""})
    assert df.loc["A1", "SCORE_OKB_BEFORE"] == "" and df.loc["A1", "SCORE_OKB_AFTER"] == ""


def test_field_map_products_must_be_array(tmp_path):
    with pytest.raises(BadFile, match="PRODUCTS"):
        run(tmp_path, {"A1": (doc("A1", "APPROVE", []), doc("A1", "APPROVE", []))},
            field_map={"PRODUCTS": "decisionResult.product_id"})


def test_read_field():
    from pipeline.segments import read_field
    d = doc("A1", "APPROVE", [trial(1), trial(2)], okb=700)
    assert read_field(d, "DECISION") == "APPROVE"
    assert read_field(d, "PRODUCTS") == [1, 2]
    assert read_field(d, "SCORE_OKB") == 700
    assert read_field({}, "DECISION") is None
    assert read_field(d, "DECISION", {"DECISION": "x.y"}) is None


def test_progress_reaches_total(tmp_path):
    seen = []
    build_segments(MINI, tmp_path / "s.csv", on_progress=seen.append)
    assert seen[-1] == 3


@pytest.mark.skipif(not (REAL / "manifest.json").exists(), reason="нет настоящего датасета")
def test_real_dataset(tmp_path):
    out = tmp_path / "segments.csv"
    n = build_segments(REAL, out)
    df = read_csv(out)
    assert n == len(df) == 2002
    assert df["APP_ID"].is_unique
    assert (df["DECISION_CHANGED"] == "1").sum() == 385
    pair = df[df["DECISION_CHANGED"] == "1"].groupby(["DECISION_BEFORE", "DECISION_AFTER"]).size()
    assert pair[("APPROVE", "REJECT")] == 273
    assert pair[("REJECT", "APPROVE")] == 112
    row = df.set_index("APP_ID")
    assert (row.loc["I32554354", "DECISION_BEFORE"], row.loc["I32554354", "DECISION_AFTER"]) == ("REJECT", "APPROVE")
    assert (row.loc["I32554362", "DECISION_BEFORE"], row.loc["I32554362", "DECISION_AFTER"]) == ("APPROVE", "REJECT")
