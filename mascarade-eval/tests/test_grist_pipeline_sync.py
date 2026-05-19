from mascarade_eval.grist.pipeline_sync import (
    collect_domains, domain_status, fetch_served_aliases,
    resolve_sync_config, sync_pipeline,
)


def test_collect_domains_unions_the_three_sources():
    domain_rows = [{"domain": "kicad"}, {"domain": "spice"}]
    training_rows = [{"domain": "kicad"}]
    bench_rows = [{"domain": "stm32"}]
    assert collect_domains(domain_rows, training_rows, bench_rows) == {
        "kicad", "spice", "stm32"}


def test_collect_domains_ignores_rows_without_domain():
    assert collect_domains([{"domain": "kicad"}, {"other": "x"}],
                           [], []) == {"kicad"}


def test_domain_status_all_flags_true():
    row = domain_status("kicad", sourced=True, trained=True,
                        evaluated=True, served=True)
    assert row["domain"] == "kicad"
    assert row["sourced"] is True
    assert row["trained"] is True
    assert row["evaluated"] is True
    assert row["served"] is True
    assert row["notes"] == ""
    assert row["updated_at"].endswith("Z")


def test_domain_status_mixed_flags():
    row = domain_status("spice", sourced=True, trained=False,
                        evaluated=False, served=False)
    assert row["sourced"] is True
    assert row["trained"] is False
    assert set(row) == {"domain", "sourced", "trained", "evaluated",
                        "served", "updated_at", "notes"}


def test_fetch_served_aliases_extracts_model_ids():
    def fake_transport(url):
        assert url == "https://gw.example/v1/models"
        return {"data": [{"id": "ailiance-kicad"},
                         {"id": "ailiance-spice"}]}
    aliases = fetch_served_aliases("https://gw.example",
                                   transport=fake_transport)
    assert aliases == {"ailiance-kicad", "ailiance-spice"}


def test_fetch_served_aliases_handles_empty_data():
    aliases = fetch_served_aliases("https://gw.example",
                                   transport=lambda url: {"data": []})
    assert aliases == set()


def test_fetch_served_aliases_strips_trailing_slash():
    seen = {}

    def fake_transport(url):
        seen["url"] = url
        return {"data": []}
    fetch_served_aliases("https://gw.example/", transport=fake_transport)
    assert seen["url"] == "https://gw.example/v1/models"


def test_sync_pipeline_upserts_per_domain_status(fake_client):
    domain_c = fake_client(records={"Sourcing": [
        {"domain": "kicad"}, {"domain": "spice"}]})
    training_c = fake_client(records={"Training_Runs": [
        {"domain": "kicad"}]})
    bench_c = fake_client(records={"Mascarade_Eval": [
        {"domain": "kicad"}]})
    workflow_c = fake_client(tables=[])

    report = sync_pipeline(domain_c, training_c, bench_c, workflow_c,
                           served={"ailiance-kicad"})

    assert set(report) == {"kicad", "spice"}
    assert report["kicad"]["sourced"] is True
    assert report["kicad"]["trained"] is True
    assert report["kicad"]["evaluated"] is True
    assert report["kicad"]["served"] is True
    assert report["spice"]["sourced"] is True
    assert report["spice"]["trained"] is False
    assert report["spice"]["served"] is False
    upserted = workflow_c.upserted["Pipeline_Status"]
    assert {r["domain"] for r in upserted} == {"kicad", "spice"}


def test_resolve_sync_config_reads_docs_and_gateway(monkeypatch):
    import mascarade_eval.grist.pipeline_sync as ps
    monkeypatch.setattr(ps, "load_doc_id", lambda name: f"id-{name}")
    cfg = resolve_sync_config()
    assert cfg["doc_ids"]["domain"] == "id-GRIST_DOC_LLM_DOMAIN"
    assert cfg["doc_ids"]["workflow"] == "id-GRIST_DOC_LLM_WORKFLOW"
    assert cfg["gateway_url"] == "id-GRIST_GATEWAY_URL"


def test_resolve_sync_config_exits_on_missing(monkeypatch):
    import mascarade_eval.grist.pipeline_sync as ps
    monkeypatch.setattr(
        ps, "load_doc_id",
        lambda name: None if name == "GRIST_GATEWAY_URL" else "x")
    import pytest
    with pytest.raises(SystemExit):
        resolve_sync_config()


def test_sync_pipeline_dry_run_writes_nothing(fake_client):
    domain_c = fake_client(records={"Sourcing": [{"domain": "kicad"}]})
    training_c = fake_client(records={"Training_Runs": []})
    bench_c = fake_client(records={"Mascarade_Eval": []})
    workflow_c = fake_client(tables=[])
    report = sync_pipeline(domain_c, training_c, bench_c, workflow_c,
                           served=set(), dry_run=True)
    assert set(report) == {"kicad"}
    assert workflow_c.upserted == {}
