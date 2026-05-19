from mascarade_eval.grist.grist_migrate import (
    MIGRATION_MAP, map_row, row_hash, migrate_table,
)


def test_map_row_renames_and_keeps_target_columns():
    src = {"_id": 3, "old_name": "v1", "keep": "v2", "drop_me": "v3"}
    out = map_row(src, rename={"old_name": "new_name"},
                  target_columns=("new_name", "keep"))
    assert out == {"new_name": "v1", "keep": "v2"}


def test_map_row_drops_grist_internal_id():
    out = map_row({"_id": 9, "keep": "v"}, rename={},
                  target_columns=("keep",))
    assert "_id" not in out


def test_row_hash_is_order_independent():
    assert row_hash({"a": 1, "b": 2}) == row_hash({"b": 2, "a": 1})


def test_row_hash_differs_on_content():
    assert row_hash({"a": 1}) != row_hash({"a": 2})


def test_migrate_table_copies_and_verifies(fake_client):
    src = fake_client(records={"Src": [
        {"_id": 1, "item_key": "k1", "domain": "kicad", "extra": "x"},
        {"_id": 2, "item_key": "k2", "domain": "spice", "extra": "y"},
    ]})
    tgt = fake_client(tables=[])
    report = migrate_table(
        src, tgt, src_table="Src", tgt_table="Dst",
        tgt_columns=("item_key", "domain"), rename={})
    assert report["copied"] == 2
    assert report["verified"] is True
    assert report["dropped_columns"] == ["extra"]
    written = tgt.added["Dst"]
    assert {r["item_key"] for r in written} == {"k1", "k2"}
    assert all("extra" not in r for r in written)


def test_migrate_table_dry_run_writes_nothing(fake_client):
    src = fake_client(records={"Src": [
        {"_id": 1, "item_key": "k1", "domain": "kicad"}]})
    tgt = fake_client(tables=[])
    report = migrate_table(
        src, tgt, src_table="Src", tgt_table="Dst",
        tgt_columns=("item_key", "domain"), rename={}, dry_run=True)
    assert report["copied"] == 1
    assert tgt.added == {}


def test_migration_map_targets_known_docs():
    valid = {"heldout_old", "mascarade_old", "training_old",
             "domain", "training", "bench"}
    for entry in MIGRATION_MAP:
        assert entry["src_doc"] in valid
        assert entry["tgt_doc"] in valid
        assert isinstance(entry["rename"], dict)


def test_migrate_table_verifies_fan_in_into_non_empty_target(fake_client):
    # A fan-in target already holds a prior batch's rows; the new
    # batch must still verify True — only its own delta is checked.
    src = fake_client(records={"Src": [
        {"_id": 1, "item_key": "k1", "domain": "kicad"}]})
    tgt = fake_client(records={"Dst": [
        {"_id": 9, "item_key": "pre", "domain": "spice"}]})
    report = migrate_table(
        src, tgt, src_table="Src", tgt_table="Dst",
        tgt_columns=("item_key", "domain"), rename={})
    assert report["copied"] == 1
    assert report["verified"] is True
