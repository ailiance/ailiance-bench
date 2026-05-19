#!/usr/bin/env python3
"""Migrate existing Grist tables into the four ailiance-llm-* docs.

Row-by-row verified. Use --dry-run first: it prints, per table, the
source columns that would be dropped (not in the target schema), so
renames can be added to MIGRATION_MAP before the real run.

Usage::

    python scripts/migrate_grist_docs.py --dry-run
    python scripts/migrate_grist_docs.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PKG_PARENT = Path(__file__).resolve().parent.parent
if str(_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_PKG_PARENT))

from mascarade_eval.grist.client import GristClient, load_doc_id  # noqa: E402
from mascarade_eval.grist.grist_migrate import (  # noqa: E402
    MIGRATION_MAP, migrate_table,
)
from mascarade_eval.grist.llm_schema import LLM_DOCS  # noqa: E402

# Source docs that are not configurable (known fixed IDs).
SRC_FIXED = {
    "heldout_old": "eGbbrpzN3TeLq3sUd2YFA2",
    "mascarade_old": "dhyrySCayizD1PNqCNhCPN",
}
# Doc keys resolved from env / grist.env.
ENV_DOCS = {
    "training_old": "GRIST_DOC_TRAINING",
    "domain": "GRIST_DOC_LLM_DOMAIN",
    "training": "GRIST_DOC_LLM_TRAINING",
    "bench": "GRIST_DOC_LLM_BENCH",
}

# The workflow doc (Pipeline_Status, Audit_Log) is populated at runtime, not migrated.
# Which doc key supplies the target column tuples.
_TGT_SCHEMA = {
    "domain": LLM_DOCS["domain"],
    "training": LLM_DOCS["training"],
    "bench": LLM_DOCS["bench"],
}


def resolve_doc_ids() -> dict[str, str]:
    """Return {doc_key: doc_id}; fixed sources + env-resolved ones."""
    ids = dict(SRC_FIXED)
    for key, env_name in ENV_DOCS.items():
        doc_id = load_doc_id(env_name)
        if not doc_id:
            sys.exit(f"missing {env_name} (env or grist.env)")
        ids[key] = doc_id
    return ids


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report dropped columns, write nothing")
    args = ap.parse_args(argv)

    doc_ids = resolve_doc_ids()
    failed = False
    for entry in MIGRATION_MAP:
        src = GristClient.from_env(doc_ids[entry["src_doc"]])
        tgt = GristClient.from_env(doc_ids[entry["tgt_doc"]])
        tgt_columns = _TGT_SCHEMA[entry["tgt_doc"]][entry["tgt_table"]]
        report = migrate_table(
            src, tgt, src_table=entry["src_table"],
            tgt_table=entry["tgt_table"], tgt_columns=tgt_columns,
            rename=entry["rename"], dry_run=args.dry_run)
        tag = f"{entry['src_table']} -> {entry['tgt_doc']}/{entry['tgt_table']}"
        print(f"{tag}: {report}")
        if not args.dry_run and not report["verified"]:
            print(f"  !! verification FAILED for {tag}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
