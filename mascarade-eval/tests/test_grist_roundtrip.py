# tests/test_grist_roundtrip.py
import json
from mascarade_eval.grist.migrate import migrate_domain
from mascarade_eval.grist.export import export_domain


def test_migrate_then_export_round_trips(fake_client, tmp_path):
    source = [
        {"messages": [{"role": "user", "content": "Q1"},
                      {"role": "assistant", "content": "A1"}]},
        {"messages": [{"role": "system", "content": "S"},
                      {"role": "user", "content": "Q2"},
                      {"role": "assistant", "content": "A2"}]},
    ]
    client = fake_client(tables=[])
    migrate_domain(client, "kicad", records=source)
    # Migrated rows start as review_status=pending; include them so the
    # round-trip exercises message semantics independent of review state.
    report = export_domain(client, "kicad", out_dir=tmp_path,
                           include_pending=True)

    assert report["n_items"] == 2
    out_file = tmp_path / report["output_file"]
    exported = [json.loads(ln) for ln in out_file.read_text().splitlines()]

    def norm(msgs):
        return sorted(json.dumps(m, sort_keys=True) for m in msgs)

    source_sets = {tuple(norm(r["messages"])) for r in source}
    export_sets = {tuple(norm(r["messages"])) for r in exported}
    assert source_sets == export_sets


def test_double_ingest_inserts_zero_the_second_time(fake_client):
    source = [{"messages": [{"role": "user", "content": "Q"},
                            {"role": "assistant", "content": "A"}]}]
    client = fake_client(tables=[])
    migrate_domain(client, "kicad", records=source)
    second = migrate_domain(client, "kicad", records=source)
    assert second["inserted"] == 0
