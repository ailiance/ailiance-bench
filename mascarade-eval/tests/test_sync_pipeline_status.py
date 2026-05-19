import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sync_pipeline_status as s  # noqa: E402


def test_doc_env_covers_the_four_docs():
    assert set(s.DOC_ENV) == {"domain", "training", "bench", "workflow"}
    assert s.DOC_ENV["workflow"] == "GRIST_DOC_LLM_WORKFLOW"


def test_resolve_config_reads_docs_and_gateway(monkeypatch):
    monkeypatch.setattr(s, "load_doc_id", lambda name: f"id-{name}")
    cfg = s.resolve_config()
    assert cfg["doc_ids"]["domain"] == "id-GRIST_DOC_LLM_DOMAIN"
    assert cfg["gateway_url"] == "id-GRIST_GATEWAY_URL"


def test_resolve_config_exits_on_missing(monkeypatch):
    monkeypatch.setattr(
        s, "load_doc_id",
        lambda name: None if name == "GRIST_GATEWAY_URL" else "x")
    with pytest.raises(SystemExit):
        s.resolve_config()
