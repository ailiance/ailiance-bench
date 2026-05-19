# mascarade_eval/grist/ingest.py
"""Insert-only ingestion into Grist.

This module holds the source-of-truth invariant: an existing item row is
NEVER updated, so human edits in Grist survive re-ingestion.
"""
from __future__ import annotations

import hashlib


def item_key(domain: str, text: str) -> str:
    """Stable key for an item: domain prefix + SHA1 of its text."""
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"{domain}-{digest}"


def compute_delta(existing_keys: set[str], incoming: list[dict],
                  key_field: str = "item_key") -> list[dict]:
    """Return only rows whose key is absent from Grist and unseen in batch."""
    seen: set[str] = set(existing_keys)
    delta: list[dict] = []
    for row in incoming:
        key = row[key_field]
        if key in seen:
            continue
        seen.add(key)
        delta.append(row)
    return delta


def ingest_rows(client, table: str, columns: tuple[str, ...],
                rows: list[dict], key_field: str = "item_key",
                dry_run: bool = False) -> dict:
    """Insert-only ingestion. Returns {"inserted": n, "skipped": n}."""
    client.ensure_table(table, columns)
    existing = {r[key_field] for r in client.fetch_records(table)
                if key_field in r}
    delta = compute_delta(existing, rows, key_field)
    if not dry_run:
        client.add_records(table, delta)
    return {"inserted": len(delta), "skipped": len(rows) - len(delta)}
