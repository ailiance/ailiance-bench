from mascarade_eval.grist.domain_pages import reconcile_domains


def test_reconcile_all_present():
    rows = [{"domain": "kicad"}, {"domain": "spice"}]
    out = reconcile_domains(rows, ("kicad", "spice"))
    assert out["expected"] == ["kicad", "spice"]
    assert out["present"] == ["kicad", "spice"]
    assert out["orphans"] == []
    assert out["missing"] == []


def test_reconcile_flags_orphan_domains():
    rows = [{"domain": "kicad"}, {"domain": "weird"}]
    out = reconcile_domains(rows, ("kicad", "spice"))
    assert out["orphans"] == ["weird"]


def test_reconcile_flags_missing_domains():
    rows = [{"domain": "kicad"}]
    out = reconcile_domains(rows, ("kicad", "spice"))
    assert out["missing"] == ["spice"]
    assert out["present"] == ["kicad"]


def test_reconcile_ignores_rows_without_domain():
    rows = [{"domain": "kicad"}, {"other": "x"}, {"domain": ""}]
    out = reconcile_domains(rows, ("kicad",))
    assert out["orphans"] == []
    assert out["present"] == ["kicad"]


def test_reconcile_lists_are_sorted():
    rows = [{"domain": "spice"}, {"domain": "kicad"}]
    out = reconcile_domains(rows, ("spice", "kicad"))
    assert out["expected"] == ["kicad", "spice"]
    assert out["present"] == ["kicad", "spice"]


def test_page_plan_describes_the_domain_page():
    from mascarade_eval.grist.domain_pages import page_plan
    plan = page_plan("kicad")
    assert plan["page_name"] == "Domain: kicad"
    assert plan["widgets"] == ["Sourcing", "Dataset_Items"]
    assert plan["filter"] == {"column": "domain", "value": "kicad"}


def test_page_plan_distinct_per_domain():
    from mascarade_eval.grist.domain_pages import page_plan
    assert page_plan("spice")["page_name"] != page_plan("kicad")["page_name"]
    assert page_plan("spice")["filter"]["value"] == "spice"
