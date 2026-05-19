import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_domain_pages as b  # noqa: E402


def test_resolve_doc_id_returns_the_env_value(monkeypatch):
    monkeypatch.setattr(b, "load_doc_id", lambda name: f"id-{name}")
    assert b.resolve_doc_id() == "id-GRIST_DOC_LLM_DOMAIN"


def test_resolve_doc_id_exits_when_unset(monkeypatch):
    monkeypatch.setattr(b, "load_doc_id", lambda name: None)
    with pytest.raises(SystemExit):
        b.resolve_doc_id()
