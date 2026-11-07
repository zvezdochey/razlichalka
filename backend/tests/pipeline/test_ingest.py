import io
import zipfile

import pytest

from pipeline.errors import BadFile
from pipeline.ingest import iter_files, split_apps

ARRAYS = {"decisionResult.product_trials[]", "decisionResult.available_offers[]", "decisionResult.product_trials[].rules[]"}


def one(name, data, arrays=ARRAYS):
    return split_apps(name, "." + name.rsplit(".", 1)[1], data, arrays)


def test_json_one_app_and_list():
    assert one("I1.json", b'{"appData": {"application_id": "I1"}}') == [{"appData": {"application_id": "I1"}}]
    docs = one("all.json", b'[{"appData": {"application_id": "A"}}, {"appData": {"application_id": "B"}}]')
    assert [d["appData"]["application_id"] for d in docs] == ["A", "B"]


def test_app_id_from_file_name_and_numbers_become_strings():
    assert one("I7.json", b'{"decisionResult": {}}')[0]["appData"]["application_id"] == "I7"
    assert one("x.json", b'{"appData": {"application_id": 123}}')[0]["appData"]["application_id"] == "123"


def test_bad_app_id_is_rejected():
    with pytest.raises(BadFile, match="недопустимый id"):
        one("x.json", b'{"appData": {"application_id": "../evil"}}')
    with pytest.raises(BadFile, match="недопустимый id"):
        one("x.json", b'{"appData": {"application_id": ".."}}')


def test_xml_arrays_types_and_empty_array():
    xml = (b'<response><appData><application_id>I1</application_id><score>0.5</score><ok>true</ok></appData>'
           b'<decisionResult><available_offers/><product_trials><product_id>1</product_id>'
           b'<rules><name>A</name><hit>false</hit></rules></product_trials></decisionResult></response>')
    doc = one("I1.xml", xml)[0]
    assert doc["appData"] == {"application_id": "I1", "score": 0.5, "ok": True}
    assert doc["decisionResult"]["available_offers"] == []
    # один элемент массива остаётся массивом, потому что путь есть в правилах
    assert doc["decisionResult"]["product_trials"] == [{"product_id": 1, "rules": [{"name": "A", "hit": False}]}]


def test_xml_forbids_entities_and_reports_syntax_errors():
    with pytest.raises(BadFile, match="запрещены"):
        one("x.xml", b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY e "x">]><a>&e;</a>')
    with pytest.raises(BadFile, match="не разобрать как XML"):
        one("x.xml", b"<a><b></a>")


def test_csv_long_table_semicolon_comma_and_cp1251():
    text = "path;value\nappData.application_id;I2\ndecisionResult.available_offers;[]\n" \
           "decisionResult.product_trials[0].product_id;7\ndecisionResult.product_trials[1].product_id;8\n"
    doc = one("I2.csv", text.encode())[0]
    assert doc["decisionResult"]["available_offers"] == []
    assert [t["product_id"] for t in doc["decisionResult"]["product_trials"]] == [7, 8]
    assert one("r.csv", b"path;value\na[0].x;1\na[1].x;2\n")[0]["a"] == [{"x": 1}, {"x": 2}]
    assert one("I2.csv", text.replace(";", ",").encode())[0] == doc
    ru = "путь;значение\nappData.application_id;I3\ndecisionResult.decision;Отказ\n".encode("cp1251")
    assert one("I3.csv", ru)[0]["decisionResult"]["decision"] == "Отказ"


def test_csv_many_apps_by_application_id_column():
    text = "application_id;path;value\nA;decisionResult.decision;APPROVE\nB;decisionResult.decision;REJECT\n"
    docs = one("all.csv", text.encode())
    assert [(d["appData"]["application_id"], d["decisionResult"]["decision"]) for d in docs] == [("A", "APPROVE"), ("B", "REJECT")]


@pytest.mark.parametrize("text, message", [
    ("a;b\n1;2\n", "нужны колонки path и value"),
    ("path;value\nx[0;1\n", "записан неверно"),
    ("path;value\na.b;1\na.b;2\n", "встречается дважды"),
    ("path;value\na;1\na.b;2\n", "другого вида"),
    ("path;value\n", "нет строк с данными"),
    ("path;value\na[5].x;1\n", "индексы идут по порядку"),
    ("path;value\nx;1e999\n", "слишком большое"),
])
def test_csv_errors_name_the_row(text, message):
    with pytest.raises(BadFile, match=message):
        one("x.csv", text.encode())


def make_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_zip_skips_junk_and_keeps_supported_files():
    data = make_zip({"BEFORE/I1.json": "{}", "__MACOSX/BEFORE/._I1.json": "x", "manifest.json": "{}", "readme.txt": "hi", ".hidden.json": "{}"})
    assert [n for n, _, _ in iter_files("s.zip", data)] == ["s.zip/BEFORE/I1.json"]


def test_zip_errors():
    with pytest.raises(BadFile, match="не zip"):
        list(iter_files("s.zip", b"not a zip"))
    with pytest.raises(BadFile, match="слишком много"):
        list(iter_files("s.zip", make_zip({"a.json": "{" + " " * 100 + "}"}), budget=[10]))


def test_hostile_input_gives_bad_file_not_500():
    with pytest.raises(BadFile):
        one("x.json", b"[" * 100_000)
    with pytest.raises(BadFile):
        one("x.json", b'{"x": NaN}')
    with pytest.raises(BadFile):
        one("x.xml", ("<a>" * 5000 + "</a>" * 5000).encode())
    with pytest.raises(BadFile):
        one("x.xml", '<!DOCTYPE r [<!ENTITY a "x">]><r><v>&a;</v></r>'.encode("utf-16"))
    big = one("x.csv", b"path;value\nappData.application_id;I1\nx;" + b"9" * 5000 + b"\n")  # длинное число — просто строка
    assert big[0]["x"] == "9" * 5000
    with pytest.raises(BadFile):
        one("x.json", b'{"appData": {"application_id": "ab\\n"}}')
