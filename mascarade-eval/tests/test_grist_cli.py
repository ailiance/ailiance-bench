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


def test_parser_accepts_schema_command():
    ns = build_parser().parse_args(["schema"])
    assert ns.command == "schema"


def test_schema_command_runs_over_review_targets(monkeypatch, fake_client):
    from mascarade_eval.grist import cli
    made = fake_client(tables=["Heldout_Items"],
                       columns={"Heldout_Items": ["item_key"]})
    monkeypatch.setattr(cli.GristClient, "from_env",
                        classmethod(lambda c, doc: made))
    rc = cli.main(["schema"])
    assert rc == 0
    assert made.added_columns["Heldout_Items"]


def test_parser_export_accepts_include_pending():
    ns = build_parser().parse_args(
        ["export", "--doc", "D", "--domain", "kicad", "--include-pending"])
    assert ns.include_pending is True
