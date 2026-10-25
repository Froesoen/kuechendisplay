from pathlib import Path

from openpyxl import Workbook

from yuvomi_import.mapper import map_rows, parse_partial_date
from yuvomi_import.reader import read_table

HEADER = ["Nachname", "Vorname", "Geburtsdatum", "Straße", "PLZ", "Ort",
          "Handynummer", "Festnetznummer", "E-Mailadresse", "Kategorie"]


def make_xlsx(path: Path, rows: list[list], header=HEADER) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append(r)
    wb.save(path)
    return path


def test_real_world_headers_are_mapped(tmp_path):
    f = make_xlsx(tmp_path / "a.xlsx", [["Giese", "Brigitte", "05.10.1960", "Im Kreuzfeld 10", "40885",
                                         "Ratingen", "+49 162 7263805", "+49 2102 37213", "b@g.de", "Familie"]])
    p = map_rows(read_table(f))[0]
    assert [x["label"] for x in p.payload["phones"]] == ["Festnetz", "Mobil"]
    assert p.payload["phones"][1]["value"] == "+49 162 7263805"
    assert p.payload["emails"][0]["value"] == "b@g.de"
    assert p.payload["category"] == "Familie"
    assert not p.warnings


def test_partial_birthday_sets_year_unknown(tmp_path):
    assert parse_partial_date("08.11.") == "2000-11-08"
    assert parse_partial_date("8.11") == "2000-11-08"
    assert parse_partial_date("29.02.") == "2000-02-29"
    assert parse_partial_date("31.04.") is None
    assert parse_partial_date("08.11.2026") is None
    f = make_xlsx(tmp_path / "b.xlsx", [["Kleis", "Wilfried", "08.11.", "", "", "", "", "", "", ""]])
    pl = map_rows(read_table(f))[0].payload
    assert pl["birthday"] == "2000-11-08" and pl["birthday_year_unknown"] is True


def test_full_birthday_has_no_year_unknown_flag(tmp_path):
    f = make_xlsx(tmp_path / "c.xlsx", [["Koch", "Katharina", "14.04.1990", "", "", "", "", "", "", ""]])
    pl = map_rows(read_table(f))[0].payload
    assert pl["birthday"] == "1990-04-14" and "birthday_year_unknown" not in pl


def test_unknown_header_columns_are_reported(tmp_path):
    f = make_xlsx(tmp_path / "d.xlsx", [["A", "B", "Fax-Nummer"]], header=["Nachname", "Vorname", "Fax"])
    m = map_rows(read_table(f))
    assert any("Fax" in w for w in m[0].warnings)
