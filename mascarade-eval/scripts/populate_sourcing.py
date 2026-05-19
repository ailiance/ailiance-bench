#!/usr/bin/env python3
"""Populate the Sourcing table of the ailiance-llm-domain doc.

For each domain directory under HF_DIR, scans its train.jsonl and
writes one Sourcing row with the corpus summary (count, licenses,
sources, disk path). The corpus itself stays on disk — Grist holds
only the summary.

Usage::

    python scripts/populate_sourcing.py
    python scripts/populate_sourcing.py --hf-dir <path>
    python scripts/populate_sourcing.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_PKG_PARENT = Path(__file__).resolve().parent.parent
if str(_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_PKG_PARENT))

from mascarade_eval.grist.client import GristClient, load_doc_id  # noqa: E402
from mascarade_eval.grist.llm_schema import LLM_DOCS  # noqa: E402

DEFAULT_HF_DIR = Path("/Users/electron/Documents/Projets/eu-kiki/data/hf-traced")
DOMAIN_DOC_ENV = "GRIST_DOC_LLM_DOMAIN"


def compute_sourcing(domain_dir: Path) -> dict | None:
    """Summarise one domain directory. Returns None if no train.jsonl."""
    train = domain_dir / "train.jsonl"
    if not train.is_file():
        return None
    licenses: Counter = Counter()
    sources: Counter = Counter()
    n = 0
    with train.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            prov = rec.get("_provenance") or {}
            licenses[prov.get("license", "")] += 1
            sources[prov.get("source", "")] += 1
            n += 1
    extras = sorted(p.name for p in domain_dir.iterdir()
                    if p.is_file() and p.name != "train.jsonl"
                    and p.suffix == ".jsonl")
    return {
        "domain": domain_dir.name,
        "n_records": n,
        "n_licenses": len([k for k in licenses if k]),
        "n_sources": len([k for k in sources if k]),
        "licenses": json.dumps(dict(licenses), ensure_ascii=False),
        "sources": json.dumps(sorted(k for k in sources if k),
                              ensure_ascii=False),
        "local_path": str(train),
        "extra_files": ", ".join(extras),
        "notes": "",
    }


def resolve_doc_id() -> str:
    doc_id = load_doc_id(DOMAIN_DOC_ENV)
    if not doc_id:
        sys.exit(f"missing {DOMAIN_DOC_ENV} (env or grist.env)")
    return doc_id


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hf-dir", default=str(DEFAULT_HF_DIR),
                    help="root with per-domain dirs containing train.jsonl")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute summaries, write nothing to Grist")
    args = ap.parse_args(argv)

    hf_dir = Path(args.hf_dir)
    if not hf_dir.is_dir():
        sys.exit(f"hf-dir not found: {hf_dir}")

    rows: list[dict] = []
    skipped: list[str] = []
    for child in sorted(hf_dir.iterdir()):
        if not child.is_dir():
            continue
        row = compute_sourcing(child)
        if row is None:
            skipped.append(child.name)
            continue
        rows.append(row)
        print(f"  {row['domain']}: {row['n_records']} records, "
              f"{row['n_licenses']} licenses, {row['n_sources']} sources")
    if skipped:
        print(f"[info] skipped (no train.jsonl): {skipped}")

    if args.dry_run:
        print(f"dry-run: would upsert {len(rows)} rows")
        return 0

    doc_id = resolve_doc_id()
    client = GristClient.from_env(doc_id)
    cols = LLM_DOCS["domain"]["Sourcing"]
    client.ensure_table("Sourcing", cols)
    client.upsert_records("Sourcing", rows, "domain")
    print(f"upserted {len(rows)} rows to Sourcing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
