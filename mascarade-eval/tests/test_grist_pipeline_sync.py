from mascarade_eval.grist.pipeline_sync import (
    collect_domains, domain_status,
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
