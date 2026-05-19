# tests/test_grist_export.py
import json
import pytest
from mascarade_eval.grist import TRAINING_TABLE, EXPORTS_TABLE
from mascarade_eval.grist.export import (
    canonical_jsonl, content_hash, export_domain,
)


def test_canonical_jsonl_sorts_by_key():
    keyed = [("b", {"v": 2}), ("a", {"v": 1})]
    lines = canonical_jsonl(keyed).splitlines()
    assert json.loads(lines[0]) == {"v": 1}
    assert json.loads(lines[1]) == {"v": 2}


def test_canonical_jsonl_is_order_independent():
    a = [("x", {"v": 1}), ("y", {"v": 2})]
    b = [("y", {"v": 2}), ("x", {"v": 1})]
    assert canonical_jsonl(a) == canonical_jsonl(b)


def test_canonical_jsonl_omits_the_sort_key_from_output():
    text = canonical_jsonl([("x", {"v": 1})])
    assert json.loads(text) == {"v": 1}  # no "x", no item_key


def test_content_hash_stable():
    text = canonical_jsonl([("x", {"v": 1})])
    assert content_hash(text) == content_hash(text)
    assert len(content_hash(text)) == 64


def test_export_domain_filters_excluded_and_writes_file(fake_client, tmp_path):
    client = fake_client(
        tables=[TRAINING_TABLE],
        records={TRAINING_TABLE: [
            {"_id": 1, "item_key": "kicad-1", "domain": "kicad",
             "user_msg": "Q1", "assistant_msg": "A1", "system": "",
             "extra_turns": "", "source": "", "exclure": False, "notes": ""},
            {"_id": 2, "item_key": "kicad-2", "domain": "kicad",
             "user_msg": "Q2", "assistant_msg": "A2", "system": "",
             "extra_turns": "", "source": "", "exclure": True, "notes": ""},
        ]},
    )
    report = export_domain(client, "kicad", out_dir=tmp_path)
    assert report["n_items"] == 1  # the excluded row is dropped
    out_file = tmp_path / report["output_file"]
    assert out_file.exists()
    written = [json.loads(ln) for ln in out_file.read_text().splitlines()]
    assert written == [{"messages": [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1"},
    ]}]
    assert client.added[EXPORTS_TABLE][0]["domain"] == "kicad"
    assert client.added[EXPORTS_TABLE][0]["content_hash"] == report["content_hash"]


def test_export_domain_dry_run_writes_nothing(fake_client, tmp_path):
    client = fake_client(
        tables=[TRAINING_TABLE],
        records={TRAINING_TABLE: [
            {"_id": 1, "item_key": "kicad-1", "domain": "kicad",
             "user_msg": "Q", "assistant_msg": "A", "system": "",
             "extra_turns": "", "exclure": False}]},
    )
    report = export_domain(client, "kicad", out_dir=tmp_path, dry_run=True)
    assert report["n_items"] == 1
    assert list(tmp_path.iterdir()) == []
    assert client.added == {}


def test_export_domain_removes_file_when_grist_logging_fails(
        fake_client, tmp_path):
    client = fake_client(
        tables=[TRAINING_TABLE],
        records={TRAINING_TABLE: [
            {"_id": 1, "item_key": "kicad-1", "domain": "kicad",
             "user_msg": "Q", "assistant_msg": "A", "system": "",
             "extra_turns": "", "exclure": False}]},
    )

    def boom(table, rows):
        raise RuntimeError("grist down")

    client.add_records = boom
    with pytest.raises(RuntimeError, match="grist down"):
        export_domain(client, "kicad", out_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []  # no orphaned snapshot file
