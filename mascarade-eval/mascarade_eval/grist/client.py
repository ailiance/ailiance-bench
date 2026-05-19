# mascarade_eval/grist/client.py
"""Thin Grist REST client. The HTTP transport is injectable for tests."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from . import GRIST_BASE, KEY_FILE, REVIEW_STATUSES, REVIEWER_CHOICES

_INT_COLS = {"n_items", "n_rows", "n_records", "n_licenses", "n_sources"}
_BOOL_COLS = {"sourced", "trained", "evaluated", "served"}
_MAX_POST_BYTES = 500_000  # keep POST bodies well under Grist's limit
_CHOICE_COLS = {
    "review_status": REVIEW_STATUSES,
    "reviewer": REVIEWER_CHOICES,
}


def _col_fields(name: str) -> dict:
    """Grist column `fields` payload for a column id (label/type/options)."""
    if name in _CHOICE_COLS:
        opts = json.dumps({"choices": list(_CHOICE_COLS[name])})
        return {"label": name, "type": "Choice", "widgetOptions": opts}
    if name in _INT_COLS:
        return {"label": name, "type": "Int"}
    if name in _BOOL_COLS:
        return {"label": name, "type": "Bool"}
    return {"label": name, "type": "Text"}


def load_grist_key() -> str:
    """Return the Grist API key from env or ~/.config/electron-rare/grist.env."""
    key = os.environ.get("GRIST_API_KEY")
    if key:
        return key
    if KEY_FILE.exists():
        for line in KEY_FILE.read_text().splitlines():
            if line.strip().startswith("GRIST_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    sys.exit("GRIST_API_KEY not found (env or ~/.config/electron-rare/grist.env)")


def load_doc_id(name: str) -> str | None:
    """Return a doc ID stored as <name>= in the grist.env file, or None."""
    env = os.environ.get(name)
    if env:
        return env
    if KEY_FILE.exists():
        for line in KEY_FILE.read_text().splitlines():
            if line.strip().startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"')
    return None


def _http_transport(method: str, url: str, key: str, body: dict | None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"Grist {method} {url} -> HTTP {exc.code}: {detail}")


class GristClient:
    """Records- and column-level access to one Grist document."""

    def __init__(self, doc_id: str, key: str, transport=_http_transport):
        self.doc_id = doc_id
        self.key = key
        self._transport = transport

    @classmethod
    def from_env(cls, doc_id: str) -> "GristClient":
        return cls(doc_id, load_grist_key())

    def _api(self, method: str, path: str, body: dict | None = None) -> dict:
        return self._transport(method, f"{GRIST_BASE}{path}", self.key, body)

    def list_tables(self) -> set[str]:
        resp = self._api("GET", f"/docs/{self.doc_id}/tables")
        return {t["id"] for t in resp.get("tables", [])}

    def create_table(self, table: str, columns: tuple[str, ...]) -> None:
        cols = [{"id": c, "fields": _col_fields(c)} for c in columns]
        self._api("POST", f"/docs/{self.doc_id}/tables",
                  {"tables": [{"id": table, "columns": cols}]})

    def ensure_table(self, table: str, columns: tuple[str, ...]) -> None:
        if table not in self.list_tables():
            self.create_table(table, columns)

    def list_columns(self, table: str) -> set[str]:
        resp = self._api(
            "GET", f"/docs/{self.doc_id}/tables/{table}/columns")
        return {c["id"] for c in resp.get("columns", [])}

    def add_columns(self, table: str, columns: tuple[str, ...]) -> None:
        if not columns:
            return
        cols = [{"id": c, "fields": _col_fields(c)} for c in columns]
        self._api("POST", f"/docs/{self.doc_id}/tables/{table}/columns",
                  {"columns": cols})

    def fetch_records(self, table: str) -> list[dict]:
        resp = self._api("GET", f"/docs/{self.doc_id}/tables/{table}/records")
        return [{"_id": r["id"], **r["fields"]} for r in resp.get("records", [])]

    def add_records(self, table: str, rows: list[dict]) -> None:
        """Insert records, chunked by row count and payload size.

        A chunk is flushed at 100 rows or when adding the next row
        would exceed _MAX_POST_BYTES, whichever comes first. This keeps
        wide rows (large text cells) under Grist's request size limit.
        """
        if not rows:
            return
        path = f"/docs/{self.doc_id}/tables/{table}/records"
        chunk: list[dict] = []
        chunk_bytes = 0
        for row in rows:
            row_bytes = len(json.dumps(row))
            if chunk and (len(chunk) >= 100
                          or chunk_bytes + row_bytes > _MAX_POST_BYTES):
                self._api("POST", path,
                          {"records": [{"fields": r} for r in chunk]})
                chunk = []
                chunk_bytes = 0
            chunk.append(row)
            chunk_bytes += row_bytes
        if chunk:
            self._api("POST", path,
                      {"records": [{"fields": r} for r in chunk]})

    def upsert_records(self, table: str, rows: list[dict],
                       key_field: str) -> None:
        """Insert or update rows, matched on key_field, in chunks of 100."""
        if not rows:
            return
        for start in range(0, len(rows), 100):
            chunk = rows[start:start + 100]
            self._api(
                "PUT",
                f"/docs/{self.doc_id}/tables/{table}/records?onmany=first",
                {"records": [{"require": {key_field: r[key_field]},
                              "fields": r} for r in chunk]})
