# Pipeline_Status Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A sync module + script + CLI subcommand that derives each domain's pipeline status from the domain/training/bench Grist docs plus the gateway model list, and upserts it into the workflow doc's `Pipeline_Status` table.

**Architecture:** A new `mascarade_eval/grist/pipeline_sync.py` holds pure functions (`collect_domains`, `domain_status`), an injectable-transport gateway call (`fetch_served_aliases`), and an orchestrator (`sync_pipeline`) that reads the three source docs via `GristClient`, computes per-domain status, and upserts into `workflow/Pipeline_Status`. A standalone script and a `sync` subcommand in the existing grist CLI are thin shells over `sync_pipeline`.

**Tech Stack:** Python ≥3.12, stdlib (`urllib`, `datetime`, `json`), `uv`, `pytest`. Reuses `GristClient`, `load_doc_id`, `LLM_DOCS`.

**Spec:** `docs/superpowers/specs/2026-05-19-pipeline-sync-design.md`.

---

## Repo and worktree

Work in **`ailiance-bench`**, sub-project `mascarade-eval/`, on `main`.

**Test command:** `uv run --extra dev python -m pytest` (from `mascarade-eval/`). The `--extra dev` flag is REQUIRED.
**Commit format:** subject ≤50 chars incl. prefix; body ≤72; no AI attribution; no underscore in scope.

## Prior context

- `mascarade_eval/grist/client.py` exports `GristClient` (classmethod `from_env(doc_id)`, methods `fetch_records`, `ensure_table`, `add_records`, `upsert_records`) and `load_doc_id(name) -> str | None`.
- `mascarade_eval/grist/llm_schema.py` exports `LLM_DOCS`; `LLM_DOCS["workflow"]["Pipeline_Status"]` is the tuple `("domain", "sourced", "trained", "evaluated", "served", "updated_at", "notes")`.
- `tests/conftest.py` provides a `fake_client` fixture: an in-memory `FakeClient` with `fetch_records`, `ensure_table`, `add_records`, `upsert_records` (upsert matches on a key field and records into `.upserted`), constructible with `tables=` and `records=`.

## File structure

| File | Responsibility | Action |
|------|----------------|--------|
| `mascarade_eval/grist/pipeline_sync.py` | `collect_domains`, `domain_status`, `fetch_served_aliases`, `sync_pipeline` | Create |
| `tests/test_grist_pipeline_sync.py` | Tests for the four functions | Create |
| `scripts/sync_pipeline_status.py` | Standalone entry point | Create |
| `tests/test_sync_pipeline_status.py` | Script env-resolution test | Create |
| `mascarade_eval/grist/cli.py` | Add the `sync` subcommand | Modify |
| `tests/test_grist_cli.py` | Test the `sync` subcommand parses | Modify |

---

## Task 1: The pure status functions

**Files:**
- Create: `mascarade_eval/grist/pipeline_sync.py`
- Test: `tests/test_grist_pipeline_sync.py`

`collect_domains` and `domain_status` are pure. They go in first; the gateway call and orchestrator follow in Tasks 2-3.

- [ ] **Step 1: Write the failing test**

Create `tests/test_grist_pipeline_sync.py`:

```python
from mascarade_eval.grist.pipeline_sync import (
    collect_domains, domain_status,
)


def test_collect_domains_unions_the_three_sources():
    domain_rows = [{"domain": "kicad"}, {"domain": "spice"}]
    training_rows = [{"domain": "kicad"}]
    bench_rows = [{"domain": "stm32"}]
    assert collect_domains(domain_rows, training_rows, bench_rows) == {
        "kicad", "spice", "stm32"}


def test_collect_domains_ignores_rows_without_domain():
    assert collect_domains([{"domain": "kicad"}, {"other": "x"}],
                           [], []) == {"kicad"}


def test_domain_status_all_flags_true():
    row = domain_status("kicad", sourced=True, trained=True,
                        evaluated=True, served=True)
    assert row["domain"] == "kicad"
    assert row["sourced"] is True
    assert row["trained"] is True
    assert row["evaluated"] is True
    assert row["served"] is True
    assert row["notes"] == ""
    assert row["updated_at"].endswith("Z")


def test_domain_status_mixed_flags():
    row = domain_status("spice", sourced=True, trained=False,
                        evaluated=False, served=False)
    assert row["sourced"] is True
    assert row["trained"] is False
    assert set(row) == {"domain", "sourced", "trained", "evaluated",
                        "served", "updated_at", "notes"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_grist_pipeline_sync.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mascarade_eval.grist.pipeline_sync'`

- [ ] **Step 3: Write the implementation**

Create `mascarade_eval/grist/pipeline_sync.py`:

```python
# mascarade_eval/grist/pipeline_sync.py
"""Sync the workflow doc's Pipeline_Status from the other three docs.

collect_domains / domain_status are pure. fetch_served_aliases calls the
gateway (injectable transport). sync_pipeline orchestrates the upsert.
"""
from __future__ import annotations

import datetime
import json
import urllib.request


def collect_domains(domain_rows: list[dict], training_rows: list[dict],
                    bench_rows: list[dict]) -> set[str]:
    """Union of the `domain` values seen across the three docs' rows."""
    domains: set[str] = set()
    for rows in (domain_rows, training_rows, bench_rows):
        for r in rows:
            value = r.get("domain")
            if value:
                domains.add(value)
    return domains


def _utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def domain_status(domain: str, sourced: bool, trained: bool,
                  evaluated: bool, served: bool) -> dict:
    """Build one Pipeline_Status row for a domain."""
    return {
        "domain": domain,
        "sourced": sourced,
        "trained": trained,
        "evaluated": evaluated,
        "served": served,
        "updated_at": _utc_now(),
        "notes": "",
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev python -m pytest tests/test_grist_pipeline_sync.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/pipeline_sync.py tests/test_grist_pipeline_sync.py
git commit -m "feat(grist): add pipeline status pure functions"
```

---

## Task 2: The gateway model-list call

**Files:**
- Modify: `mascarade_eval/grist/pipeline_sync.py`
- Modify: `tests/test_grist_pipeline_sync.py`

`fetch_served_aliases` GETs `<gateway_url>/v1/models` and returns the set of model IDs. The HTTP transport is injectable so tests never hit the network.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_grist_pipeline_sync.py` (add `fetch_served_aliases` to the existing import line from `pipeline_sync`):

```python
def test_fetch_served_aliases_extracts_model_ids():
    def fake_transport(url):
        assert url == "https://gw.example/v1/models"
        return {"data": [{"id": "ailiance-kicad"},
                         {"id": "ailiance-spice"}]}
    aliases = fetch_served_aliases("https://gw.example",
                                   transport=fake_transport)
    assert aliases == {"ailiance-kicad", "ailiance-spice"}


def test_fetch_served_aliases_handles_empty_data():
    aliases = fetch_served_aliases("https://gw.example",
                                   transport=lambda url: {"data": []})
    assert aliases == set()


def test_fetch_served_aliases_strips_trailing_slash():
    seen = {}

    def fake_transport(url):
        seen["url"] = url
        return {"data": []}
    fetch_served_aliases("https://gw.example/", transport=fake_transport)
    assert seen["url"] == "https://gw.example/v1/models"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_grist_pipeline_sync.py -v`
Expected: FAIL — `ImportError: cannot import name 'fetch_served_aliases'`

- [ ] **Step 3: Write the implementation**

Append to `mascarade_eval/grist/pipeline_sync.py`:

```python
def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", "replace")
    return json.loads(raw) if raw else {}


def fetch_served_aliases(gateway_url: str, transport=_http_get_json) -> set[str]:
    """Return the set of model IDs exposed by the gateway /v1/models.

    `transport` is injected for testing; production uses urllib.
    """
    url = f"{gateway_url.rstrip('/')}/v1/models"
    payload = transport(url)
    return {m["id"] for m in payload.get("data", []) if m.get("id")}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev python -m pytest tests/test_grist_pipeline_sync.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/pipeline_sync.py tests/test_grist_pipeline_sync.py
git commit -m "feat(grist): add gateway model-list fetch"
```

---

## Task 3: The sync orchestrator

**Files:**
- Modify: `mascarade_eval/grist/pipeline_sync.py`
- Modify: `tests/test_grist_pipeline_sync.py`

`sync_pipeline` reads the three source docs, computes each domain's status (`served` = `ailiance-<domain>` ∈ the served set), and upserts into `workflow/Pipeline_Status` keyed on `domain`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_grist_pipeline_sync.py` (add `sync_pipeline` to the `pipeline_sync` import line):

```python
def test_sync_pipeline_upserts_per_domain_status(fake_client):
    domain_c = fake_client(records={"Dataset_Items": [
        {"domain": "kicad"}, {"domain": "spice"}]})
    training_c = fake_client(records={"Training_Runs": [
        {"domain": "kicad"}]})
    bench_c = fake_client(records={"Bench_Results": [
        {"domain": "kicad"}]})
    workflow_c = fake_client(tables=[])

    report = sync_pipeline(domain_c, training_c, bench_c, workflow_c,
                           served={"ailiance-kicad"})

    assert set(report) == {"kicad", "spice"}
    assert report["kicad"]["sourced"] is True
    assert report["kicad"]["trained"] is True
    assert report["kicad"]["evaluated"] is True
    assert report["kicad"]["served"] is True
    assert report["spice"]["sourced"] is True
    assert report["spice"]["trained"] is False
    assert report["spice"]["served"] is False
    upserted = workflow_c.upserted["Pipeline_Status"]
    assert {r["domain"] for r in upserted} == {"kicad", "spice"}


def test_sync_pipeline_dry_run_writes_nothing(fake_client):
    domain_c = fake_client(records={"Dataset_Items": [{"domain": "kicad"}]})
    training_c = fake_client(records={"Training_Runs": []})
    bench_c = fake_client(records={"Bench_Results": []})
    workflow_c = fake_client(tables=[])
    report = sync_pipeline(domain_c, training_c, bench_c, workflow_c,
                           served=set(), dry_run=True)
    assert set(report) == {"kicad"}
    assert workflow_c.upserted == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_grist_pipeline_sync.py -v`
Expected: FAIL — `ImportError: cannot import name 'sync_pipeline'`

- [ ] **Step 3: Write the implementation**

3a. In `mascarade_eval/grist/pipeline_sync.py`, add this import line immediately after the existing `import urllib.request` line:

```python
from mascarade_eval.grist.llm_schema import LLM_DOCS
```

3b. Append this function to the end of `mascarade_eval/grist/pipeline_sync.py`:

```python
def sync_pipeline(domain_client, training_client, bench_client,
                  workflow_client, served: set[str],
                  dry_run: bool = False) -> dict:
    """Compute each domain's status and upsert Pipeline_Status.

    `served` is the set of model IDs from the gateway. Returns
    {domain: status_row}.
    """
    domain_rows = domain_client.fetch_records("Dataset_Items")
    training_rows = training_client.fetch_records("Training_Runs")
    bench_rows = bench_client.fetch_records("Bench_Results")

    sourced = {r["domain"] for r in domain_rows if r.get("domain")}
    trained = {r["domain"] for r in training_rows if r.get("domain")}
    evaluated = {r["domain"] for r in bench_rows if r.get("domain")}
    domains = collect_domains(domain_rows, training_rows, bench_rows)

    report: dict[str, dict] = {}
    for domain in sorted(domains):
        report[domain] = domain_status(
            domain,
            sourced=domain in sourced,
            trained=domain in trained,
            evaluated=domain in evaluated,
            served=f"ailiance-{domain}" in served,
        )
    if not dry_run:
        columns = LLM_DOCS["workflow"]["Pipeline_Status"]
        workflow_client.ensure_table("Pipeline_Status", columns)
        workflow_client.upsert_records(
            "Pipeline_Status", list(report.values()), "domain")
    return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev python -m pytest tests/test_grist_pipeline_sync.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/pipeline_sync.py tests/test_grist_pipeline_sync.py
git commit -m "feat(grist): add pipeline sync orchestrator"
```

---

## Task 4: The standalone script

**Files:**
- Create: `scripts/sync_pipeline_status.py`
- Test: `tests/test_sync_pipeline_status.py`

The script resolves the four doc IDs and the gateway URL from env, fetches the served set, runs `sync_pipeline`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_sync_pipeline_status.py`:

```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sync_pipeline_status as s  # noqa: E402


def test_doc_env_covers_the_four_docs():
    assert set(s.DOC_ENV) == {"domain", "training", "bench", "workflow"}
    assert s.DOC_ENV["workflow"] == "GRIST_DOC_LLM_WORKFLOW"


def test_resolve_config_reads_docs_and_gateway(monkeypatch):
    monkeypatch.setattr(s, "load_doc_id", lambda name: f"id-{name}")
    cfg = s.resolve_config()
    assert cfg["doc_ids"]["domain"] == "id-GRIST_DOC_LLM_DOMAIN"
    assert cfg["gateway_url"] == "id-GRIST_GATEWAY_URL"


def test_resolve_config_exits_on_missing(monkeypatch):
    monkeypatch.setattr(
        s, "load_doc_id",
        lambda name: None if name == "GRIST_GATEWAY_URL" else "x")
    with pytest.raises(SystemExit):
        s.resolve_config()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_sync_pipeline_status.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sync_pipeline_status'`

- [ ] **Step 3: Write the implementation**

Create `scripts/sync_pipeline_status.py`:

```python
#!/usr/bin/env python3
"""Sync the workflow doc's Pipeline_Status table.

Reads the domain/training/bench/workflow doc IDs and the gateway URL
from env / grist.env, fetches the gateway model list, and upserts one
Pipeline_Status row per domain.

Usage::

    python scripts/sync_pipeline_status.py --dry-run
    python scripts/sync_pipeline_status.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PKG_PARENT = Path(__file__).resolve().parent.parent
if str(_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_PKG_PARENT))

from mascarade_eval.grist.client import GristClient, load_doc_id  # noqa: E402
from mascarade_eval.grist.pipeline_sync import (  # noqa: E402
    fetch_served_aliases, sync_pipeline,
)

DOC_ENV = {
    "domain": "GRIST_DOC_LLM_DOMAIN",
    "training": "GRIST_DOC_LLM_TRAINING",
    "bench": "GRIST_DOC_LLM_BENCH",
    "workflow": "GRIST_DOC_LLM_WORKFLOW",
}
GATEWAY_ENV = "GRIST_GATEWAY_URL"


def resolve_config() -> dict:
    """Return {doc_ids: {key: id}, gateway_url}. Exits if any missing."""
    doc_ids: dict[str, str] = {}
    for key, env_name in DOC_ENV.items():
        doc_id = load_doc_id(env_name)
        if not doc_id:
            sys.exit(f"missing {env_name} (env or grist.env)")
        doc_ids[key] = doc_id
    gateway_url = load_doc_id(GATEWAY_ENV)
    if not gateway_url:
        sys.exit(f"missing {GATEWAY_ENV} (env or grist.env)")
    return {"doc_ids": doc_ids, "gateway_url": gateway_url}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="compute status, write nothing")
    args = ap.parse_args(argv)

    cfg = resolve_config()
    ids = cfg["doc_ids"]
    served = fetch_served_aliases(cfg["gateway_url"])
    report = sync_pipeline(
        GristClient.from_env(ids["domain"]),
        GristClient.from_env(ids["training"]),
        GristClient.from_env(ids["bench"]),
        GristClient.from_env(ids["workflow"]),
        served=served, dry_run=args.dry_run)
    for domain, row in sorted(report.items()):
        flags = {k: row[k] for k in
                 ("sourced", "trained", "evaluated", "served")}
        print(f"{domain}: {flags}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev python -m pytest tests/test_sync_pipeline_status.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/sync_pipeline_status.py tests/test_sync_pipeline_status.py
git commit -m "feat(grist): add pipeline sync script"
```

---

## Task 5: The `sync` CLI subcommand

**Files:**
- Modify: `mascarade_eval/grist/cli.py`
- Modify: `tests/test_grist_cli.py`

The grist CLI (`build_parser`/`main`) gets a `sync` subcommand. It needs no `--doc` (it reads all four docs via env) — only `--dry-run`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_grist_cli.py`:

```python
def test_parser_sync_accepts_dry_run():
    ns = build_parser().parse_args(["sync", "--dry-run"])
    assert ns.command == "sync"
    assert ns.dry_run is True


def test_parser_sync_without_dry_run():
    ns = build_parser().parse_args(["sync"])
    assert ns.command == "sync"
    assert ns.dry_run is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_grist_cli.py -v`
Expected: FAIL — `sync` is not a valid subcommand (argparse raises `SystemExit`).

- [ ] **Step 3: Add the subcommand**

In `mascarade_eval/grist/cli.py`, `build_parser()` already adds subparsers `ingest`, `export`, `migrate`, `publish`, `schema`. After the `schema` subparser line (`sub.add_parser("schema", ...)`), add:

```python
    p_sync = sub.add_parser("sync", help="sync workflow Pipeline_Status")
    p_sync.add_argument("--dry-run", action="store_true")
```

In `main()`, the `schema` command is handled in its own `if args.command == "schema":` block before the `client = GristClient.from_env(...)` line. Add an analogous block for `sync`, right after the `schema` block:

```python
    if args.command == "sync":
        from .pipeline_sync import fetch_served_aliases, sync_pipeline
        from .client import load_doc_id
        env = {"domain": "GRIST_DOC_LLM_DOMAIN",
               "training": "GRIST_DOC_LLM_TRAINING",
               "bench": "GRIST_DOC_LLM_BENCH",
               "workflow": "GRIST_DOC_LLM_WORKFLOW"}
        ids = {}
        for key, name in env.items():
            doc_id = load_doc_id(name)
            if not doc_id:
                sys.exit(f"missing {name} (env or grist.env)")
            ids[key] = doc_id
        gateway = load_doc_id("GRIST_GATEWAY_URL")
        if not gateway:
            sys.exit("missing GRIST_GATEWAY_URL (env or grist.env)")
        served = fetch_served_aliases(gateway)
        report = sync_pipeline(
            GristClient.from_env(ids["domain"]),
            GristClient.from_env(ids["training"]),
            GristClient.from_env(ids["bench"]),
            GristClient.from_env(ids["workflow"]),
            served=served, dry_run=args.dry_run)
        print(f"sync: {len(report)} domains")
        return 0
```

(`sys` and `GristClient` are already imported in `cli.py`; `load_doc_id` is imported locally in the block to keep the change self-contained.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev python -m pytest tests/test_grist_cli.py -v`
Expected: PASS (the two new tests plus the pre-existing CLI tests).

- [ ] **Step 5: Run the full suite**

Run: `uv run --extra dev python -m pytest -q`
Expected: PASS — all tests green.

- [ ] **Step 6: Commit**

```bash
git add mascarade_eval/grist/cli.py tests/test_grist_cli.py
git commit -m "feat(grist): add sync subcommand to cli"
```

---

## Manual validation (after all tasks, requires network)

Needs `GRIST_DOC_LLM_{DOMAIN,TRAINING,BENCH,WORKFLOW}` and `GRIST_GATEWAY_URL` in `grist.env`, and the four docs provisioned + migrated:

1. `uv run python scripts/sync_pipeline_status.py --dry-run` — prints per-domain flags, writes nothing.
2. `uv run python scripts/sync_pipeline_status.py` — confirm `Pipeline_Status` in the workflow doc has one row per domain.
3. Re-run — confirm rows are updated, not duplicated (upsert on `domain`).
4. `uv run python -m mascarade_eval.grist.cli sync --dry-run` — same result via the CLI.

---

## Self-Review

**Spec coverage:**
- `collect_domains` / `domain_status` pure functions — Task 1.
- `fetch_served_aliases` with injectable transport — Task 2.
- `sync_pipeline` orchestrator, upsert on `domain`, `dry_run` — Task 3.
- `served` = `ailiance-<domain>` ∈ gateway set — Task 3 (`f"ailiance-{domain}" in served`).
- Standalone script — Task 4.
- `sync` CLI subcommand — Task 5.
- Logic in the module, entries are thin shells — Tasks 4-5 both call `sync_pipeline`/`fetch_served_aliases`.
- `Audit_Log`, cron, doc creation, migration — out of scope per the spec.

**Placeholder scan:** No `TBD`/`TODO` markers. Every code step shows complete code.

**Type/name consistency:** `sync_pipeline(domain_client, training_client, bench_client, workflow_client, served, dry_run)` — same signature in Task 3's test, Task 4's script, Task 5's CLI block. `fetch_served_aliases(gateway_url, transport)` consistent across Tasks 2, 4, 5. `domain_status` returns the 7 keys matching `LLM_DOCS["workflow"]["Pipeline_Status"]`. The table name `"Pipeline_Status"` and source table names `"Dataset_Items"`/`"Training_Runs"`/`"Bench_Results"` are consistent with the migration spec's targets.
