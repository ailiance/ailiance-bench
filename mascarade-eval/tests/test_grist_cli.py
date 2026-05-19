# tests/test_grist_cli.py
import pytest
from mascarade_eval.grist.cli import build_parser, resolve_doc


def test_parser_ingest_requires_doc_and_jsonl():
    ns = build_parser().parse_args(
        ["ingest", "--doc", "D", "--jsonl", "mine.jsonl", "--domain", "kicad"])
    assert ns.command == "ingest"
    assert ns.doc == "D"
    assert ns.jsonl == "mine.jsonl"
    assert ns.domain == "kicad"


def test_parser_export_accepts_dry_run():
    ns = build_parser().parse_args(
        ["export", "--doc", "D", "--domain", "kicad", "--dry-run"])
    assert ns.command == "export"
    assert ns.dry_run is True


def test_parser_migrate_and_publish():
    p = build_parser()
    m = p.parse_args(["migrate", "--doc", "D", "--domain", "kicad"])
    assert m.command == "migrate"
    pub = p.parse_args(
        ["publish", "--snapshot", "exports/kicad.x.jsonl",
         "--hf-dataset", "Ailiance-fr/mascarade-kicad-dataset",
         "--filename", "kicad_chat.jsonl"])
    assert pub.command == "publish"
    assert pub.hf_dataset == "Ailiance-fr/mascarade-kicad-dataset"


def test_resolve_doc_prefers_explicit_arg():
    assert resolve_doc("explicit-id") == "explicit-id"


def test_resolve_doc_errors_when_unset(monkeypatch):
    monkeypatch.delenv("GRIST_DOC_TRAINING", raising=False)
    monkeypatch.setattr("mascarade_eval.grist.cli.load_doc_id",
                        lambda name: None)
    with pytest.raises(SystemExit):
        resolve_doc(None)


def test_ingest_jsonl_rows_exits_on_missing_file(tmp_path):
    from mascarade_eval.grist.cli import _ingest_jsonl_rows
    with pytest.raises(SystemExit):
        _ingest_jsonl_rows("kicad", str(tmp_path / "does-not-exist.jsonl"))
