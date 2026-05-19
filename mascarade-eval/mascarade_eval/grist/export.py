# mascarade_eval/grist/export.py
"""Deterministic Grist -> .jsonl snapshot export, journaled in Exports."""
from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path

from . import EXPORTS_COLUMNS, EXPORTS_TABLE, TRAINING_TABLE
from .migrate import rebuild_messages


def canonical_jsonl(keyed_rows: list[tuple[str, dict]]) -> str:
    """Serialize (sort_key, object) pairs to JSONL ordered by sort_key.

    Same input set -> same bytes, regardless of input order. The sort key
    itself is not written; only the object is.
    """
    ordered = sorted(keyed_rows, key=lambda kv: kv[0])
    return "\n".join(json.dumps(obj, ensure_ascii=False, sort_keys=True)
                     for _, obj in ordered)


def content_hash(text: str) -> str:
    """SHA256 hex digest of the canonical snapshot text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _timestamp() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")


def export_domain(client, domain: str, out_dir: Path,
                  dry_run: bool = False) -> dict:
    """Export one domain's non-excluded training rows to a hashed snapshot.

    Returns a report dict matching the Exports row written to Grist.
    """
    rows = [r for r in client.fetch_records(TRAINING_TABLE)
            if r.get("domain") == domain and not r.get("exclure")]
    payload = canonical_jsonl(
        [(r.get("item_key", ""), rebuild_messages(r)) for r in rows])
    digest = content_hash(payload)
    stamp = _timestamp()
    filename = f"{domain}.{stamp}.jsonl"
    report = {
        "export_id": f"{domain}-{stamp}",
        "domain": domain,
        "created_at": stamp,
        "n_items": len(rows),
        "content_hash": digest,
        "output_file": filename,
        "hf_dataset_id": "",
    }
    if dry_run:
        return report
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / filename).write_text(payload + ("\n" if payload else ""),
                                    encoding="utf-8")
    client.ensure_table(EXPORTS_TABLE, EXPORTS_COLUMNS)
    client.add_records(EXPORTS_TABLE, [report])
    return report
