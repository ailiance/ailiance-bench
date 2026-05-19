# tests/test_grist_migrate_domain.py
from mascarade_eval.grist import TRAINING_TABLE, REGISTRY_TABLE
from mascarade_eval.grist.migrate import migrate_domain


def test_migrate_domain_ingests_flattened_rows(fake_client):
    client = fake_client(tables=[])
    records = [
        {"messages": [{"role": "user", "content": "Q1"},
                      {"role": "assistant", "content": "A1"}]},
        {"messages": [{"role": "user", "content": "Q2"},
                      {"role": "assistant", "content": "A2"}]},
    ]
    report = migrate_domain(client, "kicad", records=records)
    assert report["inserted"] == 2
    added = client.added[TRAINING_TABLE]
    assert {r["user_msg"] for r in added} == {"Q1", "Q2"}
    assert all(r["domain"] == "kicad" for r in added)
    assert all(r["item_key"].startswith("kicad-") for r in added)
    assert all(r["review_status"] == "pending" for r in added)


def test_migrate_domain_is_idempotent(fake_client):
    client = fake_client(tables=[])
    records = [{"messages": [{"role": "user", "content": "Q"},
                             {"role": "assistant", "content": "A"}]}]
    migrate_domain(client, "kicad", records=records)
    report2 = migrate_domain(client, "kicad", records=records)
    assert report2 == {"inserted": 0, "skipped": 1}


def test_migrate_domain_writes_registry_row(fake_client):
    client = fake_client(tables=[])
    records = [{"messages": [{"role": "user", "content": "Q"},
                             {"role": "assistant", "content": "A"}]}]
    migrate_domain(client, "kicad", records=records)
    reg = client.upserted[REGISTRY_TABLE]
    assert reg[0]["name"] == "mascarade-kicad-train"
    assert reg[0]["family"] == "mascarade-training"
    assert reg[0]["hf_dataset_id"] == "Ailiance-fr/mascarade-kicad-dataset"


def test_migrate_domain_registry_row_is_upserted_not_duplicated(fake_client):
    client = fake_client(tables=[])
    records = [{"messages": [{"role": "user", "content": "Q"},
                             {"role": "assistant", "content": "A"}]}]
    migrate_domain(client, "kicad", records=records)
    migrate_domain(client, "kicad", records=records)
    from mascarade_eval.grist import REGISTRY_TABLE
    reg_rows = [r for r in client.fetch_records(REGISTRY_TABLE)]
    assert len([r for r in reg_rows if r["name"] == "mascarade-kicad-train"]) == 1
