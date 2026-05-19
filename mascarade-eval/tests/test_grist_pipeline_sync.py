from mascarade_eval.grist.pipeline_sync import (
    collect_domains, domain_status, fetch_served_aliases,
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
