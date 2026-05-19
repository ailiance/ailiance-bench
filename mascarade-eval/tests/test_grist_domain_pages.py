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
