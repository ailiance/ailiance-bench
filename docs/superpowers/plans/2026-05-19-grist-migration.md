# Grist Data Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Copy every row of the existing Grist tables into the four `ailiance-llm-*` documents, row-by-row verified, then rewire `mascarade_eval/grist/` to the new topology.

**Architecture:** A schema-adaptive migration engine: a `MIGRATION_MAP` declares each `(source doc, table) → (target doc, table)` with an optional column-rename dict; the engine reads live source rows, applies renames, keeps only columns the target table declares, and reports any source column it dropped. A row-level hash check verifies no loss. A one-shot script wires the doc IDs from `grist.env` and runs the map (with a dry-run mode). Finally the `mascarade_eval/grist/` constants are repointed at the new docs.

**Tech Stack:** Python ≥3.12, stdlib, `uv`, `pytest`. Reuses `GristClient`, `load_doc_id`, `LLM_DOCS`.

**Spec:** `docs/superpowers/specs/2026-05-19-grist-migration-design.md`.

---

## Repo and worktree

Work in **`ailiance-bench`**, sub-project `mascarade-eval/`, on `main` (consistent with the provisioning sub-project's commits). Create an isolated worktree if preferred (superpowers:using-git-worktrees).

**Test command:** `uv run --extra dev python -m pytest` (from `mascarade-eval/`).
**Commit format:** subject ≤50 chars incl. prefix; body ≤72; no AI attribution; no underscore in scope.

## Why schema-adaptive

The `mascarade-data` doc tables (`Mascarade_Eval`, `Bench_31_domains`, `Mascarade_Eval_Items`, `Bench_mascarade_heldout`) have schemas not known at planning time. The engine therefore does NOT hardcode their columns: it reads whatever columns each source row has, applies an explicit `rename` dict (empty by default), and keeps only the keys the target table declares in `LLM_DOCS`. Its dry-run mode prints, per table, the source columns that were dropped — so the operator adds renames to `MIGRATION_MAP` before the real run if a drop is wrong.

## File structure

| File | Responsibility | Action |
|------|----------------|--------|
| `mascarade_eval/grist/llm_schema.py` | 4-doc schema | Modify — add `Datasets` table to `training` |
| `tests/test_grist_llm_schema.py` | schema tests | Modify — assert `Datasets` |
| `mascarade_eval/grist/grist_migrate.py` | Migration engine: `row_hash`, `map_row`, `migrate_table`, `MIGRATION_MAP` | Create |
| `tests/test_grist_migrate_engine.py` | Engine tests | Create |
| `scripts/migrate_grist_docs.py` | One-shot script wiring doc IDs + run | Create |
| `tests/test_migrate_grist_docs.py` | Script env-resolution test | Create |
| `mascarade_eval/grist/__init__.py` | Doc/table constants | Modify — repoint to new topology |

---

## Task 1: Add the `Datasets` table to the training-doc schema

**Files:**
- Modify: `mascarade_eval/grist/llm_schema.py`
- Modify: `tests/test_grist_llm_schema.py`

`Datasets_Registry` migrates into a new `Datasets` table in the `training` doc.

- [ ] **Step 1: Add the failing assertion**

In `tests/test_grist_llm_schema.py`, the test `test_each_doc_declares_its_tables` currently asserts `set(LLM_DOCS["training"]) == {"Exports", "Training_Runs"}`. Change that one line to:

```python
    assert set(LLM_DOCS["training"]) == {"Exports", "Training_Runs",
                                         "Datasets"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_grist_llm_schema.py -v`
Expected: FAIL — `test_each_doc_declares_its_tables` (training has only 2 tables).

- [ ] **Step 3: Add the table to the schema**

In `mascarade_eval/grist/llm_schema.py`, inside `LLM_DOCS["training"]`, add a third entry after `Training_Runs`:

```python
        "Datasets": (
            "name", "family", "domain", "hf_dataset_id", "license",
            "n_items", "notes",
        ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev python -m pytest tests/test_grist_llm_schema.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/llm_schema.py tests/test_grist_llm_schema.py
git commit -m "feat(grist): add Datasets table to training doc"
```

---

## Task 2: The migration engine

**Files:**
- Create: `mascarade_eval/grist/grist_migrate.py`
- Test: `tests/test_grist_migrate_engine.py`

`map_row` and `row_hash` are pure. `migrate_table` ties them to two clients (source + target). `MIGRATION_MAP` is the declarative table list.

- [ ] **Step 1: Write the failing test**

Create `tests/test_grist_migrate_engine.py`:

```python
from mascarade_eval.grist.grist_migrate import (
    MIGRATION_MAP, map_row, row_hash, migrate_table,
)


def test_map_row_renames_and_keeps_target_columns():
    src = {"_id": 3, "old_name": "v1", "keep": "v2", "drop_me": "v3"}
    out = map_row(src, rename={"old_name": "new_name"},
                  target_columns=("new_name", "keep"))
    assert out == {"new_name": "v1", "keep": "v2"}


def test_map_row_drops_grist_internal_id():
    out = map_row({"_id": 9, "keep": "v"}, rename={},
                  target_columns=("keep",))
    assert "_id" not in out


def test_row_hash_is_order_independent():
    assert row_hash({"a": 1, "b": 2}) == row_hash({"b": 2, "a": 1})


def test_row_hash_differs_on_content():
    assert row_hash({"a": 1}) != row_hash({"a": 2})


def test_migrate_table_copies_and_verifies(fake_client):
    src = fake_client(records={"Src": [
        {"_id": 1, "item_key": "k1", "domain": "kicad", "extra": "x"},
        {"_id": 2, "item_key": "k2", "domain": "spice", "extra": "y"},
    ]})
    tgt = fake_client(tables=[])
    report = migrate_table(
        src, tgt, src_table="Src", tgt_table="Dst",
        tgt_columns=("item_key", "domain"), rename={})
    assert report["copied"] == 2
    assert report["verified"] is True
    assert report["dropped_columns"] == ["extra"]
    written = tgt.added["Dst"]
    assert {r["item_key"] for r in written} == {"k1", "k2"}
    assert all("extra" not in r for r in written)


def test_migrate_table_dry_run_writes_nothing(fake_client):
    src = fake_client(records={"Src": [
        {"_id": 1, "item_key": "k1", "domain": "kicad"}]})
    tgt = fake_client(tables=[])
    report = migrate_table(
        src, tgt, src_table="Src", tgt_table="Dst",
        tgt_columns=("item_key", "domain"), rename={}, dry_run=True)
    assert report["copied"] == 1
    assert tgt.added == {}


def test_migration_map_targets_known_docs():
    valid = {"heldout_old", "mascarade_old", "training_old",
             "domain", "training", "bench"}
    for entry in MIGRATION_MAP:
        assert entry["src_doc"] in valid
        assert entry["tgt_doc"] in valid
        assert isinstance(entry["rename"], dict)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_grist_migrate_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mascarade_eval.grist.grist_migrate'`

- [ ] **Step 3: Write the implementation**

Create `mascarade_eval/grist/grist_migrate.py`:

```python
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
    tgt_client.add_records(tgt_table, mapped)

    want = sorted(row_hash(m) for m in mapped)
    got = sorted(row_hash(map_row(r, {}, tgt_columns))
                 for r in tgt_client.fetch_records(tgt_table))
    report["verified"] = all(h in got for h in want)
    return report


# Declarative migration table. `rename` starts empty; a dry-run prints
# `dropped_columns` per entry so the operator adds renames where a drop
# is unintended, before the real run.
MIGRATION_MAP: list[dict] = [
    {"src_doc": "training_old", "src_table": "Mascarade_Training",
     "tgt_doc": "domain", "tgt_table": "Dataset_Items", "rename": {}},
    {"src_doc": "heldout_old", "src_table": "Heldout_Items",
     "tgt_doc": "bench", "tgt_table": "Eval_Items", "rename": {}},
    {"src_doc": "training_old", "src_table": "Exports",
     "tgt_doc": "training", "tgt_table": "Exports", "rename": {}},
    {"src_doc": "training_old", "src_table": "Datasets_Registry",
     "tgt_doc": "training", "tgt_table": "Datasets", "rename": {}},
    {"src_doc": "mascarade_old", "src_table": "Mascarade_Eval",
     "tgt_doc": "bench", "tgt_table": "Bench_Results", "rename": {}},
    {"src_doc": "mascarade_old", "src_table": "Bench_31_domains",
     "tgt_doc": "bench", "tgt_table": "Bench_Results", "rename": {}},
    {"src_doc": "mascarade_old", "src_table": "Mascarade_Eval_Items",
     "tgt_doc": "bench", "tgt_table": "Eval_Items", "rename": {}},
    {"src_doc": "mascarade_old", "src_table": "Bench_mascarade_heldout",
     "tgt_doc": "bench", "tgt_table": "Eval_Items", "rename": {}},
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev python -m pytest tests/test_grist_migrate_engine.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/grist_migrate.py tests/test_grist_migrate_engine.py
git commit -m "feat(grist): add schema-adaptive migration engine"
```

---

## Task 3: The migration script

**Files:**
- Create: `scripts/migrate_grist_docs.py`
- Test: `tests/test_migrate_grist_docs.py`

The script resolves source and target doc IDs, then runs every `MIGRATION_MAP` entry. Source docs `heldout_old` and `mascarade_old` are fixed IDs; `training_old` and the three targets come from env.

- [ ] **Step 1: Write the failing test**

Create `tests/test_migrate_grist_docs.py`:

```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import migrate_grist_docs as m  # noqa: E402


def test_fixed_source_docs_are_the_known_ids():
    assert m.SRC_FIXED["heldout_old"] == "eGbbrpzN3TeLq3sUd2YFA2"
    assert m.SRC_FIXED["mascarade_old"] == "dhyrySCayizD1PNqCNhCPN"


def test_resolve_doc_ids_merges_fixed_and_env(monkeypatch):
    monkeypatch.setattr(m, "load_doc_id", lambda name: f"id-{name}")
    ids = m.resolve_doc_ids()
    assert ids["heldout_old"] == "eGbbrpzN3TeLq3sUd2YFA2"
    assert ids["training_old"] == "id-GRIST_DOC_TRAINING"
    assert ids["domain"] == "id-GRIST_DOC_LLM_DOMAIN"
    assert ids["bench"] == "id-GRIST_DOC_LLM_BENCH"


def test_resolve_doc_ids_exits_on_missing_env(monkeypatch):
    monkeypatch.setattr(
        m, "load_doc_id",
        lambda name: None if name == "GRIST_DOC_LLM_BENCH" else "x")
    with pytest.raises(SystemExit):
        m.resolve_doc_ids()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_migrate_grist_docs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'migrate_grist_docs'`

- [ ] **Step 3: Write the implementation**

Create `scripts/migrate_grist_docs.py`:

```python
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

# Which (doc key, table) supplies the target column tuple.
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev python -m pytest tests/test_migrate_grist_docs.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_grist_docs.py tests/test_migrate_grist_docs.py
git commit -m "feat(grist): add grist docs migration script"
```

---

## Task 4: Rewire `mascarade_eval/grist/` constants to the new topology

**Files:**
- Modify: `mascarade_eval/grist/__init__.py`

The grist subpackage's table constants still name the old tables. Repoint them: training items now live in `Dataset_Items`, held-out/eval items in `Eval_Items`. The doc IDs become runtime-resolved (env), so the hardcoded `DOC_HELDOUT` is replaced by env-var names.

- [ ] **Step 1: Update the constants**

In `mascarade_eval/grist/__init__.py`, replace the doc-ID and table-name block. The current lines are:

```python
DOC_HELDOUT = "eGbbrpzN3TeLq3sUd2YFA2"      # ailiance-llm-workflow
DOC_MASCARADE = "dhyrySCayizD1PNqCNhCPN"    # mascarade-data
```
and
```python
TRAINING_TABLE = "Mascarade_Training"
```

Replace the two doc-ID lines with env-var-name constants:

```python
# New topology: doc IDs are resolved at runtime from grist.env.
DOC_DOMAIN_ENV = "GRIST_DOC_LLM_DOMAIN"
DOC_TRAINING_ENV = "GRIST_DOC_LLM_TRAINING"
DOC_BENCH_ENV = "GRIST_DOC_LLM_BENCH"
# Legacy doc IDs, kept read-only for the post-migration window.
DOC_HELDOUT_LEGACY = "eGbbrpzN3TeLq3sUd2YFA2"
DOC_MASCARADE_LEGACY = "dhyrySCayizD1PNqCNhCPN"
```

Replace `TRAINING_TABLE = "Mascarade_Training"` with:

```python
TRAINING_TABLE = "Dataset_Items"
EVAL_TABLE = "Eval_Items"
```

Leave `REGISTRY_TABLE`, `EXPORTS_TABLE`, `TRAINING_COLUMNS`, `REVIEW_*`, `EXPORTS_DIR` unchanged.

- [ ] **Step 2: Find every reference to the changed names**

Run: `grep -rn "DOC_HELDOUT\b\|DOC_MASCARADE\b\|Mascarade_Training" mascarade_eval/ tests/ scripts/`
Expected: a list of files still using the old names. They must be updated to use `DOC_HELDOUT_LEGACY` / `DOC_MASCARADE_LEGACY` (only in legacy-facing code such as `export_grist.py`) or `TRAINING_TABLE` (now `Dataset_Items`).

- [ ] **Step 3: Update each reference**

For each hit from Step 2, repoint it: code that ingests/exports training data uses `TRAINING_TABLE` (already a constant — its VALUE changed, so call sites that import the constant need no edit); any code with a literal `"Mascarade_Training"` switches to importing `TRAINING_TABLE`; any `DOC_HELDOUT` use becomes `DOC_HELDOUT_LEGACY`. Show each edit's before/after as you make it.

- [ ] **Step 4: Run the full suite**

Run: `uv run --extra dev python -m pytest -q`
Expected: PASS. Tests that asserted `TRAINING_TABLE == "Mascarade_Training"` must be updated to `"Dataset_Items"`. If a test fails because it pinned the old value, update the test's expected value (the constant's new value is correct) — do not revert the constant.

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/__init__.py tests/ mascarade_eval/ scripts/
git commit -m "refactor(grist): repoint constants to llm topology"
```

---

## Task 5: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `uv run --extra dev python -m pytest -q`
Expected: PASS — all tests green on the new topology.

- [ ] **Step 2: Confirm the migration script imports**

Run: `uv run --extra dev python -c "import sys; sys.path.insert(0,'scripts'); import migrate_grist_docs as m; print(len(m.MIGRATION_MAP), 'entries')"`
Expected: `8 entries`.

No commit — verification only.

---

## Manual validation (after all tasks, requires network)

Needs the four `GRIST_DOC_LLM_*` IDs plus `GRIST_DOC_TRAINING` in `grist.env`, and the target tables provisioned (provisioning sub-project):

1. `uv run python scripts/migrate_grist_docs.py --dry-run` — read the `dropped_columns` for each table. For any drop that is a renamed column (not a genuine removal), add a `rename` entry to that `MIGRATION_MAP` row and re-run the dry-run.
2. `uv run python scripts/migrate_grist_docs.py` — confirm every table reports `verified: True`. A non-zero exit means a verification failed.
3. Spot-check each of the four docs in the Grist UI.
4. Set the legacy docs (`eGbbrpzN3TeLq3sUd2YFA2`, `dhyrySCayizD1PNqCNhCPN`) to read-only; archive them after a validation period.

---

## Self-Review

**Spec coverage:**
- Migration script + `MIGRATION_MAP` — Tasks 2-3. All 8 source tables from the spec's migration table are entries in `MIGRATION_MAP`.
- `Datasets` table for `Datasets_Registry` — Task 1 (schema) + `MIGRATION_MAP` entry (Task 2).
- Row-by-row verification — `migrate_table` hash check (Task 2), surfaced as `verified` in the script (Task 3), gated in manual validation step 2.
- Rewire `mascarade_eval/grist/` — Task 4.
- Sequencing (migrate → verify → rewire → archive) — Tasks ordered 1-5; archiving is manual validation step 4.
- Column-mapping uncertainty for the `mascarade-data` tables — handled by the schema-adaptive engine + `--dry-run` `dropped_columns` report, not by hardcoding unknown schemas.

**Placeholder scan:** No `TBD`/`TODO`. `rename` dicts start empty by design — the dry-run report tells the operator which to fill; this is a deliberate, documented seam, not a placeholder.

**Type/name consistency:** `migrate_table(src_client, tgt_client, src_table, tgt_table, tgt_columns, rename, dry_run)` — same signature in Task 2 tests and Task 3's `main`. `MIGRATION_MAP` entry keys (`src_doc`, `src_table`, `tgt_doc`, `tgt_table`, `rename`) are consistent across Task 2 (definition + test) and Task 3 (`main` consumption). `row_hash`/`map_row` names match between definition and tests. The doc keys (`heldout_old`, `mascarade_old`, `training_old`, `domain`, `training`, `bench`) are consistent across `MIGRATION_MAP`, `SRC_FIXED`, `ENV_DOCS`, and `test_migration_map_targets_known_docs`.
