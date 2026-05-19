# tests/test_grist_schema.py
from mascarade_eval.grist import REVIEW_COLUMNS
from mascarade_eval.grist.schema import ensure_review_columns, migrate_doc


def test_ensure_review_columns_adds_all_when_absent(fake_client):
    client = fake_client(tables=["Heldout_Items"],
                         columns={"Heldout_Items": ["item_key", "prompt"]})
    added = ensure_review_columns(client, "Heldout_Items")
    assert added == list(REVIEW_COLUMNS)
    assert client.added_columns["Heldout_Items"] == list(REVIEW_COLUMNS)


def test_ensure_review_columns_is_idempotent(fake_client):
    cols = ["item_key", *REVIEW_COLUMNS]
    client = fake_client(tables=["Heldout_Items"],
                         columns={"Heldout_Items": cols})
    added = ensure_review_columns(client, "Heldout_Items")
    assert added == []
    assert "Heldout_Items" not in client.added_columns


def test_ensure_review_columns_adds_only_missing(fake_client):
    client = fake_client(
        tables=["Datasets"],
        columns={"Datasets": ["domain", "review_status", "reviewer"]})
    added = ensure_review_columns(client, "Datasets")
    assert added == ["reviewed_at", "review_note"]


def test_migrate_doc_skips_absent_tables(fake_client):
    client = fake_client(tables=["Heldout_Items"],
                         columns={"Heldout_Items": ["item_key"]})
    report = migrate_doc(client, ("Heldout_Items", "Mascarade_Training"))
    assert report["Heldout_Items"] == list(REVIEW_COLUMNS)
    assert report["Mascarade_Training"] is None
