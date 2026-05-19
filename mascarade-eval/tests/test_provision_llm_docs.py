import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import provision_llm_docs as p  # noqa: E402


def test_doc_env_covers_the_four_docs():
    assert set(p.DOC_ENV) == {"domain", "training", "bench", "workflow"}
    assert p.DOC_ENV["domain"] == "GRIST_DOC_LLM_DOMAIN"


def test_resolve_doc_ids_reads_each_env_var(monkeypatch):
    monkeypatch.setattr(p, "load_doc_id",
                        lambda name: f"id-for-{name}")
    ids = p.resolve_doc_ids()
    assert ids == {
        "domain": "id-for-GRIST_DOC_LLM_DOMAIN",
        "training": "id-for-GRIST_DOC_LLM_TRAINING",
        "bench": "id-for-GRIST_DOC_LLM_BENCH",
        "workflow": "id-for-GRIST_DOC_LLM_WORKFLOW",
    }


def test_resolve_doc_ids_exits_when_one_is_missing(monkeypatch):
    monkeypatch.setattr(
        p, "load_doc_id",
        lambda name: None if name == "GRIST_DOC_LLM_BENCH" else "x")
    with pytest.raises(SystemExit):
        p.resolve_doc_ids()
