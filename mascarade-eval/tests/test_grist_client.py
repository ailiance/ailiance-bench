# tests/test_grist_client.py
import pytest
from mascarade_eval.grist.client import GristClient, load_grist_key


def _recording_transport(log):
    def transport(method, url, key, body):
        log.append((method, url, body))
        if method == "GET" and url.endswith("/tables"):
            return {"tables": [{"id": "Existing"}]}
        if method == "GET" and "/records" in url:
            return {"records": [
                {"id": 1, "fields": {"item_key": "k1", "exclure": False}},
                {"id": 2, "fields": {"item_key": "k2", "exclure": True}},
            ]}
        return {}
    return transport


def test_list_tables_returns_ids():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    assert c.list_tables() == {"Existing"}
    assert log[0][0] == "GET"
    assert log[0][1] == "https://grist.saillant.cc/api/docs/doc1/tables"


def test_fetch_records_flattens_id_into_fields():
    c = GristClient("doc1", "key1", transport=_recording_transport([]))
    rows = c.fetch_records("Mascarade_Training")
    assert rows == [
        {"_id": 1, "item_key": "k1", "exclure": False},
        {"_id": 2, "item_key": "k2", "exclure": True},
    ]


def test_add_records_posts_fields_wrapped():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    c.add_records("T", [{"a": "1"}, {"a": "2"}])
    method, url, body = log[-1]
    assert method == "POST"
    assert url.endswith("/docs/doc1/tables/T/records")
    assert body == {"records": [{"fields": {"a": "1"}},
                                {"fields": {"a": "2"}}]}


def test_add_records_noop_on_empty():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    c.add_records("T", [])
    assert log == []


def test_create_table_types_exclure_as_bool():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    c.create_table("T", ("item_key", "exclure", "n_items"))
    method, url, body = log[-1]
    assert method == "POST"
    cols = {col["id"]: col["fields"]["type"] for col in body["tables"][0]["columns"]}
    assert cols == {"item_key": "Text", "exclure": "Bool", "n_items": "Int"}


def test_load_grist_key_prefers_env(monkeypatch):
    monkeypatch.setenv("GRIST_API_KEY", "env-key")
    assert load_grist_key() == "env-key"
