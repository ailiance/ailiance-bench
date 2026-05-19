# Bench Doc Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `bench` doc's two consolidated tables with one table per legacy source so the migration copies all 856 rows losslessly.

**Architecture:** Three code tasks update `llm_schema.py` (the bench schema), `grist_migrate.py` (the migration map), and `pipeline_sync.py` + `__init__.py` (the `evaluated`-flag derivation, now reading two bench tables). A fourth ops step (not a code task) re-provisions the bench doc and runs the migration.

**Tech Stack:** Python ≥3.12, `uv`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-05-19-bench-doc-redesign-design.md`.

---

## Repo

Work in `/Users/electron/ailiance-bench/mascarade-eval`, branch `main`, commit directly. Test command: `uv run --extra dev python -m pytest` (from `mascarade-eval/`). Commits: subject ≤50 chars incl. prefix, no underscore in scope, no AI attribution.

---

## Task 1: Redefine the bench schema

**Files:**
- Modify: `mascarade_eval/grist/llm_schema.py`
- Modify: `tests/test_grist_llm_schema.py`

- [ ] **Step 1: Update the test**

In `tests/test_grist_llm_schema.py`, the test `test_each_doc_declares_its_tables` asserts `set(LLM_DOCS["bench"]) == {"Bench_Results", "Eval_Items"}`. Change that line to:

```python
    assert set(LLM_DOCS["bench"]) == {"Heldout_Items", "Mascarade_Eval",
                                      "Mascarade_Eval_Items",
                                      "Bench_31_domains"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_grist_llm_schema.py -v`
Expected: FAIL on `test_each_doc_declares_its_tables`.

- [ ] **Step 3: Rewrite the bench schema**

In `mascarade_eval/grist/llm_schema.py`, replace the entire `"bench": { ... }` entry of `LLM_DOCS` with:

```python
    "bench": {
        "Heldout_Items": (
            "item_key", "domain", "prompt", "reference", "source",
            "dataset", "review_status", "reviewer", "reviewed_at",
            "review_note",
        ),
        "Mascarade_Eval": (
            "run_domain", "run_id", "domain", "n", "base_score",
            "lora_score", "delta", "verdict", "routed_to", "scorer",
            "status", "updated_at",
        ),
        "Mascarade_Eval_Items": (
            "run_item", "run_id", "domain", "item_idx", "question",
            "reference", "base_answer", "base_score", "base_scorer",
            "base_judge_raw", "lora_answer", "lora_score", "lora_scorer",
            "lora_judge_raw", "delta", "updated_at", "review_status",
            "reviewer", "reviewed_at", "review_note",
        ),
        "Bench_31_domains": (
            "model", "domain", "ppl", "stderr_ppl", "status", "samples",
            "date", "source", "task_score", "task_metric", "judge_score",
            "judge_rationale", "judge_independence", "host", "runtime_s",
            "tokens_per_s", "run_id", "validator_score",
            "validator_image_digest", "review_status", "reviewer",
            "reviewed_at", "review_note",
        ),
    },
```

Leave the `domain`, `training`, `workflow` entries of `LLM_DOCS` unchanged.

- [ ] **Step 4: Run the full suite**

Run: `uv run --extra dev python -m pytest -q`
Expected: PASS. If another test in `test_grist_llm_schema.py` references `Bench_Results`/`Eval_Items` (e.g. a provision test), update it minimally to the new table set.

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/llm_schema.py tests/test_grist_llm_schema.py
git commit -m "feat(grist): bench schema one table per source"
```

---

## Task 2: Update the migration map

**Files:**
- Modify: `mascarade_eval/grist/grist_migrate.py`
- Modify: `tests/test_grist_migrate_engine.py` (only if a test pins the old `tgt_table` names)

- [ ] **Step 1: Rewrite MIGRATION_MAP**

In `mascarade_eval/grist/grist_migrate.py`, replace `MIGRATION_MAP` with (each entry's `tgt_table` now equals its `src_table` — a same-name copy into the `bench` doc):

```python
MIGRATION_MAP: list[dict] = [
    {"src_doc": "heldout_old", "src_table": "Heldout_Items",
     "tgt_doc": "bench", "tgt_table": "Heldout_Items", "rename": {}},
    {"src_doc": "mascarade_old", "src_table": "Mascarade_Eval",
     "tgt_doc": "bench", "tgt_table": "Mascarade_Eval", "rename": {}},
    {"src_doc": "mascarade_old", "src_table": "Mascarade_Eval_Items",
     "tgt_doc": "bench", "tgt_table": "Mascarade_Eval_Items",
     "rename": {}},
    {"src_doc": "mascarade_old", "src_table": "Bench_31_domains",
     "tgt_doc": "bench", "tgt_table": "Bench_31_domains", "rename": {}},
]
```

Update the comment block above `MIGRATION_MAP` if it names the old `Eval_Items`/`Bench_Results` targets.

- [ ] **Step 2: Run the full suite**

Run: `uv run --extra dev python -m pytest -q`
Expected: PASS. `test_migration_map_targets_known_docs` checks `tgt_doc` ∈ a valid set — `bench` is in it, so it still passes. If any test pins the old `tgt_table` values, update it to the new same-name targets.

- [ ] **Step 3: Commit**

```bash
git add mascarade_eval/grist/grist_migrate.py tests/test_grist_migrate_engine.py
git commit -m "feat(grist): migrate bench tables one to one"
```

(If `test_grist_migrate_engine.py` needed no change, commit only `grist_migrate.py`.)

---

## Task 3: Repoint pipeline_sync and drop EVAL_TABLE

**Files:**
- Modify: `mascarade_eval/grist/pipeline_sync.py`
- Modify: `mascarade_eval/grist/__init__.py`
- Modify: `tests/test_grist_pipeline_sync.py`

`sync_pipeline` currently reads `bench_client.fetch_records("Bench_Results")` and derives `evaluated` from rows' `domain`. `Bench_Results` no longer exists. The bench doc now has `Mascarade_Eval` and `Bench_31_domains`, both with a `domain` column — `evaluated` = a domain appears in either.

- [ ] **Step 1: Update the test**

In `tests/test_grist_pipeline_sync.py`, the sync tests seed a `fake_client` with a `Bench_Results` table. Find `test_sync_pipeline_upserts_per_domain_status` and `test_sync_pipeline_dry_run_writes_nothing`. In each, the `bench_c` fake client is constructed with `records={"Bench_Results": [...]}`. Change `"Bench_Results"` to `"Mascarade_Eval"` in both (keep the row contents — rows with a `domain` key are all that matters). The assertions on `report[...]["evaluated"]` stay valid: in `test_sync_pipeline_upserts_per_domain_status`, `kicad` has a bench row so `evaluated` is True; `spice` has none so False.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_grist_pipeline_sync.py -v`
Expected: FAIL — `sync_pipeline` still reads `Bench_Results`, the fake client now has `Mascarade_Eval`, so `evaluated` comes out wrong.

- [ ] **Step 3: Repoint sync_pipeline**

In `mascarade_eval/grist/pipeline_sync.py`, `sync_pipeline` currently has:

```python
    bench_rows = bench_client.fetch_records("Bench_Results")
```

Replace that single line with two fetches unioned:

```python
    bench_rows = (bench_client.fetch_records("Mascarade_Eval")
                  + bench_client.fetch_records("Bench_31_domains"))
```

The rest of `sync_pipeline` (`evaluated = {r["domain"] for r in bench_rows if r.get("domain")}`) is unchanged — it already derives the set from `bench_rows`.

- [ ] **Step 4: Drop the dead constant**

In `mascarade_eval/grist/__init__.py`, delete the line `EVAL_TABLE = "Eval_Items"` — it is no longer referenced anywhere. Leave `TRAINING_TABLE` and every other constant unchanged.

- [ ] **Step 5: Run the full suite**

Run: `uv run --extra dev python -m pytest -q`
Expected: PASS — all tests green.

- [ ] **Step 6: Commit**

```bash
git add mascarade_eval/grist/pipeline_sync.py mascarade_eval/grist/__init__.py tests/test_grist_pipeline_sync.py
git commit -m "feat(grist): derive evaluated from bench tables"
```

---

## Ops step (after Tasks 1-3, not a code task — the controller runs this)

1. Delete the two wrongly-provisioned empty tables `Bench_Results` and `Eval_Items` from the `ailiance-llm-bench` Grist doc via the API.
2. Re-run `uv run --extra dev python scripts/provision_llm_docs.py` — the bench doc gets the 4 correct tables.
3. `uv run --extra dev python scripts/migrate_grist_docs.py --dry-run` — confirm `dropped_columns` is empty for all 4.
4. `uv run --extra dev python scripts/migrate_grist_docs.py` — confirm `verified: True` for all 4 (856 rows total).

---

## Self-Review

**Spec coverage:** bench schema → Task 1; MIGRATION_MAP → Task 2; pipeline_sync `evaluated` + `EVAL_TABLE` removal → Task 3; re-provision + migrate → Ops step. **Placeholder scan:** none. **Type consistency:** the 4 bench table names (`Heldout_Items`, `Mascarade_Eval`, `Mascarade_Eval_Items`, `Bench_31_domains`) are identical across `LLM_DOCS["bench"]` (Task 1), `MIGRATION_MAP` `tgt_table` (Task 2), and the `pipeline_sync` fetches (Task 3).
