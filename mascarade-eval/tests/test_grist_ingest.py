# tests/test_grist_ingest.py
from mascarade_eval.grist import TRAINING_TABLE, TRAINING_COLUMNS
from mascarade_eval.grist.ingest import item_key, compute_delta, ingest_rows


def test_item_key_is_deterministic_and_domain_prefixed():
    k1 = item_key("kicad", "How do I add a net class?")
    k2 = item_key("kicad", "How do I add a net class?")
    assert k1 == k2
    assert k1.startswith("kicad-")


def test_item_key_differs_by_text():
    assert item_key("kicad", "A") != item_key("kicad", "B")


def test_compute_delta_skips_existing_keys():
    existing = {"kicad-aaaaaaaaaa"}
    incoming = [
        {"item_key": "kicad-aaaaaaaaaa", "user_msg": "old"},
        {"item_key": "kicad-bbbbbbbbbb", "user_msg": "new"},
    ]
    delta = compute_delta(existing, incoming)
    assert [r["item_key"] for r in delta] == ["kicad-bbbbbbbbbb"]


def test_compute_delta_dedupes_within_batch():
    incoming = [
        {"item_key": "k1", "user_msg": "x"},
        {"item_key": "k1", "user_msg": "x-dup"},
    ]
    delta = compute_delta(set(), incoming)
    assert len(delta) == 1
    assert delta[0]["user_msg"] == "x"


def test_ingest_rows_inserts_only_new(fake_client):
    client = fake_client(
        tables=[TRAINING_TABLE],
        records={TRAINING_TABLE: [{"item_key": "k1", "user_msg": "kept"}]},
    )
    rows = [
        {"item_key": "k1", "user_msg": "WOULD OVERWRITE"},
        {"item_key": "k2", "user_msg": "fresh"},
    ]
    report = ingest_rows(client, TRAINING_TABLE, TRAINING_COLUMNS, rows)
    assert report == {"inserted": 1, "skipped": 1}
    assert client.added[TRAINING_TABLE] == [{"item_key": "k2",
                                             "user_msg": "fresh"}]


def test_ingest_rows_creates_table_when_absent(fake_client):
    client = fake_client(tables=[])
    ingest_rows(client, TRAINING_TABLE, TRAINING_COLUMNS,
                [{"item_key": "k1"}])
    assert client.created == [(TRAINING_TABLE, TRAINING_COLUMNS)]


def test_ingest_rows_dry_run_writes_nothing(fake_client):
    client = fake_client(tables=[TRAINING_TABLE])
    report = ingest_rows(client, TRAINING_TABLE, TRAINING_COLUMNS,
                         [{"item_key": "k1"}], dry_run=True)
    assert report == {"inserted": 1, "skipped": 0}
    assert client.added == {}
