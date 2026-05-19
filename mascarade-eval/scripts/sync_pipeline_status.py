#!/usr/bin/env python3
"""Sync the workflow doc's Pipeline_Status table.

Reads the domain/training/bench/workflow doc IDs and the gateway URL
from env / grist.env, fetches the gateway model list, and upserts one
Pipeline_Status row per domain.

Usage::

    python scripts/sync_pipeline_status.py --dry-run
    python scripts/sync_pipeline_status.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PKG_PARENT = Path(__file__).resolve().parent.parent
if str(_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_PKG_PARENT))

from mascarade_eval.grist.client import GristClient, load_doc_id  # noqa: E402
from mascarade_eval.grist.pipeline_sync import (  # noqa: E402
    fetch_served_aliases, sync_pipeline,
)

DOC_ENV = {
    "domain": "GRIST_DOC_LLM_DOMAIN",
    "training": "GRIST_DOC_LLM_TRAINING",
    "bench": "GRIST_DOC_LLM_BENCH",
    "workflow": "GRIST_DOC_LLM_WORKFLOW",
}
GATEWAY_ENV = "GRIST_GATEWAY_URL"


def resolve_config() -> dict:
    """Return {doc_ids: {key: id}, gateway_url}. Exits if any missing."""
    doc_ids: dict[str, str] = {}
    for key, env_name in DOC_ENV.items():
        doc_id = load_doc_id(env_name)
        if not doc_id:
            sys.exit(f"missing {env_name} (env or grist.env)")
        doc_ids[key] = doc_id
    gateway_url = load_doc_id(GATEWAY_ENV)
    if not gateway_url:
        sys.exit(f"missing {GATEWAY_ENV} (env or grist.env)")
    return {"doc_ids": doc_ids, "gateway_url": gateway_url}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="compute status, write nothing")
    args = ap.parse_args(argv)

    cfg = resolve_config()
    ids = cfg["doc_ids"]
    served = fetch_served_aliases(cfg["gateway_url"])
    report = sync_pipeline(
        GristClient.from_env(ids["domain"]),
        GristClient.from_env(ids["training"]),
        GristClient.from_env(ids["bench"]),
        GristClient.from_env(ids["workflow"]),
        served=served, dry_run=args.dry_run)
    for domain, row in sorted(report.items()):
        flags = {k: row[k] for k in
                 ("sourced", "trained", "evaluated", "served")}
        print(f"{domain}: {flags}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
