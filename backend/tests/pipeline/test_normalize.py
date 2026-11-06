"""Тесты приведения среза в CSV. Мини-датасет в tests/fixtures/dataset_mini — выдуманный."""

import shutil
from pathlib import Path

import pytest

from pipeline.csvio import read_csv, write_csv
from pipeline.dataset import list_source_files, read_manifest
from pipeline.errors import BadFile, Cancelled
from pipeline.flatten import COLUMNS
from pipeline.normalize import normalize_dataset
from tests.real_dataset import REAL

MINI = Path(__file__).parent.parent / "fixtures" / "dataset_mini"
CFG = {"ignore_paths": ["appData.request_id", "appData.createDateTime"]}


def run(tmp_path, source="BEFORE", cfg=CFG, dataset=MINI, **kw):
    out = tmp_path / "n.csv"
    n = normalize_dataset(dataset, source, out, cfg, **kw)
    return n, read_csv(out)


def test_csv_columns_and_count(tmp_path):
    n, df = run(tmp_path)
    assert list(df.columns) == COLUMNS
    assert n == len(df) > 0
    assert set(df["SOURCE"]) == {"BEFORE"}
    assert set(df["APP_ID"]) == {"A1", "A2", "A3"}


def test_no_duplicate_keys(tmp_path):
    _, df = run(tmp_path, "AFTER")
    assert not df.duplicated(["APP_ID", "PATH", "ARRAY_KEY"]).any()


def test_ignore_paths_cut_technical_fields(tmp_path):
    _, df = run(tmp_path)
    assert not df["PATH"].str.contains("request_id|createDateTime").any()
    _, df2 = run(tmp_path, cfg={})
    assert df2["PATH"].str.contains("request_id").any()


def test_array_keys_and_values(tmp_path):
    _, df = run(tmp_path)
    row = df[(df.APP_ID == "A1") & (df.PATH == "decisionResult.product_trials[].scoring.pd.value") & (df.ARRAY_KEY == "1")]
    assert list(row["VALUE"]) == ["0.694"]


def test_progress_and_log(tmp_path):
    progress, logs = [], []
    run(tmp_path, on_progress=progress.append, log=lambda lvl, m: logs.append((lvl, m)))
    assert progress == [3]
    assert ("info", "Обработано 3 из 3") in logs


def test_cancelled(tmp_path):
    with pytest.raises(Cancelled):
        run(tmp_path, is_cancelled=lambda: True)


def test_broken_json(tmp_path):
    ds = tmp_path / "ds"
    shutil.copytree(MINI, ds)
    (ds / "RESULTS" / "BEFORE" / "A2.json").write_text("{не json", encoding="utf-8")
    with pytest.raises(BadFile, match="A2.json"):
        run(tmp_path, dataset=ds)


def test_app_id_mismatch(tmp_path):
    ds = tmp_path / "ds"
    shutil.copytree(MINI, ds)
    (ds / "RESULTS" / "BEFORE" / "A2.json").write_text('{"appData": {"application_id": "ZZZ"}}', encoding="utf-8")
    with pytest.raises(BadFile, match="A2.json"):
        run(tmp_path, dataset=ds)


def test_manifest_errors(tmp_path):
    with pytest.raises(BadFile):
        read_manifest(tmp_path)
    assert [p.stem for p in list_source_files(MINI, "AFTER")] == ["A1", "A2", "A3"]
    with pytest.raises(BadFile):
        list_source_files(MINI, "OTHER")


def test_csvio_roundtrip_keeps_null(tmp_path):
    p = tmp_path / "x.csv"
    assert write_csv(p, ["a", "b"], iter([{"a": "null", "b": "NA"}, {"a": "", "b": "1"}])) == 2
    df = read_csv(p)
    assert list(df["a"]) == ["null", ""] and list(df["b"]) == ["NA", "1"]
    assert p.read_bytes().startswith(b"\xef\xbb\xbf")


@pytest.mark.skipif(not (REAL / "manifest.json").exists(), reason="нет настоящего датасета")
@pytest.mark.parametrize("source", ["BEFORE", "AFTER"])
def test_real_dataset(tmp_path, source):
    n, df = run(tmp_path, source, dataset=REAL)
    assert n == len(df) > 250_000
    assert not df["PATH"].str.contains("request_id|createDateTime").any()
    assert not df.duplicated(["APP_ID", "PATH", "ARRAY_KEY"]).any()


@pytest.mark.skipif(not (REAL / "manifest.json").exists(), reason="нет настоящего датасета")
@pytest.mark.parametrize("source, rows", [("BEFORE", 291_047), ("AFTER", 292_033)])
def test_real_dataset_rows_with_procedure_rules(tmp_path, source, rows):
    # правила массивов из backend/procedures/builtin_normalize.py дают те же строки, что были в коде (array_rules.py)
    n, _ = run(tmp_path, source, cfg={}, dataset=REAL)
    assert n == rows


def test_no_partial_csv_on_failure(tmp_path):
    out = tmp_path / "n.csv"
    with pytest.raises(Cancelled):
        normalize_dataset(MINI, "BEFORE", out, CFG, is_cancelled=lambda: True)
    assert not out.exists() and not list(tmp_path.glob("*.tmp"))
    ds = tmp_path / "ds"
    shutil.copytree(MINI, ds)
    (ds / "RESULTS" / "BEFORE" / "A3.json").write_text("{не json", encoding="utf-8")
    with pytest.raises(BadFile):
        normalize_dataset(ds, "BEFORE", out, CFG)
    assert not out.exists() and not list(tmp_path.glob("*.tmp"))


def test_bad_buckets_is_bad_file(tmp_path):
    # кривые границы в старой конфигурации — понятная ошибка этапа, а не internal
    with pytest.raises(BadFile, match="бакеты"):
        run(tmp_path, cfg={**CFG, "buckets": {"a[].b": [1], "a.b": [2]}})
