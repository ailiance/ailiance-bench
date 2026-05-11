# KiCad-SCH Foundation — Implementation Plan

> **REQUIRED SUB-SKILL:** Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan.

**Date:** 2026-05-11
**Author:** Clément Saillant (LElectron Rare)
**Scope:** Foundation layer of the kicad-sch gap design spec (`docs/superpowers/specs/2026-05-11-kicad-sch-gap-design.md`, commit `e58731a`).
**Blocks:** Track E (eval N3), Track C (LoRA training), Track D (hybrid DSL→compiler).

## Goal

Land the bedrock artefacts required before any training, inference, or eval run can start:

1. OSF-style pre-registration (H1/H2/H3, stopping rules, seed list) — locked BEFORE training.
2. Risk register (table from spec §Risks).
3. NDJSON append-only audit-log writer + sha256 manifest + verification (EU AI Act Annex IV §7).
4. Dataset manifest CSV writer (EU AI Act Annex IV §2.b lineage) for D1/D2/D3.
5. Test suite for both Python modules.
6. Directory scaffolding.

Everything else (scrapers, training, eval) depends on these existing and being trusted.

## Architecture

```
~/electron-bench/                                # docs repo (electron-rare/electron-bench)
  preregistrations/
    2026-05-11-kicad-sch-prereg.md               # H1/H2/H3 lock
  docs/superpowers/
    plans/2026-05-11-kicad-sch-foundation.md     # THIS FILE
    specs/2026-05-11-kicad-sch-gap-design.md     # source spec (exists)
    specs/risks/
      2026-05-11-kicad-sch-risks.md              # risk register

~/eu-kiki/                                       # code repo
  scripts/kicad_sch/
    __init__.py
    audit_log.py                                 # AuditLogger + sha256_manifest + verify
    manifest.py                                  # DatasetManifest CSV writer
  tests/kicad_sch/
    __init__.py
    test_audit_log.py
    test_manifest.py
```

No new third-party deps — stdlib only (`json`, `hashlib`, `csv`, `pathlib`, `typing`).

## Tech Stack

- Python 3.14 (`uv run python -m pytest`)
- stdlib `json`, `hashlib`, `csv`, `pathlib`, `typing`
- pytest with `tmp_path` fixture
- Markdown for docs
- Git commit policy: subject ≤50 chars, body lines ≤72, no underscore in scope, no AI attribution lines; pre-commit hooks must pass (do not bypass)
- Author: `electron-rare <108685187+electron-rare@users.noreply.github.com>`

## File Structure

| Path | Type | Lines (target) |
|---|---|---:|
| `~/electron-bench/preregistrations/2026-05-11-kicad-sch-prereg.md` | doc | ~80 |
| `~/electron-bench/docs/superpowers/specs/risks/2026-05-11-kicad-sch-risks.md` | doc | ~40 |
| `~/eu-kiki/scripts/kicad_sch/__init__.py` | code | 1 |
| `~/eu-kiki/scripts/kicad_sch/audit_log.py` | code | ~70 |
| `~/eu-kiki/scripts/kicad_sch/manifest.py` | code | ~70 |
| `~/eu-kiki/tests/kicad_sch/__init__.py` | code | 1 |
| `~/eu-kiki/tests/kicad_sch/test_audit_log.py` | test | ~70 |
| `~/eu-kiki/tests/kicad_sch/test_manifest.py` | test | ~60 |

## Tasks

Each task is 2–5 min. TDD where applicable: write failing test → run (red) → implement → run (green) → commit.

---

### Task 1 — Scaffold directories on Studio

**Goal:** Create empty parent directories so subsequent `Write` operations succeed.

```bash
ssh studio 'mkdir -p \
  ~/electron-bench/preregistrations \
  ~/electron-bench/docs/superpowers/specs/risks \
  ~/eu-kiki/scripts/kicad_sch \
  ~/eu-kiki/tests/kicad_sch'
```

Create empty package markers:

```bash
ssh studio 'touch \
  ~/eu-kiki/scripts/kicad_sch/__init__.py \
  ~/eu-kiki/tests/kicad_sch/__init__.py'
```

Verify:

```bash
ssh studio 'ls -la ~/eu-kiki/scripts/kicad_sch ~/eu-kiki/tests/kicad_sch \
  ~/electron-bench/preregistrations ~/electron-bench/docs/superpowers/specs/risks'
```

No commit yet — scaffold only.

---

### Task 2 — Pre-registration doc (electron-bench)

**Goal:** Lock H1/H2/H3, stopping rules, and the 5-seed list verbatim from the spec §Pre-registration. Must be committed BEFORE any training run starts.

**File:** `~/electron-bench/preregistrations/2026-05-11-kicad-sch-prereg.md`

**Content (complete):**

````markdown
# KiCad-SCH Generation Gap — Pre-registration

**Date locked:** 2026-05-11
**Author:** Clément Saillant (LElectron Rare)
**Spec:** `docs/superpowers/specs/2026-05-11-kicad-sch-gap-design.md`
**Status:** Locked BEFORE any Track C training run or Track D inference run.

This pre-registration follows OSF conventions. Any deviation from the
hypotheses, stopping rules, or seed list below must be documented as an
amendment commit referencing this file.

## Hypotheses

### H1 (primary) — LoRA dataset ordering

LoRA-C-D3-qwen36 > LoRA-C-D1-qwen36 > LoRA-C-D2-qwen36 on N3 composite.

- Test: one-sided paired t-test per pair.
- Multiple-comparison correction: Bonferroni, alpha = 0.0167 (3 comparisons).
- Effect-size threshold: Cohen d >= 0.5.

### H2 — DSL pipeline ordering

Pipeline-D-skidl > Pipeline-D-tscircuit on `parse_ok` rate.

- Test: one-sided z-test on proportions, alpha = 0.05.

### H3 — Track C vs Track D semantic equivalence

max(LoRA-C N3 composite) >= max(Pipeline-D N3 composite) on the
`sem_equiv` axis.

- Test: 5-seed bootstrap CI 95% non-overlap.

## Stopping rules

- If after 5 seeds the composite CI 95% overlaps 0 for any D1-LoRA cell,
  that cell is dropped from H1 and reported as inconclusive.
- If `dsl_parse_ok` < 0.2 for any Track-D pipeline, that pipeline is
  dropped from H2.

## Seed list (locked)

```
[42, 137, 1024, 8675309, 31415]
```

Every cell (Track C LoRA, Track D pipeline) is evaluated at all 5 seeds.
Bootstrap CI 95% is reported on the composite mean.

## Reproducibility envelope

- All configs YAML versioned in `KIKI-Mac_tunner/configs/`.
- `requirements.lock` per run (uv).
- KiCad CLI pinned: `kicad-cli 10.0.2`.
- Docker images pinned by sha256 digest (iact-bench v0.2.0).
- NDJSON audit logs append-only, sha256-signed manifest at run end.

## Amendments

(none yet)
````

**Commit (electron-bench):**

```
docs(prereg): lock H1/H2/H3 kicad-sch hypotheses

Pre-registration for kicad-sch gap design spec. Locks the three
hypotheses, Bonferroni correction, stopping rules, and 5-seed list
([42, 137, 1024, 8675309, 31415]) before any Track C training run
or Track D inference run begins.

Source: docs/superpowers/specs/2026-05-11-kicad-sch-gap-design.md
```

---

### Task 3 — Risk register doc (electron-bench)

**Goal:** Persist the risk table from spec §Risks as a standalone artefact.

**File:** `~/electron-bench/docs/superpowers/specs/risks/2026-05-11-kicad-sch-risks.md`

**Content (complete):**

````markdown
# KiCad-SCH Generation Gap — Risk Register

**Date:** 2026-05-11
**Spec:** `docs/superpowers/specs/2026-05-11-kicad-sch-gap-design.md`

| Risk | Probability | Mitigation |
|---|---|---|
| D1 scrape < 1k after license + dedup filter | Medium | Augment via D2 synth weighted-up; if D1 < 1k, ablation reports "D1 insufficient" |
| Ctx fenetre saturee (lib_symbols inline) | High | Strip lib_symbols pre-training, lib_id reference resolution at load time |
| Track-D compilers crash on LLM DSL | High | Capture rc, mark pipeline failed:syntax, separate `dsl_parse_ok` metric |
| sem_equiv graph iso too slow on large refs | Low | Limit to refs with <=15 components; skip if larger |
| License contamination in D1 | Medium | `licensecheck` + manual review top-100 repos before inclusion; reject if no LICENSE file |
| Watermark `;;` interferes with kicad-cli parse | Low | Smoke test before activation; fallback to no watermark |
| Studio compute contention (F1 still running) | Medium | Schedule Track C training after F1 completes (~07:30 CEST) |

## Tracking

Risks are revisited at the end of each phase (0/1/2/3/4/5/6) listed in
the spec §"Implementation order". Probability updates and observed
materialisations are appended below as dated entries.

## Materialisations

(none yet)
````

**Commit (electron-bench):**

```
docs(risks): persist kicad-sch risk register

Extracts the 7-row risk table from the kicad-sch gap design spec
into a standalone document so it can be updated independently as
risks materialise during phases 0-6.
```

---

### Task 4 — Failing tests for AuditLogger (eu-kiki)

**Goal:** Write the test file first; run; confirm import error / red.

**File:** `~/eu-kiki/tests/kicad_sch/test_audit_log.py`

**Content (complete):**

```python
"""Tests for the NDJSON audit-log writer (EU AI Act Annex IV §7)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.kicad_sch.audit_log import AuditLogger, sha256_manifest, verify


def test_audit_logger_appends_ndjson(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.ndjson"
    logger = AuditLogger(log_path)
    logger.log("generation", model_id="apertus", prompt_hash="abc123", seed=42)
    logger.log("eval", validator="kicad-erc", exit_code=0, axis_scores={"parse_ok": 1})
    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 2
    e1 = json.loads(lines[0])
    assert e1["event_type"] == "generation"
    assert e1["seed"] == 42
    assert e1["model_id"] == "apertus"
    e2 = json.loads(lines[1])
    assert e2["event_type"] == "eval"
    assert e2["axis_scores"] == {"parse_ok": 1}


def test_audit_logger_appends_across_instances(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.ndjson"
    AuditLogger(log_path).log("a", x=1)
    AuditLogger(log_path).log("b", y=2)
    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["event_type"] == "a"
    assert json.loads(lines[1])["event_type"] == "b"


def test_sha256_manifest_deterministic(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.ndjson"
    log_path.write_text('{"a": 1}\n{"b": 2}\n')
    h1 = sha256_manifest(log_path)
    h2 = sha256_manifest(log_path)
    assert h1 == h2
    assert len(h1) == 64
    assert all(c in "0123456789abcdef" for c in h1)


def test_verify_detects_tampering(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.ndjson"
    log_path.write_text('{"a": 1}\n')
    sha = sha256_manifest(log_path)
    log_path.write_text('{"a": 2}\n')
    assert verify(log_path, sha) is False


def test_verify_passes_untampered(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.ndjson"
    log_path.write_text('{"a": 1}\n')
    sha = sha256_manifest(log_path)
    assert verify(log_path, sha) is True
```

**Run (expect red):**

```bash
ssh studio 'cd ~/eu-kiki && uv run python -m pytest tests/kicad_sch/test_audit_log.py -x'
```

Expected: `ModuleNotFoundError: No module named 'scripts.kicad_sch.audit_log'`.

No commit yet — implementation follows in Task 5.

---

### Task 5 — Implement AuditLogger (eu-kiki)

**Goal:** Make the audit-log tests pass.

**File:** `~/eu-kiki/scripts/kicad_sch/audit_log.py`

**Content (complete):**

```python
"""NDJSON append-only audit-log writer for EU AI Act Annex IV §7.

Each line of the log is a JSON object with at least an `event_type`
field plus arbitrary structured fields. The log is sha256-signed at
the end of a run via `sha256_manifest`; tampering can be detected
later via `verify`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class AuditLogger:
    """Append-only NDJSON audit logger.

    Multiple instances can target the same path — each `log()` call
    opens the file in append mode, writes one JSON line, and closes.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event_type: str, **fields: Any) -> None:
        record: dict[str, Any] = {"event_type": event_type, **fields}
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def sha256_manifest(log_path: Path) -> str:
    """Return the hex sha256 of the log file's bytes."""
    h = hashlib.sha256()
    with Path(log_path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(log_path: Path, expected_sha: str) -> bool:
    """Return True iff the file's current sha256 matches `expected_sha`."""
    return sha256_manifest(log_path) == expected_sha
```

**Run (expect green):**

```bash
ssh studio 'cd ~/eu-kiki && uv run python -m pytest tests/kicad_sch/test_audit_log.py -x'
```

**Commit (eu-kiki):**

```
feat(kicad-sch): NDJSON audit logger with sha256 sign

Implements AuditLogger (append-only NDJSON), sha256_manifest, and
verify per spec EU AI Act Annex IV §7. Backs all kicad-sch Track
C/D runs with a tamper-evident audit trail. 5 tests, stdlib only.
```

---

### Task 6 — Failing tests for DatasetManifest (eu-kiki)

**Goal:** Write the manifest test file; run; confirm red.

**File:** `~/eu-kiki/tests/kicad_sch/test_manifest.py`

**Content (complete):**

```python
"""Tests for the dataset manifest CSV writer (EU AI Act Annex IV §2.b)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.kicad_sch.manifest import DatasetManifest


HEADER = (
    "source_type,source_url,commit_sha,license_spdx,dedup_hash,"
    "file_size_bytes,kicad_version_before,kicad_version_after"
)


def test_manifest_writes_csv_with_header(tmp_path: Path) -> None:
    path = tmp_path / "manifest.csv"
    m = DatasetManifest(path, split="D1")
    m.add(
        source_type="scraped",
        source_url="https://github.com/foo/bar",
        commit_sha="abc",
        license_spdx="MIT",
        dedup_hash="def",
        file_size_bytes=1024,
        kicad_version_before="v6",
        kicad_version_after="v10",
    )
    m.write()
    content = path.read_text()
    assert HEADER in content
    assert "scraped,https://github.com/foo/bar,abc,MIT,def,1024,v6,v10" in content


def test_manifest_multiple_rows(tmp_path: Path) -> None:
    path = tmp_path / "manifest.csv"
    m = DatasetManifest(path, split="D2")
    for i in range(3):
        m.add(
            source_type="synth",
            source_url=f"seed={i}",
            commit_sha="zzz",
            license_spdx="CC0-1.0",
            dedup_hash=f"hash{i}",
            file_size_bytes=2048,
            kicad_version_before="v10",
            kicad_version_after="v10",
        )
    m.write()
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 4  # header + 3 rows
    assert lines[0] == HEADER


def test_manifest_rejects_invalid_split(tmp_path: Path) -> None:
    with pytest.raises((ValueError, TypeError)):
        DatasetManifest(tmp_path / "m.csv", split="D9")  # type: ignore[arg-type]
```

**Run (expect red):**

```bash
ssh studio 'cd ~/eu-kiki && uv run python -m pytest tests/kicad_sch/test_manifest.py -x'
```

Expected: `ModuleNotFoundError: No module named 'scripts.kicad_sch.manifest'`.

No commit yet — implementation follows in Task 7.

---

### Task 7 — Implement DatasetManifest (eu-kiki)

**Goal:** Make the manifest tests pass.

**File:** `~/eu-kiki/scripts/kicad_sch/manifest.py`

**Content (complete):**

```python
"""Dataset manifest CSV writer for EU AI Act Annex IV §2.b lineage.

Each row records lineage for a single `.kicad_sch` training sample.
Columns match the spec §Datasets:

    source_type, source_url, commit_sha, license_spdx, dedup_hash,
    file_size_bytes, kicad_version_before, kicad_version_after
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Literal

Split = Literal["D1", "D2", "D3"]

FIELDNAMES: tuple[str, ...] = (
    "source_type",
    "source_url",
    "commit_sha",
    "license_spdx",
    "dedup_hash",
    "file_size_bytes",
    "kicad_version_before",
    "kicad_version_after",
)


class DatasetManifest:
    """Accumulate manifest rows in memory, then write once via `write()`."""

    def __init__(self, path: Path, split: Split) -> None:
        if split not in ("D1", "D2", "D3"):
            raise ValueError(f"split must be one of D1/D2/D3, got {split!r}")
        self.path = Path(path)
        self.split = split
        self.rows: list[dict[str, object]] = []

    def add(
        self,
        *,
        source_type: str,
        source_url: str,
        commit_sha: str,
        license_spdx: str,
        dedup_hash: str,
        file_size_bytes: int,
        kicad_version_before: str,
        kicad_version_after: str,
    ) -> None:
        self.rows.append(
            {
                "source_type": source_type,
                "source_url": source_url,
                "commit_sha": commit_sha,
                "license_spdx": license_spdx,
                "dedup_hash": dedup_hash,
                "file_size_bytes": file_size_bytes,
                "kicad_version_before": kicad_version_before,
                "kicad_version_after": kicad_version_after,
            }
        )

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(FIELDNAMES))
            writer.writeheader()
            writer.writerows(self.rows)
```

**Run (expect green):**

```bash
ssh studio 'cd ~/eu-kiki && uv run python -m pytest tests/kicad_sch/test_manifest.py -x'
```

**Commit (eu-kiki):**

```
feat(kicad-sch): dataset manifest CSV writer

Implements DatasetManifest for D1/D2/D3 splits, columns per spec
EU AI Act Annex IV §2.b lineage requirement. Validates split enum,
batches rows, writes once via DictWriter. 3 tests, stdlib only.
```

---

### Task 8 — Full suite green + push both repos

**Goal:** Final verification, then push to remotes.

**Run:**

```bash
ssh studio 'cd ~/eu-kiki && uv run python -m pytest tests/kicad_sch/ -v'
```

Expected: 8 tests pass (5 audit_log + 3 manifest).

**Push electron-bench:**

```bash
ssh studio 'cd ~/electron-bench && git log --oneline -5 && git push origin main'
```

**Push eu-kiki:**

```bash
ssh studio 'cd ~/eu-kiki && git log --oneline -5 && git push origin main'
```

If pre-commit hooks reject any commit (subject >50, body line >72,
underscore in scope, AI attribution): fix the offending message,
re-stage, create a fresh commit, re-push. Do not bypass hooks.

---

## Verification checklist

After all tasks:

- [ ] `~/electron-bench/preregistrations/2026-05-11-kicad-sch-prereg.md` exists, contains H1/H2/H3, the 5-seed list, and stopping rules verbatim from the spec.
- [ ] `~/electron-bench/docs/superpowers/specs/risks/2026-05-11-kicad-sch-risks.md` exists, 7-row table matches spec §Risks.
- [ ] `~/eu-kiki/scripts/kicad_sch/audit_log.py` exposes `AuditLogger`, `sha256_manifest`, `verify`.
- [ ] `~/eu-kiki/scripts/kicad_sch/manifest.py` exposes `DatasetManifest` with `add()` + `write()`, split is `Literal["D1","D2","D3"]`.
- [ ] `uv run python -m pytest tests/kicad_sch/` reports 8 passed.
- [ ] Both repos pushed; pre-commit hooks pass cleanly; no `Co-Authored-By` lines in any commit.
- [ ] Author on every commit: `electron-rare <108685187+electron-rare@users.noreply.github.com>`.

## Out of scope (for Foundation)

- D1 scraper / D2 synth generator / D3 mixer (Phase 1 in spec).
- LoRA training (Phase 2).
- Track D pipelines (Phase 3).
- N3 5-axis eval (Phase 4).
- `bench_comparison.py --metric-axes` extension (Phase 5).
- Model cards + audit-trail signing automation (Phase 6).

These are picked up by the Track C / Track D / Track E sub-project plans.
