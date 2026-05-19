# mascarade_eval/grist/grist_migrate.py
"""Schema-adaptive migration of Grist tables into the ailiance-llm docs.

map_row / row_hash are pure. migrate_table copies one table source ->
target, keeping only target-declared columns, and verifies row-by-row
via content hashes. MIGRATION_MAP is the declarative table list.
"""
from __future__ import annotations

import hashlib
import json


def map_row(row: dict, rename: dict[str, str],
            target_columns: tuple[str, ...]) -> dict:
    """Rename keys, then keep only keys present in target_columns.

    The Grist-internal `_id` is always dropped.
    """
    renamed = {rename.get(k, k): v for k, v in row.items() if k != "_id"}
    return {k: v for k, v in renamed.items() if k in target_columns}


def row_hash(row: dict) -> str:
    """SHA256 of a row's canonical JSON (key-sorted)."""
    canon = json.dumps(row, ensure_ascii=False, sort_keys=True,
                        default=str)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def migrate_table(src_client, tgt_client, src_table: str, tgt_table: str,
                  tgt_columns: tuple[str, ...], rename: dict[str, str],
                  dry_run: bool = False) -> dict:
    """Copy src_table -> tgt_table, keeping target columns, verified.

    Returns {copied, verified, dropped_columns}. `dropped_columns` lists
    source columns absent from the target schema (after rename) — a
    dry-run surfaces these so the operator can add renames.

    Verification confirms this batch landed in full: the target row
    count grew by exactly len(mapped), and every source row's mapped
    hash is present. Fan-in (several sources into one target) is fine.
    """
    src_rows = src_client.fetch_records(src_table)
    mapped = [map_row(r, rename, tgt_columns) for r in src_rows]

    dropped: set[str] = set()
    for r in src_rows:
        renamed = {rename.get(k, k) for k in r if k != "_id"}
        dropped |= {k for k in renamed if k not in tgt_columns}

    report = {
        "copied": len(mapped),
        "verified": False,
        "dropped_columns": sorted(dropped),
    }
    if dry_run:
        return report

    tgt_client.ensure_table(tgt_table, tgt_columns)
    pre_count = len(tgt_client.fetch_records(tgt_table))
    tgt_client.add_records(tgt_table, mapped)
    post = tgt_client.fetch_records(tgt_table)

    want = sorted(row_hash(m) for m in mapped)
    got = sorted(row_hash(map_row(r, {}, tgt_columns)) for r in post)
    added = len(post) - pre_count
    report["verified"] = added == len(want) and all(h in got for h in want)
    return report


# Declarative migration table — 4 entries with real source docs.
# `rename` starts empty; a dry-run prints `dropped_columns` per entry
# so the operator adds renames where a drop is unintended, before the
# real run.
#
# Sources:
#   heldout_old  — ailiance-llm-heldout-legacy (fixed doc ID)
#   mascarade_old — mascarade-data (fixed doc ID)
# Targets:
#   bench        — ailiance-llm-bench (env GRIST_DOC_LLM_BENCH)
MIGRATION_MAP: list[dict] = [
    {"src_doc": "heldout_old", "src_table": "Heldout_Items",
     "tgt_doc": "bench", "tgt_table": "Eval_Items", "rename": {}},
    {"src_doc": "mascarade_old", "src_table": "Mascarade_Eval",
     "tgt_doc": "bench", "tgt_table": "Bench_Results", "rename": {}},
    {"src_doc": "mascarade_old", "src_table": "Bench_31_domains",
     "tgt_doc": "bench", "tgt_table": "Bench_Results", "rename": {}},
    {"src_doc": "mascarade_old", "src_table": "Mascarade_Eval_Items",
     "tgt_doc": "bench", "tgt_table": "Eval_Items", "rename": {}},
]
