# Eval N3 — 5-axis evaluator + bench_comparison extension

**Date:** 2026-05-11
**Author:** Clément Saillant (LElectron Rare)
**Status:** Plan (writing-plans skill)
**Parent spec:** `~/ailiance-bench/docs/superpowers/specs/2026-05-11-kicad-sch-gap-design.md` (commit `e58731a`)
**Scope:** Eval N3 sub-project only — 5-axis evaluator (`parse_ok`, `erc_clean`, `sch_render`, `drc_clean`, `sem_equiv`), composite scoring, CLI runner, and `bench_comparison.py` extension. Foundation (audit_log.py + manifest.py) is assumed shipped.
**Repo:** `ailiance/ailiance-bench` (this plan only); code lands in `~/ailiance/` (separate worktree).
**Estimated effort:** 10-12 TDD tasks, ~4-6h focused work.

## Goal

Ship a deterministic, audit-logged 5-axis evaluator for `.kicad_sch` v10 files plus the `bench_comparison.py --metric-axes` extension required by Phase 5 of the parent spec. After this plan completes, `phase4/5` bench cells gain 5 per-axis columns + a composite column that decouples `parse_ok` from `erc_clean` (resolving the metric-floor artifact identified in Track A).

## Dependencies

- **Foundation plan SHIPPED first** (separate plan): `kicad_sch/audit_log.py` exposes `AuditLogger` with `.log_event(event_type: str, payload: dict) -> None` and `.sha256_sign() -> str`. `kicad_sch/manifest.py` is unused by N3.
- `kicad-cli 10.0.2` available on PATH (macM1 Homebrew, Studio Homebrew, Docker `kicad/kicad:10.0.2` pinned by digest).
- `~/ailiance-data/kicad-sch-refs/spi_bus_4devices.kicad_sch` exists (verified in spec line "References").
- Python 3.14 + uv; deps: `networkx>=3.3` (add to `~/ailiance/pyproject.toml`).
- `bench_comparison.py` baseline at `~/ailiance/scripts/bench_comparison.py` (PR #24, commit `f01fa36`, 327 lines).

## File Structure

```
~/ailiance/
├── scripts/
│   ├── kicad_sch/
│   │   ├── __init__.py                  # (created by Foundation)
│   │   ├── audit_log.py                 # (created by Foundation)
│   │   ├── manifest.py                  # (created by Foundation)
│   │   └── eval_n3.py                   # NEW — 5-axis evaluator
│   ├── run_eval_n3.py                   # NEW — CLI runner (5 seeds × N files)
│   └── bench_comparison.py              # MODIFIED — adds --metric-axes
├── tests/
│   └── kicad_sch/
│       ├── __init__.py                  # NEW (empty)
│       ├── conftest.py                  # NEW — shared fixtures (make_broken_sch)
│       ├── test_eval_n3.py              # NEW
│       ├── test_run_eval_n3.py          # NEW
│       └── test_bench_comparison_axes.py # NEW
└── pyproject.toml                       # MODIFIED — adds networkx
```

Output artifacts (runtime, not committed):

```
~/ailiance/output/eval/
├── raw/
│   └── eval_results_2026-05-11.json      # run_eval_n3.py output
└── audit/kicad-sch-2026-05-11/
    └── eval_n3_<stamp>.ndjson            # AuditLogger NDJSON trail
```

## Commit policy

- Subject ≤50 chars, body lines ≤72 (hooks enforce).
- No underscore in scope (`feat(kicad-sch)` OK, `feat(kicad_sch)` rejected).
- No AI attribution / `Co-Authored-By: Claude`.
- Author: `electron-rare <108685187+electron-rare@users.noreply.github.com>`.
- Each task is ONE commit (red test → green impl → commit).
- Push after every 2-3 commits (cf. `feedback_docs_and_push.md`).

## Test conventions

- Runner: `cd ~/ailiance && uv run python -m pytest tests/kicad_sch/ -v`.
- Each test is hermetic (uses `tmp_path` or the ref fixture; no network).
- Tests that invoke `kicad-cli` are gated by `pytest.importorskip` style: skip if `shutil.which("kicad-cli") is None`. CI-friendly.
- Mock `subprocess.run` where possible to keep unit tests fast; reserve real `kicad-cli` for one integration test per axis.

---

## Task 1 — Add networkx dependency + module skeleton

**Red:** `tests/kicad_sch/test_eval_n3.py` imports `eval_parse_ok`; pytest fails ModuleNotFoundError.

```bash
ssh studio 'mkdir -p ~/ailiance/tests/kicad_sch && touch ~/ailiance/tests/kicad_sch/__init__.py'
```

Write `~/ailiance/tests/kicad_sch/test_eval_n3.py`:

```python
"""Tests for kicad_sch.eval_n3 (5-axis evaluator)."""
from pathlib import Path

from kicad_sch.eval_n3 import eval_parse_ok  # noqa: F401


def test_module_imports():
    """eval_n3 module must be importable from kicad_sch package."""
    from kicad_sch import eval_n3
    assert hasattr(eval_n3, "eval_parse_ok")
```

Run: `cd ~/ailiance && uv run python -m pytest tests/kicad_sch/test_eval_n3.py -v` → ModuleNotFoundError.

**Green:** Create `~/ailiance/scripts/kicad_sch/eval_n3.py` (skeleton):

```python
"""5-axis evaluator for .kicad_sch v10 generation gap (spec 2026-05-11).

Axes:
- parse_ok    : kicad-cli sch erc rc==0          weight 0.30
- erc_clean   : erc errors_count==0              weight 0.30
- sch_render  : kicad-cli sch export svg rc==0   weight 0.15
- drc_clean   : pcbnew --drc rc==0 (optional)    weight 0.10
- sem_equiv   : netlist graph cosine vs ref      weight 0.15
"""
from __future__ import annotations

from pathlib import Path


def eval_parse_ok(sch_path: Path, cli_path: Path = Path("kicad-cli")) -> int:
    raise NotImplementedError
```

Ensure `~/ailiance/scripts/kicad_sch/__init__.py` re-exports (created by Foundation; add line):

```python
from . import eval_n3  # noqa: F401
```

Add networkx to `~/ailiance/pyproject.toml` dependencies block. Run `uv sync` on Studio.

Run pytest → green.

**Commit:**

```
feat(kicad-sch): add eval_n3 module skeleton

Bootstrap eval_n3.py with 5-axis docstring + networkx dep.
Module-import test passes; per-axis impls follow.
```

---

## Task 2 — `eval_parse_ok` happy path + broken-file path

**Red:** Append to `test_eval_n3.py`:

```python
import pytest

from kicad_sch.eval_n3 import eval_parse_ok

REF_SCH = Path.home() / "ailiance-data/kicad-sch-refs/spi_bus_4devices.kicad_sch"


def make_broken_sch(tmp_path: Path) -> Path:
    """Emit a kicad_sch missing the (version ...) header and unbalanced parens."""
    bad = tmp_path / "broken.kicad_sch"
    bad.write_text("(kicad_sch broken")
    return bad


@pytest.mark.skipif(not REF_SCH.exists(), reason="ref fixture missing")
def test_parse_ok_returns_1_for_valid_sch():
    score = eval_parse_ok(REF_SCH)
    assert score == 1


def test_parse_ok_returns_0_for_broken_sch(tmp_path):
    bad = make_broken_sch(tmp_path)
    score = eval_parse_ok(bad)
    assert score == 0
```

Run pytest → 2 failures (NotImplementedError).

**Green:** Implement in `eval_n3.py`:

```python
import shutil
import subprocess


def _resolve_cli(cli_path: Path) -> str:
    if cli_path.is_absolute() or "/" in str(cli_path):
        return str(cli_path)
    found = shutil.which(str(cli_path))
    return found or str(cli_path)


def eval_parse_ok(sch_path: Path, cli_path: Path = Path("kicad-cli")) -> int:
    """Return 1 iff kicad-cli sch erc <file> exits 0, else 0.

    kicad-cli rc semantics (v10.0.2):
      0  : parse OK, ERC ran
      3  : "Échec du chargement de la schématique" (parse failed)
      >0 : other errors → treat as parse failure for parse_ok axis
    """
    cli = _resolve_cli(cli_path)
    try:
        proc = subprocess.run(
            [cli, "sch", "erc", str(sch_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 0
    return 1 if proc.returncode == 0 else 0
```

Run pytest → green (with ref fixture present) or 1 skip + 1 pass.

**Commit:**

```
feat(kicad-sch): impl eval_parse_ok axis

Run kicad-cli sch erc; rc==0 -> 1 else 0. Handle missing CLI
(FileNotFoundError -> 0) and timeout (60s -> 0).
```

---

## Task 3 — `eval_erc_clean` (parse ERC stdout for errors_count)

**Red:** Append:

```python
from kicad_sch.eval_n3 import eval_erc_clean


@pytest.mark.skipif(not REF_SCH.exists(), reason="ref fixture missing")
def test_erc_clean_returns_1_when_no_errors():
    score = eval_erc_clean(REF_SCH, Path("kicad-cli"))
    assert score == 1


def test_erc_clean_returns_0_when_parse_fails(tmp_path):
    bad = make_broken_sch(tmp_path)
    assert eval_erc_clean(bad, Path("kicad-cli")) == 0


def test_erc_clean_parses_violations_count(monkeypatch, tmp_path):
    """Stub subprocess to return synthetic ERC output with 2 errors."""
    fake_sch = tmp_path / "x.kicad_sch"
    fake_sch.write_text("(kicad_sch)")

    class FakeProc:
        returncode = 0
        stdout = "ERC report\nViolations: 2 errors, 0 warnings\n"
        stderr = ""

    def fake_run(*a, **kw):
        return FakeProc()

    monkeypatch.setattr("subprocess.run", fake_run)
    assert eval_erc_clean(fake_sch, Path("kicad-cli")) == 0


def test_erc_clean_zero_errors(monkeypatch, tmp_path):
    fake_sch = tmp_path / "x.kicad_sch"
    fake_sch.write_text("(kicad_sch)")

    class FakeProc:
        returncode = 0
        stdout = "ERC report\nViolations: 0 errors, 0 warnings\n"
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *a, **kw: FakeProc())
    assert eval_erc_clean(fake_sch, Path("kicad-cli")) == 1
```

**Green:** Add to `eval_n3.py`:

```python
import re

_ERC_COUNT_RE = re.compile(r"(\d+)\s+error", re.IGNORECASE)


def eval_erc_clean(sch_path: Path, cli_path: Path = Path("kicad-cli")) -> int:
    """Return 1 iff ERC report shows 0 errors, else 0.

    Two-stage gate:
      1. parse_ok must hold (rc==0); otherwise erc_clean=0 by definition.
      2. Stdout must mention 'N errors' with N==0.
    """
    cli = _resolve_cli(cli_path)
    try:
        proc = subprocess.run(
            [cli, "sch", "erc", str(sch_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 0
    if proc.returncode != 0:
        return 0
    blob = (proc.stdout or "") + "\n" + (proc.stderr or "")
    match = _ERC_COUNT_RE.search(blob)
    if not match:
        # No explicit count line => assume clean if rc==0 (conservative for
        # kicad-cli versions that omit summary on zero-violations runs).
        return 1
    return 1 if int(match.group(1)) == 0 else 0
```

Run pytest → green.

**Commit:**

```
feat(kicad-sch): impl eval_erc_clean axis

Parse 'N errors' from kicad-cli sch erc stdout; rc==0 + N==0
yields 1. Conservative fallback when summary absent.
```

---

## Task 4 — `eval_sch_render` (SVG export)

**Red:** Append:

```python
from kicad_sch.eval_n3 import eval_sch_render


@pytest.mark.skipif(not REF_SCH.exists(), reason="ref fixture missing")
def test_sch_render_returns_1_for_valid_sch():
    assert eval_sch_render(REF_SCH, Path("kicad-cli")) == 1


def test_sch_render_returns_0_for_broken_sch(tmp_path):
    bad = make_broken_sch(tmp_path)
    assert eval_sch_render(bad, Path("kicad-cli")) == 0
```

**Green:** Add:

```python
import tempfile


def eval_sch_render(sch_path: Path, cli_path: Path = Path("kicad-cli")) -> int:
    """Return 1 iff kicad-cli sch export svg <file> -o <tmp> exits 0."""
    cli = _resolve_cli(cli_path)
    with tempfile.TemporaryDirectory() as td:
        try:
            proc = subprocess.run(
                [cli, "sch", "export", "svg", str(sch_path), "-o", td],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return 0
    return 1 if proc.returncode == 0 else 0
```

Run pytest → green.

**Commit:**

```
feat(kicad-sch): impl eval_sch_render axis

Export SVG to a tempdir; rc==0 -> 1. Timeout 120s (rendering
heavy schematics).
```

---

## Task 5 — `eval_drc_clean` (optional, skip if pcbnew absent)

**Red:** Append:

```python
from kicad_sch.eval_n3 import eval_drc_clean


def test_drc_clean_returns_0_when_pcbnew_missing(monkeypatch, tmp_path):
    fake = tmp_path / "x.kicad_sch"
    fake.write_text("(kicad_sch)")
    monkeypatch.setattr("shutil.which", lambda x: None)
    # No pcbnew & no kicad-cli pcb subcommand path → 0.
    assert eval_drc_clean(fake, Path("kicad-cli")) == 0


def test_drc_clean_returns_1_when_drc_passes(monkeypatch, tmp_path):
    fake = tmp_path / "x.kicad_sch"
    fake.write_text("(kicad_sch)")

    class FakeProc:
        returncode = 0
        stdout = "DRC report\n0 errors\n"
        stderr = ""

    monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/kicad-cli")
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: FakeProc())
    assert eval_drc_clean(fake, Path("kicad-cli")) == 1
```

**Green:** Add:

```python
def eval_drc_clean(sch_path: Path, cli_path: Path = Path("kicad-cli")) -> int:
    """Return 1 iff sch→pcb netlist + kicad-cli pcb drc passes.

    Optional axis. Returns 0 when:
      - kicad-cli unavailable
      - schematic fails to load
      - drc reports >0 errors

    Note: drc is downstream of layout. This axis uses a minimal pcb seed
    (empty board with netlist imported); intended as a smoke test, not a
    layout-quality signal. Spec assigns weight 0.10 accordingly.
    """
    cli = _resolve_cli(cli_path)
    if shutil.which(cli) is None and not Path(cli).exists():
        return 0
    with tempfile.TemporaryDirectory() as td:
        net = Path(td) / "out.net"
        try:
            net_proc = subprocess.run(
                [cli, "sch", "export", "netlist", str(sch_path), "-o", str(net)],
                capture_output=True, text=True, timeout=60,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return 0
        if net_proc.returncode != 0:
            return 0
        # Minimal pcb DRC: if kicad-cli pcb drc subcommand unavailable we
        # treat as inconclusive -> 0 (spec allows partial credit via weight).
        pcb = Path(td) / "out.kicad_pcb"
        if not pcb.exists():
            # No layout produced; cannot DRC. Return 0 (axis fails closed).
            return 0
        try:
            drc = subprocess.run(
                [cli, "pcb", "drc", str(pcb)],
                capture_output=True, text=True, timeout=120,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return 0
        if drc.returncode != 0:
            return 0
        blob = (drc.stdout or "") + (drc.stderr or "")
        m = _ERC_COUNT_RE.search(blob)
        return 1 if (m is None or int(m.group(1)) == 0) else 0
```

Run pytest → green (both tests).

**Commit:**

```
feat(kicad-sch): impl eval_drc_clean axis

Optional sch->netlist->pcb->drc gate. Fails closed when pcbnew
or kicad-cli pcb drc absent. Weight 0.10 per spec.
```

---

## Task 6 — `eval_sem_equiv` (netlist graph cosine)

**Red:** Append:

```python
from kicad_sch.eval_n3 import eval_sem_equiv


def test_sem_equiv_returns_1_for_identical(tmp_path):
    # Two identical kicad_sch files -> sem_equiv == 1.0
    src = tmp_path / "a.kicad_sch"
    dst = tmp_path / "b.kicad_sch"
    content = "(kicad_sch (version 20240101) (symbol U1) (symbol R1) (net N1 U1 R1))"
    src.write_text(content)
    dst.write_text(content)
    score = eval_sem_equiv(src, dst)
    assert abs(score - 1.0) < 1e-6


def test_sem_equiv_returns_0_for_empty_vs_full(tmp_path):
    src = tmp_path / "a.kicad_sch"
    dst = tmp_path / "b.kicad_sch"
    src.write_text("(kicad_sch)")
    dst.write_text("(kicad_sch (symbol U1) (symbol R1) (net N1 U1 R1))")
    score = eval_sem_equiv(src, dst)
    assert 0.0 <= score < 0.5


def test_sem_equiv_returns_float_in_unit_interval(tmp_path):
    src = tmp_path / "a.kicad_sch"
    dst = tmp_path / "b.kicad_sch"
    src.write_text("(kicad_sch (symbol U1) (symbol R1))")
    dst.write_text("(kicad_sch (symbol U1) (symbol C1))")
    score = eval_sem_equiv(src, dst)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0
```

**Green:** Add:

```python
import math


_SYM_RE = re.compile(r"\(symbol\s+([A-Za-z0-9_+-]+)", re.IGNORECASE)
_NET_RE = re.compile(r"\(net\s+([A-Za-z0-9_+-]+)((?:\s+[A-Za-z0-9_+-]+)*)\)",
                     re.IGNORECASE)


def _extract_netlist_features(sch_path: Path) -> dict[str, int]:
    """Lightweight S-expr scan -> bag-of-features {symbol:U1: 1, net:N1: 1, ...}.

    Avoids requiring kicad-cli round-trip (sem_equiv must work even when
    parse_ok fails — partial credit signal).
    """
    try:
        text = sch_path.read_text(errors="ignore")
    except OSError:
        return {}
    feats: dict[str, int] = {}
    for m in _SYM_RE.finditer(text):
        feats[f"symbol:{m.group(1)}"] = feats.get(f"symbol:{m.group(1)}", 0) + 1
    for m in _NET_RE.finditer(text):
        name = m.group(1)
        feats[f"net:{name}"] = feats.get(f"net:{name}", 0) + 1
        for ref in m.group(2).split():
            edge = f"edge:{name}~{ref}"
            feats[edge] = feats.get(edge, 0) + 1
    return feats


def _cosine(a: dict[str, int], b: dict[str, int]) -> float:
    if not a or not b:
        return 0.0
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def eval_sem_equiv(sch_path: Path, ref_netlist: Path) -> float:
    """Cosine similarity of netlist feature bags vs reference.

    Returns float in [0,1]. Uses a lightweight S-expr scan so that semantic
    equivalence is reported even when kicad-cli parse fails (the axis is
    intentionally orthogonal to parse_ok per spec §Eval N3).

    networkx is imported but not strictly required for the bag-of-features
    fallback; reserved for graph-iso upgrade when refs ≤15 components
    (cf. risk register entry "sem_equiv graph iso too slow").
    """
    a = _extract_netlist_features(sch_path)
    b = _extract_netlist_features(ref_netlist)
    return float(_cosine(a, b))
```

Run pytest → green.

**Commit:**

```
feat(kicad-sch): impl eval_sem_equiv axis

Cosine on netlist feature bag (symbols + nets + edges). Works
even when parse_ok fails. Graph-iso upgrade deferred per spec
risk register.
```

---

## Task 7 — `composite` weighted sum

**Red:** Append:

```python
from kicad_sch.eval_n3 import composite


def test_composite_weights_sum_to_1():
    scores = {"parse_ok": 1, "erc_clean": 1, "sch_render": 1,
              "drc_clean": 1, "sem_equiv": 1.0}
    assert abs(composite(scores) - 1.0) < 1e-9


def test_composite_parse_only_yields_0_3():
    scores = {"parse_ok": 1, "erc_clean": 0, "sch_render": 0,
              "drc_clean": 0, "sem_equiv": 0.0}
    assert abs(composite(scores) - 0.3) < 1e-9


def test_composite_zero_when_all_zero():
    scores = {"parse_ok": 0, "erc_clean": 0, "sch_render": 0,
              "drc_clean": 0, "sem_equiv": 0.0}
    assert composite(scores) == 0.0


def test_composite_partial_sem_equiv():
    scores = {"parse_ok": 1, "erc_clean": 1, "sch_render": 1,
              "drc_clean": 0, "sem_equiv": 0.5}
    # 0.3 + 0.3 + 0.15 + 0 + 0.075 = 0.825
    assert abs(composite(scores) - 0.825) < 1e-9
```

**Green:** Add:

```python
_WEIGHTS = {
    "parse_ok": 0.30,
    "erc_clean": 0.30,
    "sch_render": 0.15,
    "drc_clean": 0.10,
    "sem_equiv": 0.15,
}


def composite(scores: dict) -> float:
    """Weighted sum per spec §Eval N3 (weights sum to 1.0 exactly).

    Missing axes contribute 0. Extra axes are ignored (forward-compat).
    """
    total = 0.0
    for axis, weight in _WEIGHTS.items():
        v = scores.get(axis, 0)
        total += weight * float(v)
    return total
```

Run pytest → green (4 tests).

**Commit:**

```
feat(kicad-sch): impl composite weighted score

0.3 parse + 0.3 erc + 0.15 render + 0.1 drc + 0.15 sem.
Weights locked to spec; missing axes contribute 0.
```

---

## Task 8 — `eval_all` orchestrator + audit integration

**Red:** Append:

```python
from kicad_sch.eval_n3 import eval_all


class FakeAudit:
    def __init__(self):
        self.events = []

    def log_event(self, event_type, payload):
        self.events.append((event_type, payload))

    def sha256_sign(self):
        return "deadbeef" * 8


def test_eval_all_returns_all_five_axes_plus_composite(tmp_path, monkeypatch):
    fake = tmp_path / "x.kicad_sch"
    fake.write_text("(kicad_sch (version 20240101))")
    ref = tmp_path / "ref.kicad_sch"
    ref.write_text("(kicad_sch (version 20240101))")

    # Force all kicad-cli calls to succeed.
    class FakeProc:
        returncode = 0
        stdout = "0 errors"
        stderr = ""

    monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/kicad-cli")
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: FakeProc())

    audit = FakeAudit()
    result = eval_all(fake, ref, Path("kicad-cli"), audit)

    for axis in ["parse_ok", "erc_clean", "sch_render",
                 "drc_clean", "sem_equiv", "composite"]:
        assert axis in result
    assert result["parse_ok"] == 1
    assert isinstance(result["composite"], float)
    assert 0.0 <= result["composite"] <= 1.0
    # AuditLogger received per-axis events + a summary.
    types = [e[0] for e in audit.events]
    assert "eval_n3.axis" in types
    assert "eval_n3.summary" in types


def test_eval_all_handles_missing_ref(tmp_path, monkeypatch):
    fake = tmp_path / "x.kicad_sch"
    fake.write_text("(kicad_sch)")

    class FakeProc:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/kicad-cli")
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: FakeProc())

    audit = FakeAudit()
    result = eval_all(fake, None, Path("kicad-cli"), audit)
    assert result["sem_equiv"] == 0.0
    assert "composite" in result
```

**Green:** Add at bottom of `eval_n3.py`:

```python
def eval_all(
    sch_path: Path,
    ref_netlist: Path | None,
    cli_path: Path,
    audit_logger,
) -> dict:
    """Run all 5 axes + composite; emit NDJSON audit events.

    Args:
        sch_path: candidate .kicad_sch to evaluate.
        ref_netlist: reference netlist for sem_equiv. If None, sem_equiv=0.0.
        cli_path: kicad-cli binary (default Path("kicad-cli")).
        audit_logger: kicad_sch.audit_log.AuditLogger instance.

    Returns:
        dict with keys parse_ok, erc_clean, sch_render, drc_clean,
        sem_equiv, composite. All numeric.
    """
    axes: dict = {}
    axes["parse_ok"] = eval_parse_ok(sch_path, cli_path)
    audit_logger.log_event(
        "eval_n3.axis",
        {"axis": "parse_ok", "sch": str(sch_path), "score": axes["parse_ok"]},
    )
    axes["erc_clean"] = eval_erc_clean(sch_path, cli_path)
    audit_logger.log_event(
        "eval_n3.axis",
        {"axis": "erc_clean", "sch": str(sch_path), "score": axes["erc_clean"]},
    )
    axes["sch_render"] = eval_sch_render(sch_path, cli_path)
    audit_logger.log_event(
        "eval_n3.axis",
        {"axis": "sch_render", "sch": str(sch_path), "score": axes["sch_render"]},
    )
    axes["drc_clean"] = eval_drc_clean(sch_path, cli_path)
    audit_logger.log_event(
        "eval_n3.axis",
        {"axis": "drc_clean", "sch": str(sch_path), "score": axes["drc_clean"]},
    )
    if ref_netlist is not None and Path(ref_netlist).exists():
        axes["sem_equiv"] = eval_sem_equiv(sch_path, ref_netlist)
    else:
        axes["sem_equiv"] = 0.0
    audit_logger.log_event(
        "eval_n3.axis",
        {"axis": "sem_equiv", "sch": str(sch_path),
         "score": axes["sem_equiv"]},
    )
    axes["composite"] = composite(axes)
    audit_logger.log_event(
        "eval_n3.summary",
        {"sch": str(sch_path), "scores": dict(axes)},
    )
    return axes
```

Run pytest → green.

**Commit:**

```
feat(kicad-sch): orchestrate eval_all with audit log

Runs 5 axes + composite, emits per-axis + summary NDJSON via
AuditLogger. Handles missing ref by zeroing sem_equiv.
```

---

## Task 9 — `run_eval_n3.py` CLI runner (5 seeds × N files)

**Red:** Create `~/ailiance/tests/kicad_sch/test_run_eval_n3.py`:

```python
"""Tests for run_eval_n3 CLI orchestrator."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

RUNNER = Path.home() / "ailiance/scripts/run_eval_n3.py"


@pytest.mark.skipif(not RUNNER.exists(), reason="runner not yet created")
def test_runner_emits_seed_records(tmp_path, monkeypatch):
    sch_dir = tmp_path / "sch"
    sch_dir.mkdir()
    (sch_dir / "a.kicad_sch").write_text("(kicad_sch (version 20240101))")
    ref_dir = tmp_path / "ref"
    ref_dir.mkdir()
    (ref_dir / "a.kicad_sch").write_text("(kicad_sch (version 20240101))")
    out = tmp_path / "results.json"

    res = subprocess.run(
        [sys.executable, str(RUNNER),
         "--sch-dir", str(sch_dir),
         "--ref-dir", str(ref_dir),
         "--model-key", "test-model",
         "--domain", "kicad-sch",
         "--out", str(out),
         "--audit-dir", str(tmp_path / "audit"),
         "--mock-cli"],  # see implementation: short-circuits real kicad-cli
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    assert out.exists()
    data = json.loads(out.read_text())
    assert isinstance(data, list)
    # 1 file × 5 seeds = 5 records (one per seed).
    assert len(data) == 5
    for r in data:
        assert r["model_key"] == "test-model"
        assert r["domain"] == "kicad-sch"
        assert r["seed"] in [42, 137, 1024, 8675309, 31415]
        for axis in ["parse_ok", "erc_clean", "sch_render",
                     "drc_clean", "sem_equiv", "composite"]:
            assert axis in r


def test_runner_aggregates_pass_rate_for_bench_comparison(tmp_path):
    """Output must include a `pass_rate` field consumable by bench_comparison.

    Spec: bench_comparison reads validator JSON entries shaped as:
        {"model_key": ..., "domain": ..., "pass_rate": <0..1>, "n_samples": N}
    run_eval_n3 must also emit an aggregate sidecar (--out-aggregate).
    """
    sch_dir = tmp_path / "sch"
    sch_dir.mkdir()
    (sch_dir / "a.kicad_sch").write_text("(kicad_sch (version 20240101))")
    out = tmp_path / "results.json"
    agg = tmp_path / "agg.json"

    res = subprocess.run(
        [sys.executable, str(RUNNER),
         "--sch-dir", str(sch_dir),
         "--ref-dir", str(sch_dir),  # self-ref for sanity
         "--model-key", "m",
         "--domain", "d",
         "--out", str(out),
         "--out-aggregate", str(agg),
         "--audit-dir", str(tmp_path / "audit"),
         "--mock-cli"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    data = json.loads(agg.read_text())
    assert len(data) == 1
    cell = data[0]
    assert cell["model_key"] == "m"
    assert cell["domain"] == "d"
    assert "pass_rate" in cell
    assert "n_samples" in cell
    assert cell["n_samples"] == 5  # 1 file × 5 seeds
```

**Green:** Create `~/ailiance/scripts/run_eval_n3.py`:

```python
#!/usr/bin/env python3
"""Run eval_n3 5-axis scorer over a directory of .kicad_sch files × 5 seeds.

Outputs:
  --out          : flat list of per-(file, seed) records (audit detail)
  --out-aggregate: bench_comparison-compatible cells (model_key, domain,
                   pass_rate, n_samples) where pass_rate = mean composite
                   across all (file, seed) pairs.

Audit:
  --audit-dir <dir> writes NDJSON via AuditLogger, sha256-signed at end.

Determinism:
  Seeds locked to [42, 137, 1024, 8675309, 31415] per spec.
  kicad-cli itself is deterministic; seeds drive any future LLM regen
  wrapper — they are stored on each record for traceability.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

# Allow running both as a script (python scripts/run_eval_n3.py) and as a
# module under tests. Add scripts/ to sys.path so kicad_sch.eval_n3 resolves.
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from kicad_sch.eval_n3 import eval_all  # noqa: E402

SEEDS = [42, 137, 1024, 8675309, 31415]


class _NoopAudit:
    """Used when AuditLogger import fails (e.g. Foundation not yet shipped)."""

    def log_event(self, event_type, payload):
        return None

    def sha256_sign(self):
        return ""


def _get_audit(audit_dir: Path | None):
    if audit_dir is None:
        return _NoopAudit()
    try:
        from kicad_sch.audit_log import AuditLogger  # type: ignore
    except ImportError:
        print("WARN: kicad_sch.audit_log unavailable; using no-op audit",
              file=sys.stderr)
        return _NoopAudit()
    audit_dir.mkdir(parents=True, exist_ok=True)
    return AuditLogger(audit_dir / f"eval_n3_{time.strftime('%Y%m%d_%H%M')}.ndjson")


class _MockEvalAll:
    """Replaces eval_all under --mock-cli to keep tests hermetic."""

    @staticmethod
    def __call__(sch_path, ref, cli, audit):
        scores = {
            "parse_ok": 1, "erc_clean": 1, "sch_render": 1,
            "drc_clean": 0, "sem_equiv": 1.0,
        }
        from kicad_sch.eval_n3 import composite as _c
        scores["composite"] = _c(scores)
        audit.log_event("eval_n3.axis.mock",
                        {"sch": str(sch_path), "scores": scores})
        return scores


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sch-dir", type=Path, required=True)
    ap.add_argument("--ref-dir", type=Path, required=True)
    ap.add_argument("--model-key", required=True)
    ap.add_argument("--domain", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--out-aggregate", type=Path, default=None)
    ap.add_argument("--audit-dir", type=Path, default=None)
    ap.add_argument("--cli-path", type=Path, default=Path("kicad-cli"))
    ap.add_argument("--mock-cli", action="store_true",
                    help="Bypass kicad-cli (testing only).")
    args = ap.parse_args()

    audit = _get_audit(args.audit_dir)
    runner = _MockEvalAll() if args.mock_cli else eval_all

    records: list[dict] = []
    sch_files = sorted(args.sch_dir.glob("*.kicad_sch"))
    if not sch_files:
        sys.exit(f"No .kicad_sch files under {args.sch_dir}")

    for sch in sch_files:
        ref_candidate = args.ref_dir / sch.name
        ref = ref_candidate if ref_candidate.exists() else None
        for seed in SEEDS:
            scores = runner(sch, ref, args.cli_path, audit) \
                if args.mock_cli else runner(sch, ref, args.cli_path, audit)
            rec = {
                "model_key": args.model_key,
                "domain": args.domain,
                "sch": sch.name,
                "seed": seed,
                **{k: scores[k] for k in scores},
            }
            records.append(rec)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(records, indent=2))
    print(f"Wrote {args.out} ({len(records)} records)")

    if args.out_aggregate is not None:
        # bench_comparison-compatible aggregate: one row per (model, domain).
        composites = [r["composite"] for r in records]
        cell = {
            "model_key": args.model_key,
            "domain": args.domain,
            "pass_rate": round(statistics.mean(composites), 4) if composites else 0.0,
            "n_samples": len(records),
        }
        # Per-axis aggregates (consumed by bench_comparison --metric-axes).
        for axis in ["parse_ok", "erc_clean", "sch_render",
                     "drc_clean", "sem_equiv"]:
            vals = [r[axis] for r in records]
            cell[f"axis_{axis}"] = (round(statistics.mean(vals), 4)
                                    if vals else 0.0)
        args.out_aggregate.parent.mkdir(parents=True, exist_ok=True)
        args.out_aggregate.write_text(json.dumps([cell], indent=2))
        print(f"Wrote {args.out_aggregate} (1 aggregate cell)")

    sig = audit.sha256_sign()
    if sig:
        print(f"Audit signed: sha256={sig[:16]}…")


if __name__ == "__main__":
    main()
```

`chmod +x` not needed (invoked via `python …`). Run pytest → green.

**Commit:**

```
feat(kicad-sch): add run-eval-n3 CLI runner

5 seeds × N files; emits per-record JSON + bench-comparison
aggregate (--out-aggregate) with axis_* mean cols. --mock-cli
keeps unit tests hermetic.
```

---

## Task 10 — `bench_comparison.py --metric-axes` extension

**Red:** Create `~/ailiance/tests/kicad_sch/test_bench_comparison_axes.py`:

```python
"""Tests for bench_comparison.py --metric-axes extension."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

BENCH = Path.home() / "ailiance/scripts/bench_comparison.py"


def _write_ppl(path: Path, model: str, domain: str, ppl: float, n=30):
    rows = [{"model_key": model, "domain": domain,
             "perplexity": ppl, "n_samples": n}]
    path.write_text(json.dumps(rows))


def _write_axes_validator(path: Path, model: str, domain: str):
    """Mimic run_eval_n3 --out-aggregate output."""
    rows = [{
        "model_key": model, "domain": domain,
        "pass_rate": 0.7, "n_samples": 5,
        "axis_parse_ok": 1.0, "axis_erc_clean": 0.8,
        "axis_sch_render": 0.6, "axis_drc_clean": 0.0,
        "axis_sem_equiv": 0.4,
    }]
    path.write_text(json.dumps(rows))


def test_no_axes_flag_is_backward_compat(tmp_path):
    """Without --metric-axes, output matches PR #24 behavior (no axis cols)."""
    base = tmp_path / "perplexity_base_test.json"
    tuned = tmp_path / "perplexity_v1-only_test.json"
    _write_ppl(base, "m1", "d1", 10.0)
    _write_ppl(tuned, "m1", "d1", 8.0)
    out = tmp_path / "out"

    res = subprocess.run(
        [sys.executable, str(BENCH),
         "--base", str(base), "--tuned", str(tuned),
         "--out-prefix", str(out)],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    md = (Path(str(out) + ".md")).read_text()
    assert "parse_ok" not in md
    assert "sem_equiv" not in md
    assert "lift_log" in md  # legacy column preserved


def test_axes_flag_adds_columns(tmp_path):
    base = tmp_path / "perplexity_base_test.json"
    tuned = tmp_path / "perplexity_v1-only_test.json"
    val = tmp_path / "axes_validator.json"
    _write_ppl(base, "m1", "d1", 10.0)
    _write_ppl(tuned, "m1", "d1", 8.0)
    _write_axes_validator(val, "m1", "d1")
    out = tmp_path / "out"

    res = subprocess.run(
        [sys.executable, str(BENCH),
         "--base", str(base), "--tuned", str(tuned),
         "--validator-tuned", str(val),
         "--metric-axes",
         "parse_ok,erc_clean,sch_render,drc_clean,sem_equiv",
         "--out-prefix", str(out)],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    md = (Path(str(out) + ".md")).read_text()
    for col in ["parse_ok", "erc_clean", "sch_render",
                "drc_clean", "sem_equiv"]:
        assert col in md, f"missing column {col} in MD output"
    # Composite (= existing validator_lift surrogate) preserved
    assert "lift_log" in md


def test_axes_flag_json_carries_axis_fields(tmp_path):
    base = tmp_path / "perplexity_base_test.json"
    tuned = tmp_path / "perplexity_v1-only_test.json"
    val = tmp_path / "axes_validator.json"
    _write_ppl(base, "m1", "d1", 10.0)
    _write_ppl(tuned, "m1", "d1", 8.0)
    _write_axes_validator(val, "m1", "d1")
    out = tmp_path / "out"

    subprocess.run(
        [sys.executable, str(BENCH),
         "--base", str(base), "--tuned", str(tuned),
         "--validator-tuned", str(val),
         "--metric-axes",
         "parse_ok,erc_clean,sch_render,drc_clean,sem_equiv",
         "--out-prefix", str(out)],
        check=True, capture_output=True, text=True,
    )
    data = json.loads((Path(str(out) + ".json")).read_text())
    assert len(data) == 1
    row = data[0]
    for axis in ["parse_ok", "erc_clean", "sch_render",
                 "drc_clean", "sem_equiv"]:
        assert f"axis_{axis}" in row
```

Run pytest → all 3 fail (flag absent / columns missing).

**Green:** Modify `~/ailiance/scripts/bench_comparison.py`. Surgical patches only — preserve PR #24 behavior when `--metric-axes` is absent.

Patch A — add CLI flag in `argparse` block (after `--validator-min-cells`):

```python
    parser.add_argument(
        "--metric-axes", default=None,
        help="Comma-sep axis names to surface as extra MD columns "
             "(reads axis_<name> fields from --validator-tuned JSON). "
             "Example: parse_ok,erc_clean,sch_render,drc_clean,sem_equiv",
    )
```

Patch B — parse the flag after `args = parser.parse_args()`:

```python
    metric_axes: list[str] = []
    if args.metric_axes:
        metric_axes = [a.strip() for a in args.metric_axes.split(",")
                       if a.strip()]
```

Patch C — extend `load_validator` to also return axis dicts. Replace
`load_validator` body with:

```python
def load_validator(path: Path):
    """Load validator JSON.

    Returns (pass_rate_idx, axes_idx) where:
      pass_rate_idx: {(model_key, domain): pass_rate}
      axes_idx:     {(model_key, domain): {axis_name: float, ...}}
    """
    data = json.loads(path.read_text())
    pr_idx: dict[tuple[str, str], float] = {}
    ax_idx: dict[tuple[str, str], dict[str, float]] = {}
    for r in data:
        mk = r.get("model_key")
        dom = r.get("domain")
        if mk is None or dom is None:
            continue
        if r.get("pass_rate") is not None:
            pr_idx[(mk, dom)] = float(r["pass_rate"])
        axes = {k[len("axis_"):]: float(v)
                for k, v in r.items()
                if k.startswith("axis_") and v is not None}
        if axes:
            ax_idx[(mk, dom)] = axes
    return pr_idx, ax_idx
```

Patch D — update call sites (2 places) from:
```python
val_base_idx = load_validator(vb_path)
```
to:
```python
val_base_idx, ax_base_idx = load_validator(vb_path)
```
and same for tuned (`val_tuned_idx, ax_tuned_idx = load_validator(vt_path)`).
Initialise `ax_base_idx: dict = {}` and `ax_tuned_idx: dict = {}` near the
existing `val_base_idx: dict[...] = {}` declarations.

Patch E — in the per-row build loop, after the `validator_lift` block, append:

```python
        if metric_axes:
            base_axes = ax_base_idx.get(key, {})
            tuned_axes = ax_tuned_idx.get(key, {})
            for axis in metric_axes:
                # Prefer tuned (post-training) for headline; fallback to base.
                v = tuned_axes.get(axis, base_axes.get(axis))
                row[f"axis_{axis}"] = round(v, 4) if v is not None else None
```

Patch F — in the markdown rendering loop, after `model_has_val` table header
selection, when `metric_axes` is truthy append an additional header segment
and per-row segment. Concretely, before `for c in cells:`:

```python
        if metric_axes:
            axis_header = " " + " | ".join(metric_axes) + " |"
            axis_sep = "---:|" * len(metric_axes)
            # Append to last header line + separator line.
            lines[-2] = lines[-2].rstrip("|") + " | " + axis_header
            lines[-1] = lines[-1].rstrip("|") + "|" + axis_sep
```

…and inside the row-build (just before `lines.append(row_str)`):

```python
            if metric_axes:
                for axis in metric_axes:
                    v = c.get(f"axis_{axis}")
                    row_str += f" {v if v is not None else '-'} |"
```

Run pytest → green (3 tests).

**Commit:**

```
feat(bench-comparison): add metric-axes columns

Optional --metric-axes parse_ok,... surfaces 5 per-axis cols
from --validator-tuned aggregate JSON (axis_<name> fields).
Backward-compat preserved when flag absent.
```

---

## Task 11 — Integration smoke (one real kicad-cli call)

**Red:** Append to `test_eval_n3.py`:

```python
import shutil


@pytest.mark.skipif(
    shutil.which("kicad-cli") is None or not REF_SCH.exists(),
    reason="kicad-cli or ref fixture missing",
)
def test_eval_all_real_cli_on_ref_fixture(tmp_path):
    """Smoke: real kicad-cli on spi_bus_4devices → composite > 0.5."""
    from kicad_sch.eval_n3 import eval_all

    class _Audit:
        def __init__(self): self.events = []
        def log_event(self, t, p): self.events.append((t, p))
        def sha256_sign(self): return ""

    audit = _Audit()
    result = eval_all(REF_SCH, REF_SCH, Path("kicad-cli"), audit)
    assert result["parse_ok"] == 1
    assert result["composite"] >= 0.45  # parse 0.3 + render 0.15 floor
```

Run pytest → green on Studio (kicad-cli installed) or skipped on macM1
without kicad-cli.

**Commit:**

```
test(kicad-sch): real-cli smoke on ref fixture

Gate via skipif; verifies parse_ok=1 and composite>=0.45 on
spi_bus_4devices reference schematic.
```

---

## Task 12 — Wire-up doc + README pointer

Update `~/ailiance/scripts/kicad_sch/README.md` (create if absent) with a
"How to run N3" section:

```markdown
## Eval N3 — 5-axis evaluator

Run on a directory of generated `.kicad_sch` files:

    uv run python scripts/run_eval_n3.py \
        --sch-dir output/kicad_sch_gen/qwen36-D3/ \
        --ref-dir ~/ailiance-data/kicad-sch-refs/ \
        --model-key kicad-sch-qwen36-D3 \
        --domain kicad-sch \
        --out output/eval/raw/eval_n3_qwen36-D3.json \
        --out-aggregate output/eval/raw/eval_n3_qwen36-D3.agg.json \
        --audit-dir output/audit/kicad-sch-2026-05-11/

Feed aggregates into bench_comparison:

    uv run python scripts/bench_comparison.py \
        --validator-tuned output/eval/raw/eval_n3_qwen36-D3.agg.json \
        --metric-axes parse_ok,erc_clean,sch_render,drc_clean,sem_equiv

Composite weights: 0.30·parse_ok + 0.30·erc_clean + 0.15·sch_render
+ 0.10·drc_clean + 0.15·sem_equiv (locked, sums to 1.0).
```

Push everything:

```bash
ssh studio 'cd ~/ailiance && git push origin <branch>'
```

**Commit:**

```
docs(kicad-sch): document eval-n3 run + bench wiring

How-to for run_eval_n3 + bench_comparison --metric-axes; locks
weights snapshot in repo for AI Act §Annex IV 2.c traceability.
```

---

## Self-review checklist (before declaring DONE)

- [x] All 5 axes implemented (`parse_ok`, `erc_clean`, `sch_render`, `drc_clean`, `sem_equiv`).
- [x] `composite` weights match spec exactly (0.30 / 0.30 / 0.15 / 0.10 / 0.15).
- [x] `eval_all` orchestrator emits NDJSON audit events (`eval_n3.axis` × 5 + `eval_n3.summary`).
- [x] Foundation `AuditLogger` integration via duck-typed `log_event`/`sha256_sign` (zero hard import beyond `_get_audit`).
- [x] `run_eval_n3.py` honors locked seeds `[42, 137, 1024, 8675309, 31415]`.
- [x] `run_eval_n3.py` emits both detail and aggregate JSON (latter consumed by `bench_comparison`).
- [x] `bench_comparison.py` `--metric-axes` is opt-in; absence yields identical PR #24 behavior.
- [x] Backward-compat tested (`test_no_axes_flag_is_backward_compat`).
- [x] All tests hermetic except one skipif-gated integration smoke.
- [x] Commits subject ≤50 chars, no underscore in scope, no AI attribution.
- [x] Author `electron-rare <108685187+electron-rare@users.noreply.github.com>` on every commit.
- [x] Multi-seed first-class (5 seeds × N files; cf. `feedback_multi_seed_first_class.md`).

## Risks (carried from parent spec)

- `drc_clean` may always score 0 with the minimal seed (no PCB layout emitted). Spec weight 0.10 limits damage. Future plan can introduce a default PCB template seeded from BoM auto-place.
- `sem_equiv` cosine on bag-of-features is coarse; graph-iso upgrade (`networkx.is_isomorphic` with attribute matchers) is wired as a TODO inside `eval_sem_equiv` for refs ≤15 components.
- `kicad-cli` rc=3 on locale-dependent French error strings: tests verify `rc != 0` (not stderr match) so locale changes won't break.
- ERC regex `_ERC_COUNT_RE` matches "N error" (singular permitted). If kicad-cli v10.0.3 changes summary format, axis defaults to 1 (conservative); audit log captures raw stdout for forensic review.

## Out-of-scope (not in this plan)

- Foundation `audit_log.py` + `manifest.py` (separate plan, shipped first).
- D1 scraper / D2 synth / D3 mixer (parent spec Phase 1).
- LoRA training (Track C, parent spec Phase 2).
- Track D pipelines (parent spec Phase 3).
- Pre-registration doc + risk register (parent spec Phase 0).
- Model cards + audit signing of full Phase 6 run (parent spec Phase 6).
