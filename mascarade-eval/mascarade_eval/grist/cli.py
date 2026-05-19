# mascarade_eval/grist/cli.py
"""CLI for Grist-backed dataset management: ingest / export / migrate / publish.

Run: python -m mascarade_eval.grist.cli <subcommand> [options]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import EXPORTS_DIR, TRAINING_COLUMNS, TRAINING_TABLE
from .client import GristClient, load_doc_id
from .export import export_domain
from .ingest import item_key, ingest_rows
from .migrate import flatten_messages, migrate_domain
from .publish import publish_snapshot


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="grist-dataset", description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    p_ing = sub.add_parser("ingest", help="insert-only ingest a .jsonl")
    p_ing.add_argument("--doc")
    p_ing.add_argument("--jsonl", required=True)
    p_ing.add_argument("--domain", required=True)
    p_ing.add_argument("--dry-run", action="store_true")

    p_exp = sub.add_parser("export", help="export a domain to a snapshot")
    p_exp.add_argument("--doc")
    p_exp.add_argument("--domain", required=True)
    p_exp.add_argument("--dry-run", action="store_true")
    p_exp.add_argument("--include-pending", action="store_true",
                       help="also export rows still pending review")

    p_mig = sub.add_parser("migrate", help="backfill a domain from HF")
    p_mig.add_argument("--doc")
    p_mig.add_argument("--domain", required=True)
    p_mig.add_argument("--dry-run", action="store_true")

    p_pub = sub.add_parser("publish", help="upload a snapshot to HF")
    p_pub.add_argument("--snapshot", required=True)
    p_pub.add_argument("--hf-dataset", required=True)
    p_pub.add_argument("--filename", required=True)

    sub.add_parser("schema", help="add review columns to existing tables")

    p_sync = sub.add_parser("sync", help="sync workflow Pipeline_Status")
    p_sync.add_argument("--dry-run", action="store_true")

    return ap


def resolve_doc(doc_arg: str | None) -> str:
    """Return the doc ID from --doc or the GRIST_DOC_TRAINING env/file value.

    Exits the program (sys.exit) if neither source provides a doc ID.
    """
    if doc_arg:
        return doc_arg
    doc = load_doc_id("GRIST_DOC_TRAINING")
    if not doc:
        sys.exit("no doc ID: pass --doc or set GRIST_DOC_TRAINING")
    return doc


def _ingest_jsonl_rows(domain: str, jsonl_path: str) -> list[dict]:
    try:
        text = Path(jsonl_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        sys.exit(f"file not found: {jsonl_path}")
    except UnicodeDecodeError as exc:
        sys.exit(f"cannot decode {jsonl_path}: {exc}")
    rows: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            print(f"[warn] skipped malformed line: {exc}", file=sys.stderr)
            continue
        flat = flatten_messages(record)
        rows.append({
            "item_key": item_key(domain, flat["user_msg"]),
            "domain": domain,
            "system": flat["system"],
            "user_msg": flat["user_msg"],
            "assistant_msg": flat["assistant_msg"],
            "extra_turns": flat["extra_turns"],
            "source": record.get("source", ""),
            "notes": "",
            "review_status": "pending",
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "publish":
        publish_snapshot(args.snapshot, args.hf_dataset, args.filename)
        print(f"published {args.snapshot} -> {args.hf_dataset}")
        return 0

    if args.command == "schema":
        from . import REVIEW_TARGETS
        from .schema import migrate_doc
        for doc_id, tables in REVIEW_TARGETS.items():
            doc_client = GristClient.from_env(doc_id)
            report = migrate_doc(doc_client, tables)
            print(f"schema {doc_id}: {report}")
        return 0

    if args.command == "sync":
        from .pipeline_sync import (
            fetch_served_aliases, resolve_sync_config, sync_pipeline,
        )
        cfg = resolve_sync_config()
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

    client = GristClient.from_env(resolve_doc(args.doc))

    if args.command == "ingest":
        rows = _ingest_jsonl_rows(args.domain, args.jsonl)
        report = ingest_rows(client, TRAINING_TABLE, TRAINING_COLUMNS, rows,
                             dry_run=args.dry_run)
        print(f"ingest {args.domain}: {report}")
    elif args.command == "export":
        report = export_domain(client, args.domain, EXPORTS_DIR,
                               dry_run=args.dry_run,
                               include_pending=args.include_pending)
        print(f"export {args.domain}: {report}")
    elif args.command == "migrate":
        report = migrate_domain(client, args.domain, dry_run=args.dry_run)
        print(f"migrate {args.domain}: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
