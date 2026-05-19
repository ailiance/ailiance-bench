import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import migrate_grist_docs as m  # noqa: E402


def test_fixed_source_docs_are_the_known_ids():
    assert m.SRC_FIXED["heldout_old"] == "eGbbrpzN3TeLq3sUd2YFA2"
    assert m.SRC_FIXED["mascarade_old"] == "dhyrySCayizD1PNqCNhCPN"


def test_resolve_doc_ids_merges_fixed_and_env(monkeypatch):
    monkeypatch.setattr(m, "load_doc_id", lambda name: f"id-{name}")
    ids = m.resolve_doc_ids()
    assert ids["heldout_old"] == "eGbbrpzN3TeLq3sUd2YFA2"
    assert ids["domain"] == "id-GRIST_DOC_LLM_DOMAIN"
    assert ids["bench"] == "id-GRIST_DOC_LLM_BENCH"


def test_resolve_doc_ids_exits_on_missing_env(monkeypatch):
    monkeypatch.setattr(
        m, "load_doc_id",
        lambda name: None if name == "GRIST_DOC_LLM_BENCH" else "x")
    with pytest.raises(SystemExit):
        m.resolve_doc_ids()
