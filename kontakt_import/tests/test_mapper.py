from datetime import date

from yuvomi_import.mapper import Options, map_rows, clean_postal, split_emails
from yuvomi_import.reader import FIELDS


def row(line, **kw):
    r = {f: "" for f in FIELDS}
    r.update(kw)
    r["_line"] = line
    return r


def test_household_block_inherits_last_name_and_resets_on_blank():
    rows = [
        row(1, last_name="Giese", first_name="Brigitte"),
        row(2, first_name="Hans Erich"),
        row(3),
        row(4, first_name="Solo"),
    ]
    m = map_rows(rows)
    assert [x.payload.get("lastName") for x in m] == ["Giese", "Giese", None]
    assert len(m) == 3


def test_no_inherit_flag():
    m = map_rows([row(1, last_name="A", first_name="B"), row(2, first_name="C")],
                 Options(inherit_last_name=False))
    assert "lastName" not in m[1].payload


def test_email_with_comment_goes_to_notes():
    found, rest = split_emails("familie.giese@arcor.de (gemeinsam)")
    assert found == ["familie.giese@arcor.de"] and rest == "gemeinsam"


def test_postal_and_dates():
    assert clean_postal("47574.0") == "47574"
    assert clean_postal(6114) == "06114"
    assert clean_postal("CZ-17100") == "CZ-17100"
    m = map_rows([row(1, first_name="A", birthday=date(1960, 10, 5))])
    assert m[0].payload["birthday"] == "1960-10-05"
    m = map_rows([row(1, first_name="A", birthday="05.10.1960")])
    assert m[0].payload["birthday"] == "1960-10-05"


def test_full_row_payload():
    m = map_rows([row(1, last_name="Koch", first_name="Katharina", birthday="1990-04-14",
                      street="Willbecker Busch 25", postal_code="40699", city="Erkrath",
                      phone_home="02104 5055592", email="k@gmx.de", phone_mobile="0162 3206803",
                      note="WhatsApp")])[0].payload
    assert m["phones"][0] == {"label": "Festnetz", "value": "02104 5055592", "isPrimary": True}
    assert m["phones"][1]["isPrimary"] is False
    assert m["emails"][0]["value"] == "k@gmx.de"
    assert m["addresses"][0]["postalCode"] == "40699"
    assert m["notes"] == "WhatsApp"


def test_nameless_row_merges_into_previous():
    m = map_rows([row(1, last_name="Giese", first_name="Hans", email="a@b.de"),
                  row(2, email="familie@arcor.de (gemeinsam)")])
    assert len(m) == 1
    assert [e["value"] for e in m[0].payload["emails"]] == ["a@b.de", "familie@arcor.de"]
    assert "gemeinsam" in m[0].payload["notes"]
