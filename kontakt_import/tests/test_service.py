import json
import os

import pytest

from yuvomi_import.credentials import SecretsError, load_yuvomi_secrets
from yuvomi_import.mapper import Mapped
from yuvomi_import.sync import resolve_categories, run_sync


class FakeClient:
    def __init__(self):
        self.cats = [{"key": "family", "name": None}, {"key": "misc", "name": "Sonstige"}]
        self.created, self.posted = [], []

    def list_categories(self):
        return self.cats

    def create_category(self, name):
        self.created.append(name)
        return {"key": name.lower()}

    def list_contacts(self):
        return [{"id": 7, "first_name": "Eva", "last_name": "Giese", "name": "Eva Giese"}]

    def create_contact(self, payload):
        self.posted.append(payload)
        return {"id": 100 + len(self.posted)}


def items():
    return [Mapped(1, {"firstName": "A", "lastName": "B", "category": "Sonstige"}),
            Mapped(2, {"firstName": "C", "lastName": "D", "category": "Neu"}),
            Mapped(3, {"firstName": "Eva", "lastName": "Giese", "category": "family"})]


def test_resolve_dry_run_does_not_create():
    c, it = FakeClient(), items()
    resolve_categories(c, it, create=True, apply=False, log=lambda *_: None)
    assert c.created == [] and it[0].payload["category"] == "misc"
    assert it[1].payload["category"] == "Neu" and "wuerde angelegt" in it[1].warnings[0]


def test_resolve_apply_creates_and_unknown_without_create_falls_back():
    c, it = FakeClient(), items()
    resolve_categories(c, it, create=True, apply=True, log=lambda *_: None)
    assert c.created == ["Neu"] and it[1].payload["category"] == "neu"
    c2, it2 = FakeClient(), items()
    resolve_categories(c2, it2, create=False, apply=True, log=lambda *_: None)
    assert "category" not in it2[1].payload and c2.created == []


def test_run_sync_skips_existing_and_creates_new():
    c = FakeClient()
    res = run_sync(items(), c, apply=True, update=False)
    assert [r.action for r in res] == ["create", "create", "skip-exists"]
    assert len(c.posted) == 2


def test_secrets_file(tmp_path):
    p = tmp_path / "secrets.json"
    p.write_text(json.dumps({"familie_username": "x", "yuvomi_url": "http://h", "yuvomi_api_token": "yuvomi_t"}))
    os.chmod(p, 0o600)
    s = load_yuvomi_secrets(p)
    assert s.url == "http://h" and s.verify_tls is True and s.warning is None
    assert "yuvomi_t" not in repr(s)
    os.chmod(p, 0o644)
    assert load_yuvomi_secrets(p).warning
    p.write_text("{}")
    with pytest.raises(SecretsError):
        load_yuvomi_secrets(p)
    with pytest.raises(SecretsError):
        load_yuvomi_secrets(tmp_path / "nope.json")
