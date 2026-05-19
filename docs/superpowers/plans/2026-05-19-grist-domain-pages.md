# Grist Per-Domain Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A module + script that reconciles the dataset domain list against the `DOMAINS` constant and best-effort creates one Grist page per domain, plus an operator runbook for pages the API cannot create.

**Architecture:** A new `mascarade_eval/grist/domain_pages.py` holds two pure functions (`reconcile_domains`, `page_plan`) and one best-effort Grist call (`create_domain_page`, injectable transport). A standalone script reads `Dataset_Items`, reconciles against `mascarade_eval.DOMAINS`, warns about orphan domains, and runs page creation. A runbook documents the manual fallback.

**Tech Stack:** Python ≥3.12, stdlib, `uv`, `pytest`. Reuses `GristClient`, `load_doc_id`, `mascarade_eval.DOMAINS`.

**Spec:** `docs/superpowers/specs/2026-05-19-grist-domain-pages-design.md`.

---

## Repo and worktree

Work in **`ailiance-bench`**, sub-project `mascarade-eval/`, on `main`.

**Test command:** `uv run --extra dev python -m pytest` (from `mascarade-eval/`). The `--extra dev` flag is REQUIRED.
**Commit format:** subject ≤50 chars incl. prefix; body ≤72; no AI attribution; no underscore in scope.

## Prior context

- `mascarade_eval/__init__.py` exports `DOMAINS` — the tuple `("kicad", "spice", "stm32", "emc", "embedded", "platformio", "freecad", "dsp", "iot", "power")`.
- `mascarade_eval/grist/client.py` exports `GristClient` (classmethod `from_env(doc_id)`, methods incl. `fetch_records`, plus the private `_api(method, path, body)` used for raw calls) and `load_doc_id(name) -> str | None`.
- `tests/conftest.py` provides a `fake_client` fixture — an in-memory `FakeClient` constructible with `tables=` / `records=`.
- Standalone scripts in `scripts/` insert the package parent into `sys.path`.

## Grist page-creation reality

Grist creates pages/view-sections through its `/apply` user-actions endpoint, not a clean REST verb. `create_domain_page` therefore POSTs a `CreateViewSection` user action and treats a non-2xx / unexpected response as `api_unsupported` rather than crashing — the runbook covers those. The page-creation path is best-effort by design; the reconciliation logic is the solid, fully-tested core.

## File structure

| File | Responsibility | Action |
|------|----------------|--------|
| `mascarade_eval/grist/domain_pages.py` | `reconcile_domains`, `page_plan`, `create_domain_page` | Create |
| `tests/test_grist_domain_pages.py` | Tests for the three functions | Create |
| `scripts/build_domain_pages.py` | Standalone entry point | Create |
| `tests/test_build_domain_pages.py` | Script doc-resolution test | Create |
| `mascarade_eval/grist/domain-pages-runbook.md` | Operator runbook (manual fallback) | Create |

---

## Task 1: The reconciliation function

**Files:**
- Create: `mascarade_eval/grist/domain_pages.py`
- Test: `tests/test_grist_domain_pages.py`

`reconcile_domains` is pure and is the solid core of the sub-project.

- [ ] **Step 1: Write the failing test**

Create `tests/test_grist_domain_pages.py`:

```python
from mascarade_eval.grist.domain_pages import reconcile_domains


def test_reconcile_all_present():
    rows = [{"domain": "kicad"}, {"domain": "spice"}]
    out = reconcile_domains(rows, ("kicad", "spice"))
    assert out["expected"] == ["kicad", "spice"]
    assert out["present"] == ["kicad", "spice"]
    assert out["orphans"] == []
    assert out["missing"] == []


def test_reconcile_flags_orphan_domains():
    rows = [{"domain": "kicad"}, {"domain": "weird"}]
    out = reconcile_domains(rows, ("kicad", "spice"))
    assert out["orphans"] == ["weird"]


def test_reconcile_flags_missing_domains():
    rows = [{"domain": "kicad"}]
    out = reconcile_domains(rows, ("kicad", "spice"))
    assert out["missing"] == ["spice"]
    assert out["present"] == ["kicad"]


def test_reconcile_ignores_rows_without_domain():
    rows = [{"domain": "kicad"}, {"other": "x"}, {"domain": ""}]
    out = reconcile_domains(rows, ("kicad",))
    assert out["orphans"] == []
    assert out["present"] == ["kicad"]


def test_reconcile_lists_are_sorted():
    rows = [{"domain": "spice"}, {"domain": "kicad"}]
    out = reconcile_domains(rows, ("spice", "kicad"))
    assert out["expected"] == ["kicad", "spice"]
    assert out["present"] == ["kicad", "spice"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_grist_domain_pages.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mascarade_eval.grist.domain_pages'`

- [ ] **Step 3: Write the implementation**

Create `mascarade_eval/grist/domain_pages.py`:

```python
# mascarade_eval/grist/domain_pages.py
"""Per-domain pages for the ailiance-llm-domain Grist doc.

reconcile_domains / page_plan are pure. create_domain_page is a
best-effort Grist /apply call (injectable transport for tests).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request


def reconcile_domains(dataset_items_rows: list[dict],
                      known_domains: tuple[str, ...]) -> dict:
    """Compare the domains seen in Dataset_Items to the known set.

    Returns sorted lists: expected (the known set), present (known
    domains with rows), orphans (domains in data but not known),
    missing (known domains with no rows).
    """
    seen = {r["domain"] for r in dataset_items_rows if r.get("domain")}
    known = set(known_domains)
    return {
        "expected": sorted(known),
        "present": sorted(seen & known),
        "orphans": sorted(seen - known),
        "missing": sorted(known - seen),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev python -m pytest tests/test_grist_domain_pages.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/domain_pages.py tests/test_grist_domain_pages.py
git commit -m "feat(grist): add domain reconciliation function"
```

---

## Task 2: The page plan function

**Files:**
- Modify: `mascarade_eval/grist/domain_pages.py`
- Modify: `tests/test_grist_domain_pages.py`

`page_plan` is a pure description of the page wanted for one domain.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_grist_domain_pages.py` (extend the import to add `page_plan`):

```python
def test_page_plan_describes_the_domain_page():
    from mascarade_eval.grist.domain_pages import page_plan
    plan = page_plan("kicad")
    assert plan["page_name"] == "Domain: kicad"
    assert plan["widgets"] == ["Sourcing", "Dataset_Items"]
    assert plan["filter"] == {"column": "domain", "value": "kicad"}


def test_page_plan_distinct_per_domain():
    from mascarade_eval.grist.domain_pages import page_plan
    assert page_plan("spice")["page_name"] != page_plan("kicad")["page_name"]
    assert page_plan("spice")["filter"]["value"] == "spice"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_grist_domain_pages.py -v`
Expected: FAIL — `ImportError: cannot import name 'page_plan'`

- [ ] **Step 3: Write the implementation**

Append to `mascarade_eval/grist/domain_pages.py`:

```python
def page_plan(domain: str) -> dict:
    """Describe the Grist page wanted for one domain."""
    return {
        "page_name": f"Domain: {domain}",
        "widgets": ["Sourcing", "Dataset_Items"],
        "filter": {"column": "domain", "value": domain},
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev python -m pytest tests/test_grist_domain_pages.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/domain_pages.py tests/test_grist_domain_pages.py
git commit -m "feat(grist): add per-domain page plan"
```

---

## Task 3: The best-effort page creation

**Files:**
- Modify: `mascarade_eval/grist/domain_pages.py`
- Modify: `tests/test_grist_domain_pages.py`

`create_domain_page` attempts the Grist `/apply` user-action. The `apply` call is reached through an injectable `applier` callable: `applier(actions: list) -> None`, raising on failure. Production wires it to `GristClient`; tests inject a fake.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_grist_domain_pages.py`:

```python
def test_create_domain_page_reports_created_on_success():
    from mascarade_eval.grist.domain_pages import create_domain_page
    calls = []

    def applier(actions):
        calls.append(actions)

    out = create_domain_page("kicad", applier=applier)
    assert out == {"domain": "kicad", "status": "created"}
    assert len(calls) == 1


def test_create_domain_page_reports_unsupported_on_failure():
    from mascarade_eval.grist.domain_pages import create_domain_page

    def applier(actions):
        raise RuntimeError("Grist /apply rejected the action")

    out = create_domain_page("spice", applier=applier)
    assert out == {"domain": "spice", "status": "api_unsupported"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_grist_domain_pages.py -v`
Expected: FAIL — `ImportError: cannot import name 'create_domain_page'`

- [ ] **Step 3: Write the implementation**

Append to `mascarade_eval/grist/domain_pages.py`:

```python
def _grist_applier(doc_id: str, key: str):
    """Build an applier that POSTs user-actions to a Grist doc."""
    def applier(actions: list) -> None:
        url = (f"https://grist.saillant.cc/api/docs/{doc_id}/apply")
        data = json.dumps(actions).encode()
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    return applier


def create_domain_page(domain: str, applier) -> dict:
    """Best-effort: create the domain's Grist page via a user action.

    `applier` applies a list of Grist user-actions and raises on
    failure. Returns {"domain", "status"} where status is "created"
    or "api_unsupported".
    """
    plan = page_plan(domain)
    actions = [["AddView", plan["page_name"], "raw"]]
    try:
        applier(actions)
        return {"domain": domain, "status": "created"}
    except Exception:
        return {"domain": domain, "status": "api_unsupported"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev python -m pytest tests/test_grist_domain_pages.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add mascarade_eval/grist/domain_pages.py tests/test_grist_domain_pages.py
git commit -m "feat(grist): add best-effort page creation"
```

---

## Task 4: The standalone script

**Files:**
- Create: `scripts/build_domain_pages.py`
- Test: `tests/test_build_domain_pages.py`

The script resolves the domain doc ID, reads `Dataset_Items`, reconciles, warns on orphans, and runs page creation.

- [ ] **Step 1: Write the failing test**

Create `tests/test_build_domain_pages.py`:

```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_domain_pages as b  # noqa: E402


def test_resolve_doc_id_returns_the_env_value(monkeypatch):
    monkeypatch.setattr(b, "load_doc_id", lambda name: f"id-{name}")
    assert b.resolve_doc_id() == "id-GRIST_DOC_LLM_DOMAIN"


def test_resolve_doc_id_exits_when_unset(monkeypatch):
    monkeypatch.setattr(b, "load_doc_id", lambda name: None)
    with pytest.raises(SystemExit):
        b.resolve_doc_id()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_build_domain_pages.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'build_domain_pages'`

- [ ] **Step 3: Write the implementation**

Create `scripts/build_domain_pages.py`:

```python
#!/usr/bin/env python3
"""Build one Grist page per domain in the ailiance-llm-domain doc.

Reconciles the domains found in Dataset_Items against the DOMAINS
constant (warns about orphans), then best-effort creates a page per
domain. Pages the Grist API cannot create are listed for the runbook.

Usage::

    python scripts/build_domain_pages.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_PKG_PARENT = Path(__file__).resolve().parent.parent
if str(_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_PKG_PARENT))

from mascarade_eval import DOMAINS  # noqa: E402
from mascarade_eval.grist.client import (  # noqa: E402
    GristClient, load_doc_id, load_grist_key,
)
from mascarade_eval.grist.domain_pages import (  # noqa: E402
    create_domain_page, reconcile_domains,
)
from mascarade_eval.grist.domain_pages import _grist_applier  # noqa: E402

DOMAIN_DOC_ENV = "GRIST_DOC_LLM_DOMAIN"


def resolve_doc_id() -> str:
    """Return the domain doc ID from env / grist.env. Exits if unset."""
    doc_id = load_doc_id(DOMAIN_DOC_ENV)
    if not doc_id:
        sys.exit(f"missing {DOMAIN_DOC_ENV} (env or grist.env)")
    return doc_id


def main(argv: list[str] | None = None) -> int:
    doc_id = resolve_doc_id()
    client = GristClient.from_env(doc_id)
    rows = client.fetch_records("Dataset_Items")

    report = reconcile_domains(rows, DOMAINS)
    if report["orphans"]:
        print(f"[warn] orphan domains in data, not in DOMAINS: "
              f"{report['orphans']}", file=sys.stderr)
    if report["missing"]:
        print(f"[info] known domains with no rows yet: "
              f"{report['missing']}")

    applier = _grist_applier(doc_id, load_grist_key())
    created, manual = [], []
    for domain in report["expected"]:
        result = create_domain_page(domain, applier=applier)
        (created if result["status"] == "created" else manual).append(
            domain)
    print(f"pages created via API: {created}")
    print(f"pages to create by hand (see runbook): {manual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev python -m pytest tests/test_build_domain_pages.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Verify the script imports cleanly**

Run: `uv run --extra dev python -c "import sys; sys.path.insert(0,'scripts'); import build_domain_pages; print(build_domain_pages.DOMAIN_DOC_ENV)"`
Expected: `GRIST_DOC_LLM_DOMAIN`

(Note: `load_grist_key` must exist in `mascarade_eval/grist/client.py` — it does, it is the function the other scripts use to read `GRIST_API_KEY`. If the import fails, check the exact exported name in `client.py` and adjust the import line.)

- [ ] **Step 6: Commit**

```bash
git add scripts/build_domain_pages.py tests/test_build_domain_pages.py
git commit -m "feat(grist): add domain pages build script"
```

---

## Task 5: The operator runbook

**Files:**
- Create: `mascarade_eval/grist/domain-pages-runbook.md`

- [ ] **Step 1: Write the runbook**

Create `mascarade_eval/grist/domain-pages-runbook.md` with this content:

```markdown
# Runbook — per-domain pages in ailiance-llm-domain

`scripts/build_domain_pages.py` best-effort creates one Grist page per
domain. Any domain it reports under "pages to create by hand" needs the
manual steps below — Grist's API cannot always create pages.

## Per domain (manual fallback)

In the Grist UI, open the `ailiance-llm-domain` document, then for each
domain listed by the script:

1. Add a new page named `Domain: <domain>` (e.g. `Domain: kicad`).
2. On that page, add a table widget for `Sourcing`.
3. Add a second table widget for `Dataset_Items`.
4. On each widget, add a filter: column `domain` equals `<domain>`.
5. Save.

## Checking orphans

If the script prints `orphan domains in data, not in DOMAINS`, a domain
appears in `Dataset_Items` that is not in the `DOMAINS` constant
(`mascarade_eval/__init__.py`). Decide per case: either add the domain
to `DOMAINS` (if legitimate) or correct the offending rows.
```

- [ ] **Step 2: Run the full suite**

Run: `uv run --extra dev python -m pytest -q`
Expected: PASS — all tests green.

- [ ] **Step 3: Commit**

```bash
git add mascarade_eval/grist/domain-pages-runbook.md
git commit -m "docs(grist): add domain pages runbook"
```

---

## Manual validation (after all tasks, requires network)

Needs `GRIST_DOC_LLM_DOMAIN` and `GRIST_API_KEY` in `grist.env`, the
domain doc provisioned and migrated:

1. `uv run python scripts/build_domain_pages.py` — read the orphan
   warning (if any) and the created / to-do-by-hand split.
2. For every domain under "to create by hand", follow
   `domain-pages-runbook.md`.
3. Open the `ailiance-llm-domain` doc and confirm each domain has a
   page with the two filtered widgets.

---

## Self-Review

**Spec coverage:**
- `reconcile_domains` (expected/present/orphans/missing) — Task 1.
- `page_plan` — Task 2.
- `create_domain_page` best-effort, injectable transport — Task 3.
- Standalone script: resolve doc, read `Dataset_Items`, reconcile, warn
  on orphans, run page creation, report — Task 4.
- Runbook for the manual fallback — Task 5.
- Domains from the `DOMAINS` constant with orphan alerting — Task 1
  (`reconcile_domains`) consumed by Task 4 (`main` passes `DOMAINS`,
  prints `orphans`).
- Pure functions tested directly; `create_domain_page` tested with an
  injected applier — Tasks 1-3 tests.

**Placeholder scan:** No `TBD`/`TODO`. Task 4 Step 5 flags a real
import-name dependency (`load_grist_key`) with a concrete check — a
verification instruction, not a placeholder.

**Type/name consistency:** `reconcile_domains(rows, known_domains)`
returns the 4-key dict used by `main` in Task 4. `page_plan(domain)`
returns `{page_name, widgets, filter}` consumed by `create_domain_page`
in Task 3. `create_domain_page(domain, applier)` signature is identical
in Task 3's tests and Task 4's `main`. `_grist_applier(doc_id, key)`
returns the `applier` callable that `create_domain_page` expects.
`DOMAIN_DOC_ENV` is consistent across Task 4's `resolve_doc_id`, its
test, and the verification step.
