#!/usr/bin/env python3
"""Provision the table schemas of the four ailiance-llm-* Grist docs.

One-shot, idempotent. Reads four doc IDs from env / grist.env, then
ensures every table of LLM_DOCS exists in its document.

Usage::

    python scripts/provision_llm_docs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_PKG_PARENT = Path(__file__).resolve().parent.parent  # .../mascarade-eval
if str(_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_PKG_PARENT))

from mascarade_eval.grist.client import GristClient, load_doc_id  # noqa: E402
from mascarade_eval.grist.llm_schema import LLM_DOCS, provision_doc  # noqa: E402

DOC_ENV = {
    "domain": "GRIST_DOC_LLM_DOMAIN",
    "training": "GRIST_DOC_LLM_TRAINING",
    "bench": "GRIST_DOC_LLM_BENCH",
    "workflow": "GRIST_DOC_LLM_WORKFLOW",
}


def resolve_doc_ids() -> dict[str, str]:
    """Return {doc_key: doc_id} from env. Exits if any is missing."""
    ids: dict[str, str] = {}
    for key, env_name in DOC_ENV.items():
        doc_id = load_doc_id(env_name)
        if not doc_id:
            sys.exit(f"missing {env_name} (env or grist.env)")
        ids[key] = doc_id
    return ids


def main() -> int:
    doc_ids = resolve_doc_ids()
    for key, tables in LLM_DOCS.items():
        client = GristClient.from_env(doc_ids[key])
        report = provision_doc(client, tables)
        print(f"ailiance-llm-{key} ({doc_ids[key]}): {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
