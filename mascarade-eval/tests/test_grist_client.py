# tests/test_grist_client.py
import pytest
from mascarade_eval.grist.client import GristClient, load_grist_key


def _recording_transport(log):
    def transport(method, url, key, body):
        log.append((method, url, body))
        if method == "GET" and url.endswith("/tables"):
            return {"tables": [{"id": "Existing"}]}
        if method == "GET" and url.endswith("/columns"):
            return {"columns": [{"id": "item_key"}, {"id": "domain"}]}
        if method == "GET" and "/records" in url:
            return {"records": [
                {"id": 1, "fields": {"item_key": "k1",
                                     "review_status": "pending"}},
                {"id": 2, "fields": {"item_key": "k2",
                                     "review_status": "validated"}},
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
        {"_id": 1, "item_key": "k1", "review_status": "pending"},
        {"_id": 2, "item_key": "k2", "review_status": "validated"},
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


def test_create_table_assigns_column_types():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    c.create_table("T", ("item_key", "n_items", "review_status"))
    method, url, body = log[-1]
    assert method == "POST"
    cols = {col["id"]: col["fields"]["type"]
            for col in body["tables"][0]["columns"]}
    assert cols == {"item_key": "Text", "n_items": "Int",
                    "review_status": "Choice"}


def test_list_columns_returns_ids():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    assert c.list_columns("Heldout_Items") == {"item_key", "domain"}
    method, url, _ = log[-1]
    assert method == "GET"
    assert url.endswith("/docs/doc1/tables/Heldout_Items/columns")


def test_add_columns_posts_choice_with_widget_options():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    c.add_columns("Heldout_Items", ("review_status", "review_note"))
    method, url, body = log[-1]
    assert method == "POST"
    assert url.endswith("/docs/doc1/tables/Heldout_Items/columns")
    by_id = {col["id"]: col["fields"] for col in body["columns"]}
    assert by_id["review_status"]["type"] == "Choice"
    assert "pending" in by_id["review_status"]["widgetOptions"]
    assert by_id["review_note"]["type"] == "Text"


def test_add_columns_noop_on_empty():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    c.add_columns("T", ())
    assert log == []


def test_load_grist_key_prefers_env(monkeypatch):
    monkeypatch.setenv("GRIST_API_KEY", "env-key")
    assert load_grist_key() == "env-key"


def test_upsert_records_puts_with_require_wrapper():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    c.upsert_records("T", [{"name": "n1", "v": "x"}], "name")
    method, url, body = log[-1]
    assert method == "PUT"
    assert "/docs/doc1/tables/T/records?onmany=first" in url
    assert body == {"records": [
        {"require": {"name": "n1"}, "fields": {"name": "n1", "v": "x"}}]}


def test_upsert_records_noop_on_empty():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    c.upsert_records("T", [], "name")
    assert log == []


def test_add_records_splits_oversized_payload_into_multiple_posts():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    # 8 rows each ~100 KB -> ~800 KB total, must split (>500 KB budget)
    big = "x" * 100_000
    rows = [{"a": big} for _ in range(8)]
    c.add_records("T", rows)
    posts = [e for e in log if e[0] == "POST"]
    assert len(posts) >= 2  # one 800 KB POST would 413; must be chunked
    # every row is delivered exactly once across the POSTs
    delivered = [rec for _, _, body in posts
                 for rec in body["records"]]
    assert len(delivered) == 8


def test_add_records_small_rows_still_one_post():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    c.add_records("T", [{"a": "1"}, {"a": "2"}, {"a": "3"}])
    posts = [e for e in log if e[0] == "POST"]
    assert len(posts) == 1  # tiny rows fit in a single chunk
