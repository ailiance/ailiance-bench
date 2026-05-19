# Grist Human-Review Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a human verification layer on top of the Grist dataset
pipeline — review columns, an idempotent schema migration, a custom
review widget, native bench views, and an export gate so only
human-validated rows reach HuggingFace.

**Architecture:** Extends the Phase 1 `mascarade_eval.grist` package
with column-DDL on the client, a `schema.py` migration and a
`review_status` export gate; adds a static Grist custom widget
(`widgets/review-console/`); documents the native Grist UI config in
two recipe files. The boolean `exclure` column planned in Phase 1 is
replaced everywhere by a `review_status` enum.

**Tech Stack:** Python 3.12+ (uv, pytest), Grist REST API, vanilla
JS + Grist Plugin API for the widget.

---

## Execution context

- **Worktree / branch:** Implement on the existing worktree
  `/Users/electron/ailiance-bench/.claude/worktrees/grist-dataset-mgmt`
  (branch `worktree-grist-dataset-mgmt`). This branch carries the
  unmerged Phase 1 grist package; the review layer extends it. Phase 1
  and this work merge to `main` together.
- **Working directory for all commands:** the `mascarade-eval/`
  subdirectory of that worktree (it holds `pyproject.toml`). All file
  paths below are relative to `mascarade-eval/`.
- **Test command:** `uv run python -m pytest <path> -q`
- **Baseline:** 87 tests currently collected and green.

## File structure

| File | Responsibility | Tasks |
|---|---|---|
| `mascarade_eval/grist/__init__.py` | constants: docs, review columns, targets | 1 |
| `mascarade_eval/grist/client.py` | Grist REST client + column DDL | 3 |
| `mascarade_eval/grist/schema.py` (new) | idempotent review-column migration | 4 |
| `mascarade_eval/grist/migrate.py` | producer: HF backfill rows | 2 |
| `mascarade_eval/grist/cli.py` | CLI: ingest/export/migrate/publish/schema | 2,5,6 |
| `mascarade_eval/grist/export.py` | deterministic export + review gate | 6 |
| `tests/conftest.py` | `FakeClient` test double | 4 |
| `tests/test_grist_*.py` | unit tests | 1-6 |
| `widgets/review-console/index.html` (new) | Grist custom review widget | 8 |
| `docs/grist-native-views-recipe.md` (new) | bench views + form + choice colors | 7 |
| `docs/grist-widget-setup.md` (new) | widget hosting + page wiring + smoke test | 9 |

---

## Task 1: Review constants and `TRAINING_COLUMNS` amendment

**Files:**
- Modify: `mascarade_eval/grist/__init__.py`
- Test: `tests/test_grist_constants.py`

- [ ] **Step 1: Rewrite the constants test**

Replace the entire contents of `tests/test_grist_constants.py` with:

```python
# tests/test_grist_constants.py
from mascarade_eval import grist


def test_constants_present():
    assert grist.GRIST_BASE == "https://grist.saillant.cc/api"
    assert grist.DOC_HELDOUT == "eGbbrpzN3TeLq3sUd2YFA2"
    assert grist.DOC_MASCARADE == "dhyrySCayizD1PNqCNhCPN"
    assert grist.TRAINING_TABLE == "Mascarade_Training"
    assert grist.REGISTRY_TABLE == "Datasets_Registry"
    assert grist.EXPORTS_TABLE == "Exports"


def test_review_constants():
    assert grist.REVIEW_COLUMNS == (
        "review_status", "reviewer", "reviewed_at", "review_note")
    assert grist.REVIEW_STATUSES == (
        "pending", "validated", "rejected", "needs_fix")
    assert grist.REVIEWER_CHOICES == ("clems",)


def test_review_targets_cover_both_docs():
    assert grist.REVIEW_TARGETS == {
        grist.DOC_HELDOUT: ("Heldout_Items", "Datasets"),
        grist.DOC_MASCARADE: ("Mascarade_Eval_Items", "Bench_31_domains"),
    }


def test_training_columns_end_with_review_columns():
    assert grist.TRAINING_COLUMNS == (
        "item_key", "domain", "system", "user_msg", "assistant_msg",
        "extra_turns", "source", "notes",
        "review_status", "reviewer", "reviewed_at", "review_note",
    )
    assert "exclure" not in grist.TRAINING_COLUMNS
    assert grist.TRAINING_COLUMNS[-4:] == grist.REVIEW_COLUMNS


def test_exports_dir_under_repo_root():
    assert grist.EXPORTS_DIR.name == "exports"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_grist_constants.py -q`
Expected: FAIL — `AttributeError: module 'mascarade_eval.grist' has no attribute 'DOC_MASCARADE'`.

- [ ] **Step 3: Rewrite `__init__.py`**

Replace the entire contents of `mascarade_eval/grist/__init__.py` with:

```python
# mascarade_eval/grist/__init__.py
"""Grist-backed dataset management for the mascarade training corpus.

Grist is the canonical source of truth. Mining ingests in insert-only
mode (human edits in Grist are never overwritten); training and HF
publication consume a deterministic export of human-validated rows.
"""
from pathlib import Path

GRIST_BASE = "https://grist.saillant.cc/api"

# Known existing docs. The training doc ID is provided at runtime via
# --doc or the GRIST_DOC_TRAINING env/file value.
DOC_HELDOUT = "eGbbrpzN3TeLq3sUd2YFA2"      # ailiance-llm-workflow
DOC_MASCARADE = "dhyrySCayizD1PNqCNhCPN"    # mascarade-data

KEY_FILE = Path.home() / ".config" / "electron-rare" / "grist.env"

TRAINING_TABLE = "Mascarade_Training"
REGISTRY_TABLE = "Datasets_Registry"
EXPORTS_TABLE = "Exports"

# Human-review columns appended to every validation-target table.
REVIEW_COLUMNS = ("review_status", "reviewer", "reviewed_at", "review_note")
REVIEW_STATUSES = ("pending", "validated", "rejected", "needs_fix")
REVIEWER_CHOICES = ("clems",)

# Existing tables that receive the review columns, keyed by doc ID.
REVIEW_TARGETS = {
    DOC_HELDOUT: ("Heldout_Items", "Datasets"),
    DOC_MASCARADE: ("Mascarade_Eval_Items", "Bench_31_domains"),
}

TRAINING_COLUMNS = (
    "item_key", "domain", "system", "user_msg", "assistant_msg",
    "extra_turns", "source", "notes",
) + REVIEW_COLUMNS
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

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run python -m pytest tests/test_grist_constants.py -q`
Expected: PASS — 5 passed.

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/__init__.py tests/test_grist_constants.py
git commit -m "feat(grist): add review-status constants"
```

---

## Task 2: Producers write `review_status` instead of `exclure`

**Files:**
- Modify: `mascarade_eval/grist/migrate.py:89-101` (`_to_training_row`)
- Modify: `mascarade_eval/grist/cli.py:79-91` (`_ingest_jsonl_rows`)
- Test: `tests/test_grist_migrate_domain.py:20`

- [ ] **Step 1: Update the migrate-domain test assertion**

In `tests/test_grist_migrate_domain.py`, replace line 20:

```python
    assert all(r["exclure"] is False for r in added)
```

with:

```python
    assert all(r["review_status"] == "pending" for r in added)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_grist_migrate_domain.py -q`
Expected: FAIL — `KeyError: 'review_status'` in `test_migrate_domain_ingests_flattened_rows`.

- [ ] **Step 3: Update `_to_training_row` in `migrate.py`**

Replace the `_to_training_row` function (lines 89-101) with:

```python
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
        "notes": "",
        "review_status": "pending",
    }
```

- [ ] **Step 4: Update `_ingest_jsonl_rows` in `cli.py`**

In `cli.py`, in the row dict appended inside `_ingest_jsonl_rows`
(lines 80-90), replace `"exclure": False,` with `"review_status": "pending",`
so the dict reads:

```python
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
```

- [ ] **Step 5: Run the full grist suite to verify it passes**

Run: `uv run python -m pytest tests/test_grist_migrate_domain.py tests/test_grist_cli.py -q`
Expected: PASS — all passed.

- [ ] **Step 6: Commit**

```bash
git add mascarade_eval/grist/migrate.py mascarade_eval/grist/cli.py tests/test_grist_migrate_domain.py
git commit -m "refactor(grist): producers write review_status"
```

---

## Task 3: Column DDL on the Grist client

**Files:**
- Modify: `mascarade_eval/grist/client.py`
- Test: `tests/test_grist_client.py`

- [ ] **Step 1: Rewrite the client test**

Replace the entire contents of `tests/test_grist_client.py` with:

```python
# tests/test_grist_client.py
import pytest
from mascarade_eval.grist.client import GristClient, load_grist_key


def _recording_transport(log):
    def transport(method, url, key, body):
        log.append((method, url, body))
        if method == "GET" and url.endswith("/tables"):
            return {"tables": [{"id": "Existing"}]}
        if method == "GET" and url.endswith("/columns"):
            return {"columns": [{"id": "item_key"}, {"id": "domain"}]}
        if method == "GET" and "/records" in url:
            return {"records": [
                {"id": 1, "fields": {"item_key": "k1",
                                     "review_status": "pending"}},
                {"id": 2, "fields": {"item_key": "k2",
                                     "review_status": "validated"}},
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
        {"_id": 1, "item_key": "k1", "review_status": "pending"},
        {"_id": 2, "item_key": "k2", "review_status": "validated"},
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


def test_create_table_assigns_column_types():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    c.create_table("T", ("item_key", "n_items", "review_status"))
    method, url, body = log[-1]
    assert method == "POST"
    cols = {col["id"]: col["fields"]["type"]
            for col in body["tables"][0]["columns"]}
    assert cols == {"item_key": "Text", "n_items": "Int",
                    "review_status": "Choice"}


def test_list_columns_returns_ids():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    assert c.list_columns("Heldout_Items") == {"item_key", "domain"}
    method, url, _ = log[-1]
    assert method == "GET"
    assert url.endswith("/docs/doc1/tables/Heldout_Items/columns")


def test_add_columns_posts_choice_with_widget_options():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    c.add_columns("Heldout_Items", ("review_status", "review_note"))
    method, url, body = log[-1]
    assert method == "POST"
    assert url.endswith("/docs/doc1/tables/Heldout_Items/columns")
    by_id = {col["id"]: col["fields"] for col in body["columns"]}
    assert by_id["review_status"]["type"] == "Choice"
    assert "pending" in by_id["review_status"]["widgetOptions"]
    assert by_id["review_note"]["type"] == "Text"


def test_add_columns_noop_on_empty():
    log = []
    c = GristClient("doc1", "key1", transport=_recording_transport(log))
    c.add_columns("T", ())
    assert log == []


def test_load_grist_key_prefers_env(monkeypatch):
    monkeypatch.setenv("GRIST_API_KEY", "env-key")
    assert load_grist_key() == "env-key"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_grist_client.py -q`
Expected: FAIL — `AttributeError: 'GristClient' object has no attribute 'list_columns'`.

- [ ] **Step 3: Rewrite `client.py`**

Replace the entire contents of `mascarade_eval/grist/client.py` with:

```python
# mascarade_eval/grist/client.py
"""Thin Grist REST client. The HTTP transport is injectable for tests."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from . import GRIST_BASE, KEY_FILE, REVIEW_STATUSES, REVIEWER_CHOICES

_INT_COLS = {"n_items", "n_rows"}
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
        if not rows:
            return
        for start in range(0, len(rows), 100):
            chunk = rows[start:start + 100]
            self._api("POST", f"/docs/{self.doc_id}/tables/{table}/records",
                      {"records": [{"fields": r} for r in chunk]})
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run python -m pytest tests/test_grist_client.py -q`
Expected: PASS — 10 passed.

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/client.py tests/test_grist_client.py
git commit -m "feat(grist): add column DDL to client"
```

---

## Task 4: Review-column schema migration

**Files:**
- Create: `mascarade_eval/grist/schema.py`
- Modify: `tests/conftest.py` (extend `FakeClient` with column DDL)
- Test: `tests/test_grist_schema.py`

- [ ] **Step 1: Extend `FakeClient` in `conftest.py`**

Replace the entire contents of `tests/conftest.py` with:

```python
# tests/conftest.py
import pytest


class FakeClient:
    """In-memory stand-in for GristClient. Records all writes."""

    def __init__(self, tables=None, records=None, columns=None):
        self.doc_id = "fake-doc"
        self._tables = set(tables or [])
        self._records = {t: list(rs) for t, rs in (records or {}).items()}
        self._columns = {t: list(cs) for t, cs in (columns or {}).items()}
        self.created = []
        self.added = {}
        self.added_columns = {}

    def list_tables(self):
        return set(self._tables)

    def create_table(self, table, columns):
        self._tables.add(table)
        self._columns[table] = list(columns)
        self.created.append((table, tuple(columns)))

    def ensure_table(self, table, columns):
        if table not in self._tables:
            self.create_table(table, columns)

    def list_columns(self, table):
        return set(self._columns.get(table, []))

    def add_columns(self, table, columns):
        self._columns.setdefault(table, []).extend(columns)
        self.added_columns.setdefault(table, []).extend(columns)

    def fetch_records(self, table):
        return [dict(r) for r in self._records.get(table, [])]

    def add_records(self, table, rows):
        self.added.setdefault(table, []).extend(rows)
        self._records.setdefault(table, []).extend(rows)


@pytest.fixture
def fake_client():
    return FakeClient
```

- [ ] **Step 2: Write the failing schema test**

Create `tests/test_grist_schema.py`:

```python
# tests/test_grist_schema.py
from mascarade_eval.grist import REVIEW_COLUMNS
from mascarade_eval.grist.schema import ensure_review_columns, migrate_doc


def test_ensure_review_columns_adds_all_when_absent(fake_client):
    client = fake_client(tables=["Heldout_Items"],
                         columns={"Heldout_Items": ["item_key", "prompt"]})
    added = ensure_review_columns(client, "Heldout_Items")
    assert added == list(REVIEW_COLUMNS)
    assert client.added_columns["Heldout_Items"] == list(REVIEW_COLUMNS)


def test_ensure_review_columns_is_idempotent(fake_client):
    cols = ["item_key", *REVIEW_COLUMNS]
    client = fake_client(tables=["Heldout_Items"],
                         columns={"Heldout_Items": cols})
    added = ensure_review_columns(client, "Heldout_Items")
    assert added == []
    assert "Heldout_Items" not in client.added_columns


def test_ensure_review_columns_adds_only_missing(fake_client):
    client = fake_client(
        tables=["Datasets"],
        columns={"Datasets": ["domain", "review_status", "reviewer"]})
    added = ensure_review_columns(client, "Datasets")
    assert added == ["reviewed_at", "review_note"]


def test_migrate_doc_skips_absent_tables(fake_client):
    client = fake_client(tables=["Heldout_Items"],
                         columns={"Heldout_Items": ["item_key"]})
    report = migrate_doc(client, ("Heldout_Items", "Mascarade_Training"))
    assert report["Heldout_Items"] == list(REVIEW_COLUMNS)
    assert report["Mascarade_Training"] is None
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_grist_schema.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'mascarade_eval.grist.schema'`.

- [ ] **Step 4: Write `schema.py`**

Create `mascarade_eval/grist/schema.py`:

```python
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
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run python -m pytest tests/test_grist_schema.py -q`
Expected: PASS — 4 passed.

- [ ] **Step 6: Commit**

```bash
git add mascarade_eval/grist/schema.py tests/conftest.py tests/test_grist_schema.py
git commit -m "feat(grist): add review-column schema migration"
```

---

## Task 5: `schema` CLI subcommand

**Files:**
- Modify: `mascarade_eval/grist/cli.py`
- Test: `tests/test_grist_cli.py`

- [ ] **Step 1: Write the failing CLI tests**

Append to `tests/test_grist_cli.py`:

```python
def test_parser_accepts_schema_command():
    ns = build_parser().parse_args(["schema"])
    assert ns.command == "schema"


def test_schema_command_runs_over_review_targets(monkeypatch, fake_client):
    from mascarade_eval.grist import cli
    made = fake_client(tables=["Heldout_Items"],
                       columns={"Heldout_Items": ["item_key"]})
    monkeypatch.setattr(cli.GristClient, "from_env",
                        classmethod(lambda c, doc: made))
    rc = cli.main(["schema"])
    assert rc == 0
    assert made.added_columns["Heldout_Items"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_grist_cli.py -k schema -q`
Expected: FAIL — `argparse` error `invalid choice: 'schema'`.

- [ ] **Step 3: Add the `schema` subparser**

In `cli.py` `build_parser`, after the `p_pub` block and before
`return ap`, add:

```python
    sub.add_parser("schema", help="add review columns to existing tables")
```

- [ ] **Step 4: Handle the `schema` command in `main`**

In `cli.py` `main`, immediately after the `if args.command == "publish":`
block (after its `return 0`) and before the line
`client = GristClient.from_env(resolve_doc(args.doc))`, add:

```python
    if args.command == "schema":
        from . import REVIEW_TARGETS
        from .schema import migrate_doc
        for doc_id, tables in REVIEW_TARGETS.items():
            doc_client = GristClient.from_env(doc_id)
            report = migrate_doc(doc_client, tables)
            print(f"schema {doc_id}: {report}")
        return 0
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run python -m pytest tests/test_grist_cli.py -q`
Expected: PASS — all passed.

- [ ] **Step 6: Commit**

```bash
git add mascarade_eval/grist/cli.py tests/test_grist_cli.py
git commit -m "feat(grist): add schema CLI subcommand"
```

---

## Task 6: Gate the export on `review_status`

**Files:**
- Modify: `mascarade_eval/grist/export.py`
- Modify: `mascarade_eval/grist/cli.py` (`export` subparser + call)
- Test: `tests/test_grist_export.py`

- [ ] **Step 1: Rewrite the export test**

Replace the entire contents of `tests/test_grist_export.py` with:

```python
# tests/test_grist_export.py
import json
import pytest
from mascarade_eval.grist import TRAINING_TABLE, EXPORTS_TABLE
from mascarade_eval.grist.export import (
    canonical_jsonl, content_hash, export_domain,
)


def _row(key, status, q="Q", a="A"):
    return {"_id": key, "item_key": f"kicad-{key}", "domain": "kicad",
            "user_msg": q, "assistant_msg": a, "system": "",
            "extra_turns": "", "source": "", "notes": "",
            "review_status": status}


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
    assert json.loads(text) == {"v": 1}


def test_content_hash_stable():
    text = canonical_jsonl([("x", {"v": 1})])
    assert content_hash(text) == content_hash(text)
    assert len(content_hash(text)) == 64


def test_export_domain_ships_only_validated_rows(fake_client, tmp_path):
    client = fake_client(
        tables=[TRAINING_TABLE],
        records={TRAINING_TABLE: [
            _row(1, "validated", q="Q1", a="A1"),
            _row(2, "rejected", q="Q2", a="A2"),
            _row(3, "pending", q="Q3", a="A3"),
            _row(4, "needs_fix", q="Q4", a="A4"),
        ]},
    )
    report = export_domain(client, "kicad", out_dir=tmp_path)
    assert report["n_items"] == 1  # only the validated row
    out_file = tmp_path / report["output_file"]
    written = [json.loads(ln) for ln in out_file.read_text().splitlines()]
    assert written == [{"messages": [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1"},
    ]}]
    assert client.added[EXPORTS_TABLE][0]["content_hash"] == report["content_hash"]


def test_export_domain_include_pending_adds_pending_only(fake_client, tmp_path):
    client = fake_client(
        tables=[TRAINING_TABLE],
        records={TRAINING_TABLE: [
            _row(1, "validated"),
            _row(2, "pending"),
            _row(3, "rejected"),
            _row(4, ""),  # missing status -> treated as pending
        ]},
    )
    report = export_domain(client, "kicad", out_dir=tmp_path,
                           include_pending=True)
    assert report["n_items"] == 3  # validated + pending + empty, not rejected


def test_export_domain_dry_run_writes_nothing(fake_client, tmp_path):
    client = fake_client(
        tables=[TRAINING_TABLE],
        records={TRAINING_TABLE: [_row(1, "validated")]},
    )
    report = export_domain(client, "kicad", out_dir=tmp_path, dry_run=True)
    assert report["n_items"] == 1
    assert list(tmp_path.iterdir()) == []
    assert client.added == {}


def test_export_domain_removes_file_when_grist_logging_fails(
        fake_client, tmp_path):
    client = fake_client(
        tables=[TRAINING_TABLE],
        records={TRAINING_TABLE: [_row(1, "validated")]},
    )

    def boom(table, rows):
        raise RuntimeError("grist down")

    client.add_records = boom
    with pytest.raises(RuntimeError, match="grist down"):
        export_domain(client, "kicad", out_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m pytest tests/test_grist_export.py -q`
Expected: FAIL — `test_export_domain_ships_only_validated_rows` reports `n_items == 4` (the old `exclure` filter lets every row through).

- [ ] **Step 3: Rewrite `export.py`**

Replace the entire contents of `mascarade_eval/grist/export.py` with:

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


def _is_exportable(row: dict, include_pending: bool) -> bool:
    """A row ships only when validated (or pending, if explicitly allowed).

    `rejected` and `needs_fix` rows are always excluded. A row with no
    review_status is treated as `pending`.
    """
    status = row.get("review_status") or "pending"
    if status == "validated":
        return True
    return include_pending and status == "pending"


def export_domain(client, domain: str, out_dir: Path,
                  dry_run: bool = False,
                  include_pending: bool = False) -> dict:
    """Export one domain's human-validated training rows to a hashed snapshot.

    Returns a report dict matching the Exports row written to Grist.
    """
    rows = [r for r in client.fetch_records(TRAINING_TABLE)
            if r.get("domain") == domain
            and _is_exportable(r, include_pending)]
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
    out_path = out_dir / filename
    out_path.write_text(payload + ("\n" if payload else ""),
                        encoding="utf-8")
    try:
        client.ensure_table(EXPORTS_TABLE, EXPORTS_COLUMNS)
        client.add_records(EXPORTS_TABLE, [report])
    except Exception:
        out_path.unlink(missing_ok=True)
        raise
    return report
```

- [ ] **Step 4: Wire `--include-pending` into the CLI**

In `cli.py` `build_parser`, in the `p_exp` block, after
`p_exp.add_argument("--dry-run", action="store_true")` add:

```python
    p_exp.add_argument("--include-pending", action="store_true",
                       help="also export rows still pending review")
```

In `cli.py` `main`, replace the `export` branch call:

```python
    elif args.command == "export":
        report = export_domain(client, args.domain, EXPORTS_DIR,
                               dry_run=args.dry_run)
        print(f"export {args.domain}: {report}")
```

with:

```python
    elif args.command == "export":
        report = export_domain(client, args.domain, EXPORTS_DIR,
                               dry_run=args.dry_run,
                               include_pending=args.include_pending)
        print(f"export {args.domain}: {report}")
```

- [ ] **Step 5: Add a CLI parser test**

Append to `tests/test_grist_cli.py`:

```python
def test_parser_export_accepts_include_pending():
    ns = build_parser().parse_args(
        ["export", "--doc", "D", "--domain", "kicad", "--include-pending"])
    assert ns.include_pending is True
```

- [ ] **Step 6: Run the full grist suite to verify it passes**

Run: `uv run python -m pytest tests/test_grist_export.py tests/test_grist_cli.py -q`
Expected: PASS — all passed.

- [ ] **Step 7: Run the entire test suite for regressions**

Run: `uv run python -m pytest -q`
Expected: PASS — all tests passed (89+ tests; no `exclure` references remain).

- [ ] **Step 8: Commit**

```bash
git add mascarade_eval/grist/export.py mascarade_eval/grist/cli.py tests/test_grist_export.py tests/test_grist_cli.py
git commit -m "feat(grist): gate export on review_status"
```

---

## Task 7: Native bench views, form, and choice-color recipe

**Files:**
- Create: `docs/grist-native-views-recipe.md`

This task produces an operator recipe — Grist pages, views, forms and
conditional formatting are configured in the Grist UI, not via the API.

- [ ] **Step 1: Write the recipe document**

Create `docs/grist-native-views-recipe.md`:

````markdown
# Grist native review views — operator recipe

Manual Grist UI steps for the parts of the human-review layer that are
not API-scriptable. Run the schema migration first
(`python -m mascarade_eval.grist.cli schema`) so the review columns
exist.

## 1. review_status choice colors

For each table carrying `review_status` (`Heldout_Items`, `Datasets`
in doc *ailiance-llm-workflow*; `Mascarade_Eval_Items`,
`Bench_31_domains` in doc *mascarade-data*, plus `Mascarade_Training`):

1. Open the table, click the `review_status` column header → **Column
   options**.
2. Under **CHOICES**, confirm the four values are present: `pending`,
   `validated`, `rejected`, `needs_fix`.
3. Set the chip color of each: pending = grey `#E8E8E8`,
   validated = green `#C6E5B3`, rejected = red `#F2B5B5`,
   needs_fix = amber `#F5D9A6`.

## 2. Bench_31_domains review page (doc mascarade-data)

1. **Add Page** → name it `Bench review`.
2. Add a **Table** widget bound to `Bench_31_domains`.
3. Add a filter on `review_status` and a second on `domain`; save the
   view so the filters persist.
4. Conditional formatting (column header → **Column options** →
   **Add conditional style**):
   - `judge_score`: red when `$judge_score < 50`, amber when
     `$judge_score < 70`, green otherwise.
   - `validator_score`: red when `$validator_score < 50`, green when
     `$validator_score >= 70`.
   - `ppl`: red when `$ppl > 20`, amber when `$ppl > 10`.
5. Add a **Card List** widget on the same page bound to
   `Bench_31_domains`, linked to the table widget, showing `model`,
   `domain`, `judge_score`, `judge_rationale`, `validator_score`,
   `review_status`, `reviewer`, `review_note` — this is the per-row
   review surface.

## 3. Datasets review view (doc ailiance-llm-workflow)

1. **Add Page** → `Datasets review`.
2. Add a **Table** widget bound to `Datasets`, filtered on
   `review_status`.
3. Show `domain`, `name`, `n_rows`, `license`, `hf_dataset_id`,
   `review_status`, `reviewer`, `review_note`.

## 4. Read-only scoreboards

For `Bench_public`, `Bench_niches_ppl`, `Bench_gateway`,
`Bench_lift_v1`, `Bench_lift_v2`: add one page `Scoreboards` with a
Table widget per table. Apply conditional formatting on the score
columns (green high / red low) as in section 2. No review columns —
these tables are reference only.

## 5. Bench entry form (doc mascarade-data)

1. **Add Page** → `Bench entry`.
2. Add a **Form** widget bound to `Bench_31_domains`.
3. Keep only these fields on the form: `model`, `domain`, `ppl`,
   `task_score`, `task_metric`, `judge_score`, `source`, `date`.
   Remove pipeline-only fields (`validator_image_digest`, `run_id`,
   `host`, `runtime_s`, `tokens_per_s`, …).
4. Click **Publish** and copy the share URL — this is the manual
   bench-result entry form. Automated runs keep writing via the API.

## 6. Clean-up

Delete the empty default `Table1` (columns A/B/C) in each of the three
documents.
````

- [ ] **Step 2: Verify the file is valid Markdown**

Run: `python3 -c "import pathlib; t=pathlib.Path('docs/grist-native-views-recipe.md').read_text(); assert t.count('```')%2==0; print('fenced blocks balanced, %d lines'%len(t.splitlines()))"`
Expected: prints `fenced blocks balanced, N lines`.

- [ ] **Step 3: Commit**

```bash
git add docs/grist-native-views-recipe.md
git commit -m "docs(grist): add native views and form recipe"
```

---

## Task 8: Review Console widget

**Files:**
- Create: `widgets/review-console/index.html`

A single self-contained static file: a table-agnostic Grist custom
widget for one-at-a-time review of dataset items. `reviewed_at` is
written as an ISO-8601 string (the `review_*` columns are created as
Text/Choice — see Task 3 — so the widget needs no epoch conversion).

- [ ] **Step 1: Create the widget file**

Create `widgets/review-console/index.html`:

```html
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Review Console</title>
<script src="https://grist.saillant.cc/grist-plugin-api.js"></script>
<style>
  body { font: 14px/1.5 system-ui, sans-serif; margin: 0; padding: 16px;
         color: #1a1a1a; }
  #progress { color: #666; font-size: 13px; margin-bottom: 8px; }
  .field-label { font-weight: 600; font-size: 12px; text-transform: uppercase;
                 color: #888; margin-top: 12px; }
  .field-value { white-space: pre-wrap; word-break: break-word;
                 background: #f6f6f6; border-radius: 6px; padding: 8px; }
  #context { color: #555; font-size: 13px; margin-bottom: 4px; }
  #note { width: 100%; box-sizing: border-box; margin-top: 12px; padding: 6px; }
  #buttons { display: flex; gap: 8px; margin-top: 12px; }
  button { flex: 1; padding: 10px; border: 0; border-radius: 6px;
           font-size: 14px; cursor: pointer; }
  .validate { background: #C6E5B3; }
  .reject   { background: #F2B5B5; }
  .needsfix { background: #F5D9A6; }
  .skip     { background: #E8E8E8; }
  #done { font-size: 16px; color: #2a7; padding: 24px 0; }
  #empty { color: #888; padding: 24px 0; }
</style>
</head>
<body>
  <div id="progress"></div>
  <div id="card" hidden>
    <div id="context"></div>
    <div class="field-label">Item</div>
    <div class="field-value" id="primary"></div>
    <div class="field-label" id="secondary-label">Référence</div>
    <div class="field-value" id="secondary"></div>
    <input id="note" placeholder="note de revue (optionnelle)">
    <div id="buttons">
      <button class="validate" id="b-validate">✓ Valider (V)</button>
      <button class="reject"   id="b-reject">✗ Rejeter (R)</button>
      <button class="needsfix" id="b-needsfix">~ À corriger (F)</button>
      <button class="skip"     id="b-skip">→ Passer (S)</button>
    </div>
  </div>
  <div id="done" hidden>Tous les items en attente sont revus ✓</div>
  <div id="empty" hidden>Aucune ligne dans cette table.</div>
<script>
"use strict";
const REVIEWER = "clems";   // adjust to the reviewer's Grist choice value

let rows = [];      // [{id, status, primary, secondary, context}]
let queue = [];     // ids still pending
let cursor = 0;

const $ = (id) => document.getElementById(id);

function rebuild(records) {
  rows = records.map((rec) => {
    const m = grist.mapColumnNames(rec) || {};
    let ctx = m.context;
    if (Array.isArray(ctx)) ctx = ctx.filter(Boolean).join(" · ");
    return {
      id: rec.id,
      status: rec.review_status || "pending",
      primary: m.primary == null ? "" : String(m.primary),
      secondary: m.secondary == null ? "" : String(m.secondary),
      context: ctx == null ? "" : String(ctx),
    };
  });
  queue = rows.filter((r) => r.status === "pending").map((r) => r.id);
  if (cursor >= queue.length) cursor = 0;
  render();
}

function render() {
  const total = rows.length;
  const reviewed = rows.filter((r) => r.status !== "pending").length;
  $("progress").textContent = total === 0 ? ""
    : `revus ${reviewed} / ${total} — en attente ${queue.length}`;
  $("empty").hidden = total !== 0;
  const item = queue.length
    ? rows.find((r) => r.id === queue[cursor]) : null;
  $("card").hidden = !item;
  $("done").hidden = !(total > 0 && !item);
  if (!item) return;
  $("context").textContent = item.context;
  $("primary").textContent = item.primary;
  $("secondary").textContent = item.secondary;
  $("secondary-label").hidden = !item.secondary;
  $("secondary").hidden = !item.secondary;
}

async function decide(status) {
  if (!queue.length) return;
  const id = queue[cursor];
  await grist.selectedTable.update({
    id,
    fields: {
      review_status: status,
      reviewer: REVIEWER,
      reviewed_at: new Date().toISOString(),
      review_note: $("note").value,
    },
  });
  $("note").value = "";
  // grist.onRecords refires after the update and rebuilds the queue.
}

function skip() {
  if (!queue.length) return;
  cursor = (cursor + 1) % queue.length;
  render();
}

$("b-validate").onclick = () => decide("validated");
$("b-reject").onclick = () => decide("rejected");
$("b-needsfix").onclick = () => decide("needs_fix");
$("b-skip").onclick = skip;

document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT") return;
  const k = e.key.toLowerCase();
  if (k === "v") decide("validated");
  else if (k === "r") decide("rejected");
  else if (k === "f") decide("needs_fix");
  else if (k === "s" || e.key === "ArrowRight") skip();
});

grist.ready({
  requiredAccess: "full",
  columns: [
    { name: "primary", title: "Texte principal (prompt / user_msg)" },
    { name: "secondary", title: "Référence (reference / assistant_msg)",
      optional: true },
    { name: "context", title: "Contexte (domain, source)",
      optional: true, allowMultiple: true },
  ],
});
grist.onRecords(rebuild);
</script>
</body>
</html>
```

- [ ] **Step 2: Syntax-check the embedded script**

Run: `python3 -c "import pathlib,re; h=pathlib.Path('widgets/review-console/index.html').read_text(); s=re.search(r'<script>(.*?)</script>', h, re.S).group(1); pathlib.Path('/tmp/rc.js').write_text(s); print('script extracted, %d lines'%len(s.splitlines()))" && node --check /tmp/rc.js && echo "JS syntax OK"`
Expected: prints the line count then `JS syntax OK`. (Full functional verification is the smoke test in Task 9.)

- [ ] **Step 3: Commit**

```bash
git add widgets/review-console/index.html
git commit -m "feat(grist): add review console widget"
```

---

## Task 9: Widget setup recipe and smoke test

**Files:**
- Create: `docs/grist-widget-setup.md`

- [ ] **Step 1: Write the widget setup document**

Create `docs/grist-widget-setup.md`:

````markdown
# Review Console widget — hosting, wiring, smoke test

The widget at `widgets/review-console/index.html` is a static file. It
must be served over HTTPS and registered in Grist as a Custom URL
widget.

## 1. Host the static file

Serve the file behind the existing electron-server cloudflared tunnel.

```bash
# from the repo, on the dev machine
scp widgets/review-console/index.html \
    electron-server:/srv/grist-widgets/review-console/index.html
```

On electron-server, expose `/srv/grist-widgets/` via the existing
static file server / Caddy / nginx and add a cloudflared route so the
file is reachable at:

```
https://grist-widgets.saillant.cc/review-console/index.html
```

Verify: `curl -sI https://grist-widgets.saillant.cc/review-console/index.html`
should return `HTTP/2 200`.

> Hosting touches shared infra (cloudflared, electron-server) — confirm
> with the operator before applying the route.

## 2. Add a review page in Grist

In doc *ailiance-llm-workflow*:

1. **Add Page** → `Heldout review`.
2. Add a **Custom** widget. Select **Custom URL** and paste
   `https://grist-widgets.saillant.cc/review-console/index.html`.
3. Bind the widget to the `Heldout_Items` table.
4. When prompted, grant the widget **Full document access** (it must
   write the review columns).
5. Open the widget's **Column mapping**:
   - `primary` → `prompt`
   - `secondary` → `reference`
   - `context` → `domain`, `source`

Repeat for the future `Mascarade_Training` table (map `primary` →
`user_msg`, `secondary` → `assistant_msg`) and for
`Mascarade_Eval_Items` in doc *mascarade-data* (map `primary` →
`question`, `secondary` → `reference`).

## 3. Smoke-test checklist

On the `Heldout review` page:

- [ ] The progress line shows `revus 0 / 400 — en attente 400`.
- [ ] The first pending item's prompt and reference render in full.
- [ ] Pressing `V` writes `review_status = validated`, `reviewer`,
      `reviewed_at` (ISO-8601) and advances to the next item; the
      progress counter increments.
- [ ] Pressing `R` and `F` write `rejected` / `needs_fix`.
- [ ] A value typed in the note field lands in `review_note` and the
      field clears after the decision.
- [ ] `S` / `→` skips without writing.
- [ ] After every pending row is decided, the widget shows
      "Tous les items en attente sont revus ✓".
- [ ] Re-running `python -m mascarade_eval.grist.cli export --domain
      <d>` ships only the rows marked `validated`.
````

- [ ] **Step 2: Verify the file is valid Markdown**

Run: `python3 -c "import pathlib; t=pathlib.Path('docs/grist-widget-setup.md').read_text(); assert t.count('```')%2==0; print('fenced blocks balanced, %d lines'%len(t.splitlines()))"`
Expected: prints `fenced blocks balanced, N lines`.

- [ ] **Step 3: Commit**

```bash
git add docs/grist-widget-setup.md
git commit -m "docs(grist): add widget setup recipe"
```

---

## Post-implementation

- Run the schema migration against the live docs:
  `cd mascarade-eval && uv run python -m mascarade_eval.grist.cli schema`
- Follow `docs/grist-native-views-recipe.md` then
  `docs/grist-widget-setup.md` in the Grist UI.
- Merge branch `worktree-grist-dataset-mgmt` (Phase 1 + this review
  layer) to `main`.

## Risks

1. **Grist `widgetOptions` contract** — `add_columns` sends
   `widgetOptions` as a JSON string. If the Grist build rejects it, the
   Choice column is still created (just without seeded choices); add
   choices via the recipe in `docs/grist-native-views-recipe.md`.
   Verify on the first `schema` run against a scratch table.
2. **Custom widget access** — self-hosted Grist must allow Custom URL
   widgets and the operator must grant full document access; otherwise
   the widget loads read-only and write-back fails silently.
3. **Widget hosting** — depends on shared electron-server / cloudflared
   infra; treat the route change as an operator-confirmed step.
