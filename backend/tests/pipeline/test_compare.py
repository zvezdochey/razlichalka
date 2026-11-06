"""Тесты сравнения срезов. Маленькие CSV в tests/fixtures/compare — выдуманные."""

import time
from pathlib import Path

import pytest

from pipeline.compare import COLUMNS, compare_csv
from pipeline.csvio import read_csv, write_csv
from pipeline.errors import BadFile

FIX = Path(__file__).parent.parent / "fixtures" / "compare"
NORM_COLS = ["APP_ID", "SOURCE", "PREFIX", "CLASS", "SUFFIX", "ARRAY_KEY", "KEY", "PATH", "VALUE", "ADJUSTED_VALUE"]

_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = next(
    (p for p in [
        _ROOT / "ПАКЕТ/ЗАДАНИЕ/example",
        _ROOT / "ПАКЕТ/ПАКЕТ/ЗАДАНИЕ/ЗАДАНИЕ/example",
    ] if (p / "06_comparison.csv").is_file()),
    _ROOT / "ПАКЕТ/ЗАДАНИЕ/example",
)
HAS_EXAMPLE = (EXAMPLE / "06_comparison.csv").is_file()


@pytest.fixture
def mini(tmp_path):
    out = tmp_path / "c.csv"
    n = compare_csv(FIX / "before.csv", FIX / "after.csv", out)
    df = read_csv(out)
    assert n == len(df)
    return df.set_index(["APP_ID", "PATH", "ARRAY_KEY"])


def row(df, app, path, ak=""):
    return df.loc[(app, path, ak)]


def test_columns_and_sort(tmp_path):
    out = tmp_path / "c.csv"
    compare_csv(FIX / "before.csv", FIX / "after.csv", out)
    df = read_csv(out)
    assert list(df.columns) == COLUMNS
    keys = list(zip(df["APP_ID"], df["PATH"], df["ARRAY_KEY"]))
    assert keys == sorted(keys)


def test_app_id_sorted_naturally(tmp_path):
    """id заявок идут как числа: 2, 10, 100, а не 10, 100, 2."""
    def rows(src):
        return [dict(zip(NORM_COLS, [i, src, "p", "c", "", "", "k", "p.c.k", "1", "1"])) for i in ("10", "2", "100")]

    b, a, out = tmp_path / "b.csv", tmp_path / "a.csv", tmp_path / "c.csv"
    write_csv(b, NORM_COLS, rows("BEFORE"))
    write_csv(a, NORM_COLS, rows("AFTER"))
    compare_csv(b, a, out)
    assert list(read_csv(out)["APP_ID"]) == ["2", "10", "100"]


def test_same(mini):
    r = row(mini, "1", "company.decisionResult.decision")
    assert (r["CHANGE_TYPE"], r["DIFF_FLAG"]) == ("SAME", "0")


def test_value_changed(mini):
    r = row(mini, "1", "company.decisionResult.limit")
    assert (r["CHANGE_TYPE"], r["DIFF_FLAG"]) == ("VALUE_CHANGED", "1")
    assert (r["VALUE_BEFORE"], r["VALUE_AFTER"]) == ("100", "90")


def test_change_inside_one_bucket_is_still_changed(mini):
    r = row(mini, "1", "company.scoring.pd[].value", "P1")
    assert r["ADJUSTED_BEFORE"] == r["ADJUSTED_AFTER"]
    assert (r["VALUE_BEFORE"], r["VALUE_AFTER"]) == ("0.42", "0.58")
    assert (r["CHANGE_TYPE"], r["DIFF_FLAG"]) == ("VALUE_CHANGED", "1")
    assert r["SUFFIX"] == "pd"


def test_attribute_new(mini):
    r = row(mini, "1", "company.scoring.fresh")
    assert (r["CHANGE_TYPE"], r["DIFF_FLAG"]) == ("ATTRIBUTE_NEW", "1")
    assert r["VALUE_BEFORE"] == r["ADJUSTED_BEFORE"] == ""
    assert (r["VALUE_AFTER"], r["ADJUSTED_AFTER"]) == ("y", "y")


def test_attribute_lost(mini):
    r = row(mini, "1", "company.scoring.old")
    assert (r["CHANGE_TYPE"], r["DIFF_FLAG"]) == ("ATTRIBUTE_LOST", "1")
    assert r["VALUE_AFTER"] == r["ADJUSTED_AFTER"] == ""
    assert (r["PREFIX"], r["KEY"]) == ("company", "old")


def test_null_string_differs_from_missing(mini):
    # было строкой null, стало пустым значением — это изменение, а не пропажа атрибута
    r = row(mini, "1", "company.scoring.nothing")
    assert r["CHANGE_TYPE"] == "VALUE_CHANGED"
    assert r["VALUE_BEFORE"] == "null"


def test_app_only_in_after(mini):
    r = row(mini, "2", "company.decisionResult.decision")
    assert r["CHANGE_TYPE"] == "ATTRIBUTE_NEW"


def test_only_four_change_types(mini):
    assert set(mini["CHANGE_TYPE"]) == {"SAME", "VALUE_CHANGED", "ATTRIBUTE_NEW", "ATTRIBUTE_LOST"}
    assert set(mini["DIFF_FLAG"]) <= {"0", "1"}


def test_log_summary(tmp_path):
    msgs = []
    compare_csv(FIX / "before.csv", FIX / "after.csv", tmp_path / "c.csv", log=lambda lvl, m: msgs.append((lvl, m)))
    assert len(msgs) == 1 and msgs[0][0] == "info"
    assert "SAME=1" in msgs[0][1] and "ATTRIBUTE_LOST=1" in msgs[0][1]


def test_empty_sides(tmp_path):
    empty = tmp_path / "e.csv"
    write_csv(empty, NORM_COLS, [])
    out = tmp_path / "c.csv"
    assert compare_csv(empty, empty, out) == 0
    assert list(read_csv(out).columns) == COLUMNS
    assert compare_csv(empty, FIX / "after.csv", out) == 6
    assert set(read_csv(out)["CHANGE_TYPE"]) == {"ATTRIBUTE_NEW"}
    assert compare_csv(FIX / "before.csv", empty, out) == 5
    assert set(read_csv(out)["CHANGE_TYPE"]) == {"ATTRIBUTE_LOST"}


def test_duplicate_key_is_error(tmp_path):
    dup = tmp_path / "d.csv"
    r = dict(zip(NORM_COLS, ["1", "BEFORE", "p", "c", "", "", "k", "p.c.k", "1", "1"]))
    write_csv(dup, NORM_COLS, [r, r])
    with pytest.raises(BadFile):
        compare_csv(dup, FIX / "after.csv", tmp_path / "c.csv")


def test_missing_columns_is_error(tmp_path):
    bad = tmp_path / "b.csv"
    write_csv(bad, ["APP_ID"], [{"APP_ID": "1"}])
    with pytest.raises(BadFile):
        compare_csv(bad, FIX / "after.csv", tmp_path / "c.csv")


def _with_path(src: Path, dst: Path) -> Path:
    """В эталонных 03/04 нет колонки PATH (формат старее) — достраиваем: PREFIX.CLASS[.SUFFIX].KEY."""
    df = read_csv(src)
    parts = df[["PREFIX", "CLASS", "SUFFIX", "KEY"]].values
    df["PATH"] = [".".join(x for x in p if x) for p in parts]
    write_csv(dst, NORM_COLS, df.to_dict("records"))
    return dst


@pytest.mark.skipif(not HAS_EXAMPLE, reason="нет ПАКЕТ/ с эталоном организаторов")
def test_matches_reference(tmp_path):
    before = _with_path(EXAMPLE / "03_normalized_BEFORE.csv", tmp_path / "b.csv")
    after = _with_path(EXAMPLE / "04_normalized_AFTER.csv", tmp_path / "a.csv")
    out = tmp_path / "c.csv"
    compare_csv(before, after, out)
    got = read_csv(out)
    ref = read_csv(EXAMPLE / "06_comparison.csv")
    assert list(got.columns) == list(ref.columns)
    assert len(got) == len(ref)
    assert set(map(tuple, got.values)) == set(map(tuple, ref.values))


@pytest.mark.slow
def test_performance_big(tmp_path):
    n = 145_000

    def make(src, shift):
        return [
            dict(zip(NORM_COLS, [str(i // 70), src, "p", "c", "", str(i % 70), "k", "p.c[].k",
                                 str(i + (shift and i % 10 == 0)), str(i)]))
            for i in range(n)
        ]

    b, a = tmp_path / "b.csv", tmp_path / "a.csv"
    write_csv(b, NORM_COLS, make("BEFORE", False))
    write_csv(a, NORM_COLS, make("AFTER", True))
    t = time.time()
    assert compare_csv(b, a, tmp_path / "c.csv") == n
    assert time.time() - t < 30
