# mascarade_eval/grist/schema.py
"""Add the human-review columns to existing Grist tables (idempotent).

A column already present on a table is never recreated, so re-running
the migration is safe. New tables created by the pipeline already carry
the review columns via TRAINING_COLUMNS.
"""
from __future__ import annotations

from . import REVIEW_COLUMNS


def ensure_review_columns(client, table: str) -> list[str]:
    """Add any missing review column to one table. Returns columns added."""
    existing = client.list_columns(table)
    missing = [c for c in REVIEW_COLUMNS if c not in existing]
    if missing:
        client.add_columns(table, tuple(missing))
    return missing


def migrate_doc(client, tables: tuple[str, ...]) -> dict:
    """Ensure review columns on each table that exists in the document.

    A table absent from the document is reported as None (skipped).
    """
    present = client.list_tables()
    report: dict = {}
    for table in tables:
        if table in present:
            report[table] = ensure_review_columns(client, table)
        else:
            report[table] = None
    return report
