# ailiance-llm Grist Docs — Provisioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provision the table schemas of the four `ailiance-llm-*` Grist documents (domain, training, bench, workflow) idempotently, reusing the existing `GristClient`.

**Architecture:** The four Grist documents are created empty by hand in the Grist UI (a prerequisite); their IDs are stored in `~/.config/electron-rare/grist.env`. A new pure-data module `llm_schema.py` declares the 8 tables and their columns; a `provision_doc` function ensures each table exists via `GristClient.create_table`/`list_tables`. A one-shot script provisions all four docs. Idempotent: an existing table is left untouched.

**Tech Stack:** Python ≥3.12, stdlib, `uv`, `pytest`. Reuses `mascarade_eval/grist/client.py` (`GristClient`, `load_doc_id`).

**Spec:** `docs/superpowers/specs/2026-05-19-ailiance-llm-grist-docs-design.md` (sub-project 1).

---

## Repo and worktree

Work in the **`ailiance-bench`** repo, sub-project `mascarade-eval/`. Create an isolated worktree before starting (superpowers:using-git-worktrees). The `mascarade_eval/grist/` subpackage already exists on `main`.

**Test command:** `uv run --extra dev python -m pytest` (run from `mascarade-eval/`). The `--extra dev` flag is REQUIRED.

**Commit format:** subject ≤50 chars TOTAL incl. `feat(grist): ` prefix; body lines ≤72; no AI attribution; no underscore in scope.

## Prerequisites (manual, one-time — not a code task)

1. In the Grist UI (`grist.saillant.cc`), create four empty documents named **`ailiance-llm-domain`**, **`ailiance-llm-training`**, **`ailiance-llm-bench`**, **`ailiance-llm-workflow`**.
2. Copy each document ID from its URL and add four lines to `~/.config/electron-rare/grist.env`:
   ```
   GRIST_DOC_LLM_DOMAIN=<id>
   GRIST_DOC_LLM_TRAINING=<id>
   GRIST_DOC_LLM_BENCH=<id>
   GRIST_DOC_LLM_WORKFLOW=<id>
   ```
   Distinct names (`_LLM_` infixed) avoid collision with the Phase-1 `GRIST_DOC_TRAINING`.

## File structure

| File | Responsibility | Action |
|------|----------------|--------|
| `mascarade_eval/grist/llm_schema.py` | The 4-doc table schema (data) + `provision_doc` | Create |
| `tests/test_grist_llm_schema.py` | Tests for the schema + `provision_doc` | Create |
| `scripts/provision_llm_docs.py` | One-shot script: provision all 4 docs from env | Create |
| `tests/test_provision_llm_docs.py` | Test the script's env-resolution helper | Create |

---

## Task 1: The 4-doc schema and `provision_doc`

**Files:**
- Create: `mascarade_eval/grist/llm_schema.py`
- Test: `tests/test_grist_llm_schema.py`

`LLM_DOCS` is a plain dict mapping a doc key to its tables and their column tuples. `provision_doc` ensures every declared table exists in a doc, idempotently.

- [ ] **Step 1: Write the failing test**

Create `tests/test_grist_llm_schema.py`:

```python
from mascarade_eval.grist.llm_schema import LLM_DOCS, provision_doc


def test_llm_docs_has_the_four_documents():
    assert set(LLM_DOCS) == {"domain", "training", "bench", "workflow"}


def test_each_doc_declares_its_tables():
    assert set(LLM_DOCS["domain"]) == {"Sourcing", "Dataset_Items"}
    assert set(LLM_DOCS["training"]) == {"Exports", "Training_Runs"}
    assert set(LLM_DOCS["bench"]) == {"Bench_Results", "Eval_Items"}
    assert set(LLM_DOCS["workflow"]) == {"Pipeline_Status", "Audit_Log"}


def test_dataset_items_carries_review_columns():
    cols = LLM_DOCS["domain"]["Dataset_Items"]
    for c in ("item_key", "domain", "user_msg", "assistant_msg",
              "review_status"):
        assert c in cols


def test_provision_doc_creates_missing_tables(fake_client):
    client = fake_client(tables=[])
    report = provision_doc(client, LLM_DOCS["training"])
    assert report == {"Exports": "created", "Training_Runs": "created"}
    assert client.created[0][0] in {"Exports", "Training_Runs"}
    assert len(client.created) == 2


def test_provision_doc_is_idempotent(fake_client):
    client = fake_client(tables=["Exports"])
    report = provision_doc(client, LLM_DOCS["training"])
    assert report == {"Exports": "exists", "Training_Runs": "created"}
    assert [t for t, _ in client.created] == ["Training_Runs"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_grist_llm_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mascarade_eval.grist.llm_schema'`

- [ ] **Step 3: Write the implementation**

Create `mascarade_eval/grist/llm_schema.py`:

```python
# mascarade_eval/grist/llm_schema.py
"""Table schema for the four ailiance-llm-* Grist documents.

LLM_DOCS maps a doc key to {table_name: column_tuple}. provision_doc
ensures every declared table exists in a doc (idempotent).
"""
from __future__ import annotations

LLM_DOCS: dict[str, dict[str, tuple[str, ...]]] = {
    "domain": {
        "Sourcing": (
            "domain", "se_tags", "reddit_sources", "mining_quota",
            "mining_state", "notes",
        ),
        "Dataset_Items": (
            "item_key", "domain", "system", "user_msg", "assistant_msg",
            "extra_turns", "source", "review_status", "reviewer",
            "reviewed_at", "review_note", "notes",
        ),
    },
    "training": {
        "Exports": (
            "export_id", "domain", "created_at", "n_items",
            "content_hash", "output_file", "hf_dataset_id",
        ),
        "Training_Runs": (
            "run_id", "base_model", "export_id", "hyperparams",
            "checkpoints", "duration", "status", "lora_id", "notes",
        ),
    },
    "bench": {
        "Bench_Results": (
            "result_id", "domain", "model", "score", "n_items",
            "created_at", "notes",
        ),
        "Eval_Items": (
            "item_key", "domain", "prompt", "reference", "response",
            "score", "judge_reasoning", "source", "notes",
        ),
    },
    "workflow": {
        "Pipeline_Status": (
            "domain", "sourced", "trained", "evaluated", "served",
            "updated_at", "notes",
        ),
        "Audit_Log": (
            "event_id", "timestamp", "kind", "domain", "detail",
        ),
    },
}


def provision_doc(client, tables: dict[str, tuple[str, ...]]) -> dict:
    """Ensure every table exists in the doc.

    Returns {table_name: "created" | "exists"}. An existing table is
    never recreated, so re-running is safe.
    """
    existing = client.list_tables()
    report: dict[str, str] = {}
    for name, columns in tables.items():
        if name in existing:
            report[name] = "exists"
        else:
            client.create_table(name, columns)
            report[name] = "created"
    return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev python -m pytest tests/test_grist_llm_schema.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/llm_schema.py tests/test_grist_llm_schema.py
git commit -m "feat(grist): add ailiance-llm 4-doc schema"
```

---

## Task 2: The provisioning script

**Files:**
- Create: `scripts/provision_llm_docs.py`
- Test: `tests/test_provision_llm_docs.py`

The script maps each doc key to its env var, resolves the four doc IDs, and provisions each. `resolve_doc_ids` is the pure, testable part; `main` does the network calls.

- [ ] **Step 1: Write the failing test**

Create `tests/test_provision_llm_docs.py`:

```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import provision_llm_docs as p  # noqa: E402


def test_doc_env_covers_the_four_docs():
    assert set(p.DOC_ENV) == {"domain", "training", "bench", "workflow"}
    assert p.DOC_ENV["domain"] == "GRIST_DOC_LLM_DOMAIN"


def test_resolve_doc_ids_reads_each_env_var(monkeypatch):
    monkeypatch.setattr(p, "load_doc_id",
                        lambda name: f"id-for-{name}")
    ids = p.resolve_doc_ids()
    assert ids == {
        "domain": "id-for-GRIST_DOC_LLM_DOMAIN",
        "training": "id-for-GRIST_DOC_LLM_TRAINING",
        "bench": "id-for-GRIST_DOC_LLM_BENCH",
        "workflow": "id-for-GRIST_DOC_LLM_WORKFLOW",
    }


def test_resolve_doc_ids_exits_when_one_is_missing(monkeypatch):
    monkeypatch.setattr(
        p, "load_doc_id",
        lambda name: None if name == "GRIST_DOC_LLM_BENCH" else "x")
    with pytest.raises(SystemExit):
        p.resolve_doc_ids()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_provision_llm_docs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'provision_llm_docs'`

- [ ] **Step 3: Write the implementation**

Create `scripts/provision_llm_docs.py`:

```python
#!/usr/bin/env python3
"""Provision the table schemas of the four ailiance-llm-* Grist docs.

One-shot, idempotent. Reads four doc IDs from env / grist.env, then
ensures every table of LLM_DOCS exists in its document.

Usage::

    python scripts/provision_llm_docs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_PKG_PARENT = Path(__file__).resolve().parent.parent  # .../mascarade-eval
if str(_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_PKG_PARENT))

from mascarade_eval.grist.client import GristClient, load_doc_id  # noqa: E402
from mascarade_eval.grist.llm_schema import LLM_DOCS, provision_doc  # noqa: E402

DOC_ENV = {
    "domain": "GRIST_DOC_LLM_DOMAIN",
    "training": "GRIST_DOC_LLM_TRAINING",
    "bench": "GRIST_DOC_LLM_BENCH",
    "workflow": "GRIST_DOC_LLM_WORKFLOW",
}


def resolve_doc_ids() -> dict[str, str]:
    """Return {doc_key: doc_id} from env. Exits if any is missing."""
    ids: dict[str, str] = {}
    for key, env_name in DOC_ENV.items():
        doc_id = load_doc_id(env_name)
        if not doc_id:
            sys.exit(f"missing {env_name} (env or grist.env)")
        ids[key] = doc_id
    return ids


def main() -> int:
    doc_ids = resolve_doc_ids()
    for key, tables in LLM_DOCS.items():
        client = GristClient.from_env(doc_ids[key])
        report = provision_doc(client, tables)
        print(f"ailiance-llm-{key} ({doc_ids[key]}): {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev python -m pytest tests/test_provision_llm_docs.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/provision_llm_docs.py tests/test_provision_llm_docs.py
git commit -m "feat(grist): add llm-docs provisioning script"
```

---

## Task 3: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the entire test suite**

Run: `uv run --extra dev python -m pytest -q`
Expected: PASS — all pre-existing grist tests plus the 8 new tests from Tasks 1-2.

- [ ] **Step 2: Confirm the script imports cleanly**

Run: `uv run --extra dev python -c "import sys; sys.path.insert(0, 'scripts'); import provision_llm_docs; print(sorted(provision_llm_docs.DOC_ENV))"`
Expected: `['bench', 'domain', 'training', 'workflow']`

No commit — verification only.

---

## Manual validation (after all tasks, requires network)

Needs the four `GRIST_DOC_LLM_*` IDs configured in `grist.env`:

1. `uv run python scripts/provision_llm_docs.py`
2. Confirm the printed report shows every table `created` on first run.
3. Re-run the script — every table now reports `exists` (idempotency).
4. Open each of the four docs in the Grist UI and confirm the tables
   are present with their columns.

---

## Self-Review

**Spec coverage:**
- Four documents `ailiance-llm-{domain,training,bench,workflow}` — Prerequisites (manual doc creation) + `LLM_DOCS` (Task 1).
- The 8 tables and their columns — `LLM_DOCS` in Task 1 (`Sourcing`, `Dataset_Items`, `Exports`, `Training_Runs`, `Bench_Results`, `Eval_Items`, `Pipeline_Status`, `Audit_Log`).
- `Dataset_Items` carries `review_status` — Task 1 schema + `test_dataset_items_carries_review_columns`.
- Idempotent provisioning — `provision_doc` (Task 1) + `test_provision_doc_is_idempotent` + manual validation step 3.
- Sub-projects 2 (migration), 3 (sync script), 4 (per-domain pages) — explicitly out of scope; this plan only provisions empty schemas.

**Placeholder scan:** No `TBD`/`TODO`. Doc creation is a real manual prerequisite (named explicitly), not a placeholder. Column tuples are concrete.

**Type/name consistency:** `LLM_DOCS` keys (`domain`/`training`/`bench`/`workflow`) match `DOC_ENV` keys (Task 2) and the `provision_doc` calls. `provision_doc(client, tables)` signature is used identically in Task 1 tests and Task 2's `main`. `resolve_doc_ids` returns a `{key: id}` dict consumed by `main` with the same keys.
