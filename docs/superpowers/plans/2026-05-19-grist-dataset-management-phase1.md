# Grist Dataset Management — Phase 1 (Training Mascarade) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a Grist document the canonical source of truth for the
mascarade LoRA training corpus, with insert-only ingestion, deterministic
export to hashed `.jsonl` snapshots, and HuggingFace publication.

**Architecture:** A new `mascarade_eval.grist` subpackage. Logic is split
into a thin HTTP client (`client.py`), pure data transforms
(`migrate.py`, `ingest.py`, `export.py`), an HF publisher (`publish.py`),
and an `argparse` CLI (`cli.py`). The invariant — ingestion never updates
an existing item row, so human edits in Grist survive — is isolated in
`ingest.py`. Pure functions (delta computation, message flattening,
canonical serialization, hashing) are unit-tested directly; the HTTP layer
is tested through an injected transport; one network integration test is
skipped unless `GRIST_API_KEY` is set.

**Tech Stack:** Python ≥3.12, stdlib (`urllib`, `hashlib`, `json`,
`argparse`), `huggingface_hub`, `pytest`. Run with `uv`.

**Spec:** `docs/superpowers/specs/2026-05-19-grist-dataset-management-design.md`

---

## Note on file placement

The spec names the modules under `scripts/grist/`. This plan places them
in `mascarade_eval/grist/` instead — a proper Python subpackage — so that
`pytest` can import them (`from mascarade_eval.grist.X import Y`), matching
the established pattern where `tests/` imports from the `mascarade_eval`
package. The module set and responsibilities are exactly those of the
spec. The CLI is run with `python -m mascarade_eval.grist.cli`.

## Prerequisites (manual, one-time — not a code task)

1. In the Grist UI at `grist.saillant.cc`, create a new empty document
   named **"Mascarade Training"**.
2. Copy its document ID from the URL (the segment after `/doc/`, e.g.
   `abcd1234EFGH`).
3. Add it to `~/.config/electron-rare/grist.env` as a new line:
   `GRIST_DOC_TRAINING=<the-doc-id>`
4. Confirm `GRIST_API_KEY=` is already present in that same file (it is —
   `scripts/export_grist.py` already uses it).

The CLI accepts the doc ID via `--doc` and falls back to the
`GRIST_DOC_TRAINING` env/file value, so nothing is hardcoded.

---

## Task 1: Subpackage scaffold and constants

**Files:**
- Create: `mascarade_eval/grist/__init__.py`
- Test: `tests/test_grist_constants.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grist_constants.py
from mascarade_eval import grist


def test_constants_present():
    assert grist.GRIST_BASE == "https://grist.saillant.cc/api"
    assert grist.DOC_HELDOUT == "eGbbrpzN3TeLq3sUd2YFA2"
    assert grist.TRAINING_TABLE == "Mascarade_Training"
    assert grist.REGISTRY_TABLE == "Datasets_Registry"
    assert grist.EXPORTS_TABLE == "Exports"


def test_training_columns_shape():
    assert grist.TRAINING_COLUMNS == (
        "item_key", "domain", "system", "user_msg", "assistant_msg",
        "extra_turns", "source", "exclure", "notes",
    )
    assert "exclure" in grist.TRAINING_COLUMNS


def test_exports_dir_under_repo_root():
    # EXPORTS_DIR sits next to the heldout/ dir at the repo root.
    assert grist.EXPORTS_DIR.name == "exports"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mascarade-eval && uv run python -m pytest tests/test_grist_constants.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mascarade_eval.grist'`

- [ ] **Step 3: Write minimal implementation**

```python
# mascarade_eval/grist/__init__.py
"""Grist-backed dataset management for the mascarade training corpus.

Grist is the canonical source of truth. Mining ingests in insert-only
mode (human edits in Grist are never overwritten); training and HF
publication consume a deterministic export.
"""
from pathlib import Path

GRIST_BASE = "https://grist.saillant.cc/api"

# Known existing doc (held-out eval). The training doc ID is provided at
# runtime via --doc or the GRIST_DOC_TRAINING env/file value.
DOC_HELDOUT = "eGbbrpzN3TeLq3sUd2YFA2"

KEY_FILE = Path.home() / ".config" / "electron-rare" / "grist.env"

TRAINING_TABLE = "Mascarade_Training"
REGISTRY_TABLE = "Datasets_Registry"
EXPORTS_TABLE = "Exports"

TRAINING_COLUMNS = (
    "item_key", "domain", "system", "user_msg", "assistant_msg",
    "extra_turns", "source", "exclure", "notes",
)
REGISTRY_COLUMNS = (
    "name", "family", "domain", "hf_dataset_id", "license",
    "n_items", "notes",
)
EXPORTS_COLUMNS = (
    "export_id", "domain", "created_at", "n_items", "content_hash",
    "output_file", "hf_dataset_id",
)

_ROOT = Path(__file__).resolve().parent.parent.parent  # .../mascarade-eval
EXPORTS_DIR = _ROOT / "exports"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mascarade-eval && uv run python -m pytest tests/test_grist_constants.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/__init__.py tests/test_grist_constants.py
git commit -m "feat(grist): scaffold grist subpackage and constants"
```

---

## Task 2: Grist HTTP client

**Files:**
- Create: `mascarade_eval/grist/client.py`
- Test: `tests/test_grist_client.py`

The client takes an injectable `transport` callable so tests never touch
the network. `transport(method, url, key, body) -> dict`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grist_client.py
import pytest
from mascarade_eval.grist.client import GristClient, load_grist_key


def _recording_transport(log):
    def transport(method, url, key, body):
        log.append((method, url, body))
        if method == "GET" and url.endswith("/tables"):
            return {"tables": [{"id": "Existing"}]}
        if method == "GET" and "/records" in url:
            return {"records": [
                {"id": 1, "fields": {"item_key": "k1", "exclure": False}},
                {"id": 2, "fields": {"item_key": "k2", "exclure": True}},
            ]}
        return {}
    return transport


def test_list_tables_returns_ids():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    assert c.list_tables() == {"Existing"}
    assert log[0][0] == "GET"
    assert log[0][1] == "https://grist.saillant.cc/api/docs/doc1/tables"


def test_fetch_records_flattens_id_into_fields():
    c = GristClient("doc1", "key1", transport=_recording_transport([]))
    rows = c.fetch_records("Mascarade_Training")
    assert rows == [
        {"_id": 1, "item_key": "k1", "exclure": False},
        {"_id": 2, "item_key": "k2", "exclure": True},
    ]


def test_add_records_posts_fields_wrapped():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    c.add_records("T", [{"a": "1"}, {"a": "2"}])
    method, url, body = log[-1]
    assert method == "POST"
    assert url.endswith("/docs/doc1/tables/T/records")
    assert body == {"records": [{"fields": {"a": "1"}},
                                {"fields": {"a": "2"}}]}


def test_add_records_noop_on_empty():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    c.add_records("T", [])
    assert log == []


def test_create_table_types_exclure_as_bool():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    c.create_table("T", ("item_key", "exclure", "n_items"))
    method, url, body = log[-1]
    assert method == "POST"
    cols = {col["id"]: col["fields"]["type"] for col in body["tables"][0]["columns"]}
    assert cols == {"item_key": "Text", "exclure": "Bool", "n_items": "Int"}


def test_load_grist_key_prefers_env(monkeypatch):
    monkeypatch.setenv("GRIST_API_KEY", "env-key")
    assert load_grist_key() == "env-key"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mascarade-eval && uv run python -m pytest tests/test_grist_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mascarade_eval.grist.client'`

- [ ] **Step 3: Write minimal implementation**

```python
# mascarade_eval/grist/client.py
"""Thin Grist REST client. The HTTP transport is injectable for tests."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from . import GRIST_BASE, KEY_FILE

_BOOL_COLS = {"exclure"}
_INT_COLS = {"n_items", "n_rows"}


def _col_type(name: str) -> str:
    if name in _BOOL_COLS:
        return "Bool"
    if name in _INT_COLS:
        return "Int"
    return "Text"


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
    """Records-level access to one Grist document."""

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
        cols = [{"id": c, "fields": {"label": c, "type": _col_type(c)}}
                for c in columns]
        self._api("POST", f"/docs/{self.doc_id}/tables",
                  {"tables": [{"id": table, "columns": cols}]})

    def ensure_table(self, table: str, columns: tuple[str, ...]) -> None:
        if table not in self.list_tables():
            self.create_table(table, columns)

    def fetch_records(self, table: str) -> list[dict]:
        resp = self._api("GET", f"/docs/{self.doc_id}/tables/{table}/records")
        return [{"_id": r["id"], **r["fields"]} for r in resp.get("records", [])]

    def add_records(self, table: str, rows: list[dict]) -> None:
        if not rows:
            return
        for start in range(0, len(rows), 100):
            chunk = rows[start:start + 100]
            self._api("POST", f"/docs/{self.doc_id}/tables/{table}/records",
                      {"records": [{"fields": r} for r in chunk]})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mascarade-eval && uv run python -m pytest tests/test_grist_client.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/client.py tests/test_grist_client.py
git commit -m "feat(grist): add Grist REST client"
```

---

## Task 3: Message flatten / rebuild (pure transforms)

**Files:**
- Create: `mascarade_eval/grist/migrate.py`
- Test: `tests/test_grist_migrate_transforms.py`

Training records use ShareGPT (`conversations`/`from`/`value`) or OpenAI
(`messages`/`role`/`content`) format. `flatten_messages` collapses a
single-turn record into editable columns; multi-turn records keep their
full message list in `extra_turns`. `rebuild_messages` is the inverse.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grist_migrate_transforms.py
import json
from mascarade_eval.grist.migrate import flatten_messages, rebuild_messages


def test_flatten_single_turn_openai():
    rec = {"messages": [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "Q"},
        {"role": "assistant", "content": "A"},
    ]}
    flat = flatten_messages(rec)
    assert flat == {"system": "S", "user_msg": "Q",
                    "assistant_msg": "A", "extra_turns": ""}


def test_flatten_single_turn_sharegpt():
    rec = {"conversations": [
        {"from": "human", "value": "Q"},
        {"from": "gpt", "value": "A"},
    ]}
    flat = flatten_messages(rec)
    assert flat == {"system": "", "user_msg": "Q",
                    "assistant_msg": "A", "extra_turns": ""}


def test_flatten_multi_turn_keeps_extra_turns():
    rec = {"messages": [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "Q2"},
        {"role": "assistant", "content": "A2"},
    ]}
    flat = flatten_messages(rec)
    assert flat["user_msg"] == "Q1"
    assert flat["assistant_msg"] == "A1"
    parsed = json.loads(flat["extra_turns"])
    assert parsed == [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "Q2"},
        {"role": "assistant", "content": "A2"},
    ]


def test_rebuild_single_turn_round_trip():
    rec = {"messages": [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "Q"},
        {"role": "assistant", "content": "A"},
    ]}
    flat = flatten_messages(rec)
    assert rebuild_messages(flat) == rec


def test_rebuild_single_turn_no_system():
    flat = {"system": "", "user_msg": "Q",
            "assistant_msg": "A", "extra_turns": ""}
    assert rebuild_messages(flat) == {"messages": [
        {"role": "user", "content": "Q"},
        {"role": "assistant", "content": "A"},
    ]}


def test_rebuild_multi_turn_uses_extra_turns():
    rec = {"messages": [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "Q2"},
        {"role": "assistant", "content": "A2"},
    ]}
    flat = flatten_messages(rec)
    assert rebuild_messages(flat) == rec
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mascarade-eval && uv run python -m pytest tests/test_grist_migrate_transforms.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mascarade_eval.grist.migrate'`

- [ ] **Step 3: Write minimal implementation**

```python
# mascarade_eval/grist/migrate.py
"""Backfill the training corpus from HuggingFace into Grist.

Pure transforms (flatten_messages / rebuild_messages) are unit-tested;
migrate_domain wires them to HF download + insert-only ingestion.
"""
from __future__ import annotations

import json

_ROLE_NORMAL = {"user": "user", "human": "user",
                "assistant": "assistant", "gpt": "assistant",
                "system": "system"}


def _normalize(record: dict) -> list[dict]:
    """Return [{role, content}, ...] from an OpenAI or ShareGPT record."""
    raw = record.get("messages") or record.get("conversations") or []
    out: list[dict] = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        role = _ROLE_NORMAL.get(m.get("role") or m.get("from") or "")
        if role is None:
            continue
        content = m.get("content") or m.get("value") or ""
        out.append({"role": role, "content": content})
    return out


def flatten_messages(record: dict) -> dict:
    """Collapse a chat record into editable columns.

    Single-turn (<=1 system, exactly 1 user, exactly 1 assistant) maps to
    system/user_msg/assistant_msg with empty extra_turns. Anything else
    keeps the full normalized message list as JSON in extra_turns.
    """
    msgs = _normalize(record)
    systems = [m for m in msgs if m["role"] == "system"]
    users = [m for m in msgs if m["role"] == "user"]
    assistants = [m for m in msgs if m["role"] == "assistant"]
    single_turn = (len(systems) <= 1 and len(users) == 1
                   and len(assistants) == 1 and len(msgs) == len(systems) + 2)
    flat = {
        "system": systems[0]["content"] if systems else "",
        "user_msg": users[0]["content"] if users else "",
        "assistant_msg": assistants[0]["content"] if assistants else "",
        "extra_turns": "",
    }
    if not single_turn:
        flat["extra_turns"] = json.dumps(msgs, ensure_ascii=False)
    return flat


def rebuild_messages(row: dict) -> dict:
    """Inverse of flatten_messages: return {"messages": [...]}."""
    extra = row.get("extra_turns") or ""
    if extra:
        return {"messages": json.loads(extra)}
    msgs: list[dict] = []
    if row.get("system"):
        msgs.append({"role": "system", "content": row["system"]})
    msgs.append({"role": "user", "content": row.get("user_msg", "")})
    msgs.append({"role": "assistant", "content": row.get("assistant_msg", "")})
    return {"messages": msgs}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mascarade-eval && uv run python -m pytest tests/test_grist_migrate_transforms.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/migrate.py tests/test_grist_migrate_transforms.py
git commit -m "feat(grist): add message flatten and rebuild transforms"
```

---

## Task 4: Insert-only ingestion core + shared test fixture

**Files:**
- Create: `mascarade_eval/grist/ingest.py`
- Create: `tests/conftest.py`
- Test: `tests/test_grist_ingest.py`

`compute_delta` is the source-of-truth invariant: only rows whose key is
absent from Grist are returned, and duplicates within a batch are dropped.
`conftest.py` defines a `FakeClient` reused by Tasks 4–6.

- [ ] **Step 1: Write the failing test**

```python
# tests/conftest.py
import pytest


class FakeClient:
    """In-memory stand-in for GristClient. Records all writes."""

    def __init__(self, tables=None, records=None):
        self.doc_id = "fake-doc"
        self._tables = set(tables or [])
        self._records = {t: list(rs) for t, rs in (records or {}).items()}
        self.created = []
        self.added = {}

    def list_tables(self):
        return set(self._tables)

    def create_table(self, table, columns):
        self._tables.add(table)
        self.created.append((table, tuple(columns)))

    def ensure_table(self, table, columns):
        if table not in self._tables:
            self.create_table(table, columns)

    def fetch_records(self, table):
        return [dict(r) for r in self._records.get(table, [])]

    def add_records(self, table, rows):
        self.added.setdefault(table, []).extend(rows)
        self._records.setdefault(table, []).extend(rows)


@pytest.fixture
def fake_client():
    return FakeClient
```

```python
# tests/test_grist_ingest.py
from mascarade_eval.grist import TRAINING_TABLE, TRAINING_COLUMNS
from mascarade_eval.grist.ingest import item_key, compute_delta, ingest_rows


def test_item_key_is_deterministic_and_domain_prefixed():
    k1 = item_key("kicad", "How do I add a net class?")
    k2 = item_key("kicad", "How do I add a net class?")
    assert k1 == k2
    assert k1.startswith("kicad-")


def test_item_key_differs_by_text():
    assert item_key("kicad", "A") != item_key("kicad", "B")


def test_compute_delta_skips_existing_keys():
    existing = {"kicad-aaaaaaaaaa"}
    incoming = [
        {"item_key": "kicad-aaaaaaaaaa", "user_msg": "old"},
        {"item_key": "kicad-bbbbbbbbbb", "user_msg": "new"},
    ]
    delta = compute_delta(existing, incoming)
    assert [r["item_key"] for r in delta] == ["kicad-bbbbbbbbbb"]


def test_compute_delta_dedupes_within_batch():
    incoming = [
        {"item_key": "k1", "user_msg": "x"},
        {"item_key": "k1", "user_msg": "x-dup"},
    ]
    delta = compute_delta(set(), incoming)
    assert len(delta) == 1
    assert delta[0]["user_msg"] == "x"


def test_ingest_rows_inserts_only_new(fake_client):
    client = fake_client(
        tables=[TRAINING_TABLE],
        records={TRAINING_TABLE: [{"item_key": "k1", "user_msg": "kept"}]},
    )
    rows = [
        {"item_key": "k1", "user_msg": "WOULD OVERWRITE"},
        {"item_key": "k2", "user_msg": "fresh"},
    ]
    report = ingest_rows(client, TRAINING_TABLE, TRAINING_COLUMNS, rows)
    assert report == {"inserted": 1, "skipped": 1}
    assert client.added[TRAINING_TABLE] == [{"item_key": "k2",
                                             "user_msg": "fresh"}]


def test_ingest_rows_creates_table_when_absent(fake_client):
    client = fake_client(tables=[])
    ingest_rows(client, TRAINING_TABLE, TRAINING_COLUMNS,
                [{"item_key": "k1"}])
    assert client.created == [(TRAINING_TABLE, TRAINING_COLUMNS)]


def test_ingest_rows_dry_run_writes_nothing(fake_client):
    client = fake_client(tables=[TRAINING_TABLE])
    report = ingest_rows(client, TRAINING_TABLE, TRAINING_COLUMNS,
                         [{"item_key": "k1"}], dry_run=True)
    assert report == {"inserted": 1, "skipped": 0}
    assert client.added == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mascarade-eval && uv run python -m pytest tests/test_grist_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mascarade_eval.grist.ingest'`

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mascarade-eval && uv run python -m pytest tests/test_grist_ingest.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/ingest.py tests/conftest.py tests/test_grist_ingest.py
git commit -m "feat(grist): add insert-only ingestion core"
```

---

## Task 5: Deterministic export + Exports journal

**Files:**
- Create: `mascarade_eval/grist/export.py`
- Test: `tests/test_grist_export.py`

`canonical_jsonl` takes `(sort_key, object)` pairs, orders them by key,
and serializes each object with sorted keys — so the same Grist state
always yields the same bytes and the same SHA256. The published snapshot
carries only the chat objects (no `item_key`); the key is used purely to
make ordering deterministic.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grist_export.py
import json
from mascarade_eval.grist import TRAINING_TABLE, EXPORTS_TABLE
from mascarade_eval.grist.export import (
    canonical_jsonl, content_hash, export_domain,
)


def test_canonical_jsonl_sorts_by_key():
    keyed = [("b", {"v": 2}), ("a", {"v": 1})]
    lines = canonical_jsonl(keyed).splitlines()
    assert json.loads(lines[0]) == {"v": 1}
    assert json.loads(lines[1]) == {"v": 2}


def test_canonical_jsonl_is_order_independent():
    a = [("x", {"v": 1}), ("y", {"v": 2})]
    b = [("y", {"v": 2}), ("x", {"v": 1})]
    assert canonical_jsonl(a) == canonical_jsonl(b)


def test_canonical_jsonl_omits_the_sort_key_from_output():
    text = canonical_jsonl([("x", {"v": 1})])
    assert json.loads(text) == {"v": 1}  # no "x", no item_key


def test_content_hash_stable():
    text = canonical_jsonl([("x", {"v": 1})])
    assert content_hash(text) == content_hash(text)
    assert len(content_hash(text)) == 64


def test_export_domain_filters_excluded_and_writes_file(fake_client, tmp_path):
    client = fake_client(
        tables=[TRAINING_TABLE],
        records={TRAINING_TABLE: [
            {"_id": 1, "item_key": "kicad-1", "domain": "kicad",
             "user_msg": "Q1", "assistant_msg": "A1", "system": "",
             "extra_turns": "", "source": "", "exclure": False, "notes": ""},
            {"_id": 2, "item_key": "kicad-2", "domain": "kicad",
             "user_msg": "Q2", "assistant_msg": "A2", "system": "",
             "extra_turns": "", "source": "", "exclure": True, "notes": ""},
        ]},
    )
    report = export_domain(client, "kicad", out_dir=tmp_path)
    assert report["n_items"] == 1  # the excluded row is dropped
    out_file = tmp_path / report["output_file"]
    assert out_file.exists()
    written = [json.loads(ln) for ln in out_file.read_text().splitlines()]
    assert written == [{"messages": [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1"},
    ]}]
    assert client.added[EXPORTS_TABLE][0]["domain"] == "kicad"
    assert client.added[EXPORTS_TABLE][0]["content_hash"] == report["content_hash"]


def test_export_domain_dry_run_writes_nothing(fake_client, tmp_path):
    client = fake_client(
        tables=[TRAINING_TABLE],
        records={TRAINING_TABLE: [
            {"_id": 1, "item_key": "kicad-1", "domain": "kicad",
             "user_msg": "Q", "assistant_msg": "A", "system": "",
             "extra_turns": "", "exclure": False}]},
    )
    report = export_domain(client, "kicad", out_dir=tmp_path, dry_run=True)
    assert report["n_items"] == 1
    assert list(tmp_path.iterdir()) == []
    assert client.added == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mascarade-eval && uv run python -m pytest tests/test_grist_export.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mascarade_eval.grist.export'`

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mascarade-eval && uv run python -m pytest tests/test_grist_export.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/export.py tests/test_grist_export.py
git commit -m "feat(grist): add deterministic export and Exports log"
```

---

## Task 6: Migrate domain — HF download wired to ingestion

**Files:**
- Modify: `mascarade_eval/grist/migrate.py` (append `migrate_domain`)
- Test: `tests/test_grist_migrate_domain.py`

`migrate_domain` accepts an optional `records` argument so tests bypass
the HF download. When omitted, it downloads `<domain>_chat.jsonl` from
`Ailiance-fr/mascarade-<domain>-dataset`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grist_migrate_domain.py
from mascarade_eval.grist import TRAINING_TABLE, REGISTRY_TABLE
from mascarade_eval.grist.migrate import migrate_domain


def test_migrate_domain_ingests_flattened_rows(fake_client):
    client = fake_client(tables=[])
    records = [
        {"messages": [{"role": "user", "content": "Q1"},
                      {"role": "assistant", "content": "A1"}]},
        {"messages": [{"role": "user", "content": "Q2"},
                      {"role": "assistant", "content": "A2"}]},
    ]
    report = migrate_domain(client, "kicad", records=records)
    assert report["inserted"] == 2
    added = client.added[TRAINING_TABLE]
    assert {r["user_msg"] for r in added} == {"Q1", "Q2"}
    assert all(r["domain"] == "kicad" for r in added)
    assert all(r["item_key"].startswith("kicad-") for r in added)
    assert all(r["exclure"] is False for r in added)


def test_migrate_domain_is_idempotent(fake_client):
    client = fake_client(tables=[])
    records = [{"messages": [{"role": "user", "content": "Q"},
                             {"role": "assistant", "content": "A"}]}]
    migrate_domain(client, "kicad", records=records)
    report2 = migrate_domain(client, "kicad", records=records)
    assert report2 == {"inserted": 0, "skipped": 1}


def test_migrate_domain_writes_registry_row(fake_client):
    client = fake_client(tables=[])
    records = [{"messages": [{"role": "user", "content": "Q"},
                             {"role": "assistant", "content": "A"}]}]
    migrate_domain(client, "kicad", records=records)
    reg = client.added[REGISTRY_TABLE]
    assert reg[0]["name"] == "mascarade-kicad-train"
    assert reg[0]["family"] == "mascarade-training"
    assert reg[0]["hf_dataset_id"] == "Ailiance-fr/mascarade-kicad-dataset"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mascarade-eval && uv run python -m pytest tests/test_grist_migrate_domain.py -v`
Expected: FAIL with `ImportError: cannot import name 'migrate_domain'`

- [ ] **Step 3: Write minimal implementation**

3a. In `mascarade_eval/grist/migrate.py`, add these three import lines
immediately after the existing `import json` line:

```python
from mascarade_eval import HF_ORG
from . import REGISTRY_COLUMNS, REGISTRY_TABLE, TRAINING_COLUMNS, TRAINING_TABLE
from .ingest import ingest_rows, item_key
```

3b. Append these functions to the end of `mascarade_eval/grist/migrate.py`:

```python
def _download_training_records(domain: str) -> list[dict]:
    """Download <domain>_chat.jsonl from HF and parse it into records."""
    from huggingface_hub import hf_hub_download
    path = hf_hub_download(
        repo_id=f"{HF_ORG}/mascarade-{domain}-dataset",
        filename=f"{domain}_chat.jsonl",
        repo_type="dataset",
    )
    records: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _to_training_row(domain: str, record: dict) -> dict:
    flat = flatten_messages(record)
    return {
        "item_key": item_key(domain, flat["user_msg"]),
        "domain": domain,
        "system": flat["system"],
        "user_msg": flat["user_msg"],
        "assistant_msg": flat["assistant_msg"],
        "extra_turns": flat["extra_turns"],
        "source": f"{HF_ORG}/mascarade-{domain}-dataset",
        "exclure": False,
        "notes": "",
    }


def migrate_domain(client, domain: str, records: list[dict] | None = None,
                   dry_run: bool = False) -> dict:
    """Backfill one domain's HF training data into Grist (insert-only).

    Pass `records` to skip the HF download (used by tests).
    """
    if records is None:
        records = _download_training_records(domain)
    rows = [_to_training_row(domain, r) for r in records]
    report = ingest_rows(client, TRAINING_TABLE, TRAINING_COLUMNS, rows,
                         dry_run=dry_run)
    if not dry_run:
        client.ensure_table(REGISTRY_TABLE, REGISTRY_COLUMNS)
        client.add_records(REGISTRY_TABLE, [{
            "name": f"mascarade-{domain}-train",
            "family": "mascarade-training",
            "domain": domain,
            "hf_dataset_id": f"{HF_ORG}/mascarade-{domain}-dataset",
            "license": "CC-BY-SA-4.0",
            "n_items": len(rows),
            "notes": f"backfilled {report['inserted']} new, "
                     f"{report['skipped']} already present",
        }])
    return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mascarade-eval && uv run python -m pytest tests/test_grist_migrate_domain.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full grist suite to catch regressions**

Run: `cd mascarade-eval && uv run python -m pytest tests/test_grist_*.py -v`
Expected: PASS (all grist tests green)

- [ ] **Step 6: Commit**

```bash
git add mascarade_eval/grist/migrate.py tests/test_grist_migrate_domain.py
git commit -m "feat(grist): wire HF backfill into ingestion"
```

---

## Task 7: Publish a snapshot to HuggingFace

**Files:**
- Create: `mascarade_eval/grist/publish.py`
- Test: `tests/test_grist_publish.py`

`publish_snapshot` uploads one exported `.jsonl` file to its HF dataset
repo. The `huggingface_hub` API is injected so the test never uploads.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grist_publish.py
import pytest
from mascarade_eval.grist.publish import publish_snapshot


def test_publish_snapshot_uploads_with_expected_args(tmp_path):
    snap = tmp_path / "kicad.20260519T120000Z.jsonl"
    snap.write_text('{"messages": []}\n')
    calls = []

    def fake_upload(*, path_or_fileobj, path_in_repo, repo_id, repo_type,
                    commit_message):
        calls.append({
            "path_or_fileobj": path_or_fileobj,
            "path_in_repo": path_in_repo,
            "repo_id": repo_id,
            "repo_type": repo_type,
            "commit_message": commit_message,
        })

    publish_snapshot(str(snap), "Ailiance-fr/mascarade-kicad-dataset",
                     "kicad_chat.jsonl", uploader=fake_upload)
    assert len(calls) == 1
    assert calls[0]["repo_id"] == "Ailiance-fr/mascarade-kicad-dataset"
    assert calls[0]["repo_type"] == "dataset"
    assert calls[0]["path_in_repo"] == "kicad_chat.jsonl"
    assert calls[0]["path_or_fileobj"] == str(snap)


def test_publish_snapshot_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        publish_snapshot(str(tmp_path / "nope.jsonl"),
                         "Ailiance-fr/mascarade-kicad-dataset",
                         "kicad_chat.jsonl", uploader=lambda **k: None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mascarade-eval && uv run python -m pytest tests/test_grist_publish.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mascarade_eval.grist.publish'`

- [ ] **Step 3: Write minimal implementation**

```python
# mascarade_eval/grist/publish.py
"""Publish an exported snapshot to its HuggingFace dataset repo."""
from __future__ import annotations

from pathlib import Path


def _hf_upload(*, path_or_fileobj, path_in_repo, repo_id, repo_type,
               commit_message):
    from huggingface_hub import upload_file
    upload_file(path_or_fileobj=path_or_fileobj, path_in_repo=path_in_repo,
                repo_id=repo_id, repo_type=repo_type,
                commit_message=commit_message)


def publish_snapshot(snapshot_path: str, hf_dataset_id: str,
                     filename: str, uploader=_hf_upload) -> None:
    """Upload one exported .jsonl snapshot to its HF dataset repo.

    `uploader` is injected for testing; production uses huggingface_hub.
    """
    path = Path(snapshot_path)
    if not path.exists():
        raise FileNotFoundError(f"snapshot not found: {snapshot_path}")
    uploader(
        path_or_fileobj=str(path),
        path_in_repo=filename,
        repo_id=hf_dataset_id,
        repo_type="dataset",
        commit_message=f"dataset: refresh {filename} from Grist export",
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mascarade-eval && uv run python -m pytest tests/test_grist_publish.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/publish.py tests/test_grist_publish.py
git commit -m "feat(grist): add HuggingFace snapshot publisher"
```

---

## Task 8: CLI with four subcommands

**Files:**
- Create: `mascarade_eval/grist/cli.py`
- Test: `tests/test_grist_cli.py`

`build_parser()` is unit-tested for argument wiring; `main()` dispatches.
Run in production as `python -m mascarade_eval.grist.cli <subcommand>`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grist_cli.py
import pytest
from mascarade_eval.grist.cli import build_parser, resolve_doc


def test_parser_ingest_requires_doc_and_jsonl():
    ns = build_parser().parse_args(
        ["ingest", "--doc", "D", "--jsonl", "mine.jsonl", "--domain", "kicad"])
    assert ns.command == "ingest"
    assert ns.doc == "D"
    assert ns.jsonl == "mine.jsonl"
    assert ns.domain == "kicad"


def test_parser_export_accepts_dry_run():
    ns = build_parser().parse_args(
        ["export", "--doc", "D", "--domain", "kicad", "--dry-run"])
    assert ns.command == "export"
    assert ns.dry_run is True


def test_parser_migrate_and_publish():
    p = build_parser()
    m = p.parse_args(["migrate", "--doc", "D", "--domain", "kicad"])
    assert m.command == "migrate"
    pub = p.parse_args(
        ["publish", "--snapshot", "exports/kicad.x.jsonl",
         "--hf-dataset", "Ailiance-fr/mascarade-kicad-dataset",
         "--filename", "kicad_chat.jsonl"])
    assert pub.command == "publish"
    assert pub.hf_dataset == "Ailiance-fr/mascarade-kicad-dataset"


def test_resolve_doc_prefers_explicit_arg():
    assert resolve_doc("explicit-id") == "explicit-id"


def test_resolve_doc_errors_when_unset(monkeypatch):
    monkeypatch.delenv("GRIST_DOC_TRAINING", raising=False)
    monkeypatch.setattr("mascarade_eval.grist.cli.load_doc_id",
                        lambda name: None)
    with pytest.raises(SystemExit):
        resolve_doc(None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mascarade-eval && uv run python -m pytest tests/test_grist_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mascarade_eval.grist.cli'`

- [ ] **Step 3: Write minimal implementation**

```python
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

    p_mig = sub.add_parser("migrate", help="backfill a domain from HF")
    p_mig.add_argument("--doc")
    p_mig.add_argument("--domain", required=True)
    p_mig.add_argument("--dry-run", action="store_true")

    p_pub = sub.add_parser("publish", help="upload a snapshot to HF")
    p_pub.add_argument("--snapshot", required=True)
    p_pub.add_argument("--hf-dataset", required=True)
    p_pub.add_argument("--filename", required=True)

    return ap


def resolve_doc(doc_arg: str | None) -> str:
    """Return the doc ID from --doc or the GRIST_DOC_TRAINING env/file value."""
    if doc_arg:
        return doc_arg
    doc = load_doc_id("GRIST_DOC_TRAINING")
    if not doc:
        sys.exit("no doc ID: pass --doc or set GRIST_DOC_TRAINING")
    return doc


def _ingest_jsonl_rows(domain: str, jsonl_path: str) -> list[dict]:
    rows: list[dict] = []
    for line in Path(jsonl_path).read_text(encoding="utf-8").splitlines():
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
            "exclure": False,
            "notes": "",
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "publish":
        publish_snapshot(args.snapshot, args.hf_dataset, args.filename)
        print(f"published {args.snapshot} -> {args.hf_dataset}")
        return 0

    client = GristClient.from_env(resolve_doc(args.doc))

    if args.command == "ingest":
        rows = _ingest_jsonl_rows(args.domain, args.jsonl)
        report = ingest_rows(client, TRAINING_TABLE, TRAINING_COLUMNS, rows,
                             dry_run=args.dry_run)
        print(f"ingest {args.domain}: {report}")
    elif args.command == "export":
        report = export_domain(client, args.domain, EXPORTS_DIR,
                               dry_run=args.dry_run)
        print(f"export {args.domain}: {report}")
    elif args.command == "migrate":
        report = migrate_domain(client, args.domain, dry_run=args.dry_run)
        print(f"migrate {args.domain}: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mascarade-eval && uv run python -m pytest tests/test_grist_cli.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/cli.py tests/test_grist_cli.py
git commit -m "feat(grist): add ingest/export/migrate/publish CLI"
```

---

## Task 9: Round-trip integration test and operator docs

**Files:**
- Create: `tests/test_grist_roundtrip.py`
- Create: `mascarade_eval/grist/README.md`

The round-trip test uses the in-memory `FakeClient` (no network): migrate
a sample → export → assert the exported chat objects equal the source.
This is the migration acceptance check from the spec.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grist_roundtrip.py
import json
from mascarade_eval.grist.migrate import migrate_domain
from mascarade_eval.grist.export import export_domain


def test_migrate_then_export_round_trips(fake_client, tmp_path):
    source = [
        {"messages": [{"role": "user", "content": "Q1"},
                      {"role": "assistant", "content": "A1"}]},
        {"messages": [{"role": "system", "content": "S"},
                      {"role": "user", "content": "Q2"},
                      {"role": "assistant", "content": "A2"}]},
    ]
    client = fake_client(tables=[])
    migrate_domain(client, "kicad", records=source)
    report = export_domain(client, "kicad", out_dir=tmp_path)

    assert report["n_items"] == 2
    out_file = tmp_path / report["output_file"]
    exported = [json.loads(ln) for ln in out_file.read_text().splitlines()]

    def norm(msgs):
        return sorted(json.dumps(m, sort_keys=True) for m in msgs)

    source_sets = {tuple(norm(r["messages"])) for r in source}
    export_sets = {tuple(norm(r["messages"])) for r in exported}
    assert source_sets == export_sets


def test_double_ingest_inserts_zero_the_second_time(fake_client):
    source = [{"messages": [{"role": "user", "content": "Q"},
                            {"role": "assistant", "content": "A"}]}]
    client = fake_client(tables=[])
    migrate_domain(client, "kicad", records=source)
    second = migrate_domain(client, "kicad", records=source)
    assert second["inserted"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mascarade-eval && uv run python -m pytest tests/test_grist_roundtrip.py -v`
Expected: FAIL — file does not exist yet; after creating it, it should
PASS (both functions already exist from Tasks 5–6). If it fails on an
assertion, the bug is real: fix the implementation, not the test.

- [ ] **Step 3: Verify it passes**

Run: `cd mascarade-eval && uv run python -m pytest tests/test_grist_roundtrip.py -v`
Expected: PASS (2 tests)

- [ ] **Step 4: Write the operator README**

```markdown
# mascarade_eval.grist — Grist-backed dataset management

Grist is the canonical source of truth for the mascarade training corpus.
Mining ingests in insert-only mode (edits made in Grist are never
overwritten); training and HF publication consume a deterministic export.

## One-time setup

1. Create an empty Grist doc "Mascarade Training" at grist.saillant.cc.
2. Add `GRIST_DOC_TRAINING=<doc-id>` to `~/.config/electron-rare/grist.env`
   (the file already holds `GRIST_API_KEY`).

## Commands

Run with `uv run python -m mascarade_eval.grist.cli <subcommand>`.

- `migrate --domain kicad` — backfill a domain's HF training data into
  Grist (insert-only). Run once per domain to seed the doc.
- `ingest --domain kicad --jsonl mine.jsonl` — insert-only ingest of a
  new mining/curation file. Existing rows are never touched.
- `export --domain kicad` — write a hashed `.jsonl` snapshot to
  `exports/` and log a row in the `Exports` table.
- `publish --snapshot exports/kicad.<ts>.jsonl --hf-dataset
  Ailiance-fr/mascarade-kicad-dataset --filename kicad_chat.jsonl` —
  upload a snapshot to its HF dataset repo.

Add `--dry-run` to `ingest`, `export`, or `migrate` to preview without
writing to Grist or disk.

## Human review

Edit rows directly in the Grist UI. To drop an item from future exports,
tick its `exclure` checkbox — `export` filters those rows out.
```

Save the block above as `mascarade_eval/grist/README.md`.

- [ ] **Step 5: Run the entire test suite**

Run: `cd mascarade-eval && uv run python -m pytest -v`
Expected: PASS — all grist tests plus the pre-existing harness tests
(`test_train_corpus.py`, `test_runner.py`, etc.) green.

- [ ] **Step 6: Commit**

```bash
git add tests/test_grist_roundtrip.py mascarade_eval/grist/README.md
git commit -m "test(grist): add round-trip check and operator docs"
```

---

## Manual validation (after all tasks, requires network)

These steps need `GRIST_API_KEY` + `GRIST_DOC_TRAINING` configured and are
run by hand once, not part of the automated suite:

1. `uv run python -m mascarade_eval.grist.cli migrate --domain kicad --dry-run`
   — confirm the planned insert count looks right.
2. `uv run python -m mascarade_eval.grist.cli migrate --domain kicad`
   — backfill kicad; open Grist and confirm `Mascarade_Training` is
   populated and `Datasets_Registry` has one row.
3. In Grist, edit one `user_msg` and tick one `exclure` box.
4. Re-run `migrate --domain kicad` — confirm `inserted: 0` and that the
   edited row keeps its edit (insert-only invariant).
5. `uv run python -m mascarade_eval.grist.cli export --domain kicad`
   — confirm a file lands in `exports/`, the excluded row is absent, and
   an `Exports` row appears with a matching `content_hash`.
6. Repeat for the remaining 9 domains once kicad is verified.

---

## Self-Review

**Spec coverage:**
- Grist as source of truth, insert-only ingestion — Task 4 (`compute_delta`,
  `ingest_rows`), verified by `test_ingest_rows_inserts_only_new` and the
  double-ingest test in Task 9.
- `Mascarade_Training` / `Datasets_Registry` / `Exports` tables and schema
  — Task 1 constants, created via `ensure_table` in Tasks 4–6.
- Flattened training format with `extra_turns` fallback — Task 3.
- Deterministic hashed export + `Exports` journal — Task 5.
- HF publication — Task 7.
- `grist_client` / `ingest` / `export` / `publish` / `migrate` / CLI module
  set — Tasks 2, 4, 5, 7, 6, 8. (`dataset_cli` from the spec is `cli.py`.)
- Round-trip migration acceptance test — Task 9.
- Error handling: malformed JSONL skipped (`_ingest_jsonl_rows`, Task 8);
  Grist failure raises (`_http_transport`, Task 2); multi-turn fallback
  (Task 3).
- Phases 2 (heldout) and 3 (iact-bench) are deliberately out of scope for
  this plan — they are separate plans per the spec's phasing.

**Placeholder scan:** No `TBD`/`TODO`/`implement later` markers remain.
Every code step shows complete code; the only manual non-code step is the
documented Grist-doc creation in Prerequisites.

**Type consistency:** `GristClient` methods (`list_tables`, `ensure_table`,
`fetch_records`, `add_records`, `create_table`) are used identically by
`FakeClient` and by `ingest_rows`/`export_domain`/`migrate_domain`.
`flatten_messages` returns `{system, user_msg, assistant_msg, extra_turns}`
— consumed with those exact keys in `migrate._to_training_row` and
`cli._ingest_jsonl_rows`. `export_domain`/`ingest_rows`/`migrate_domain`
all return report dicts and all accept `dry_run`.
