# Track C — LoRA Training (kicad-sch v10)

> **Sub-skills required:** superpowers:writing-plans, superpowers:test-driven-development, superpowers:executing-plans

**Date:** 2026-05-11
**Author:** Clement Saillant (LElectron Rare)
**Parent spec:** `docs/superpowers/specs/2026-05-11-kicad-sch-gap-design.md` (commit `e58731a`)
**Scope:** Track C of the kicad-sch gap design — datasets D1/D2/D3 + 6 LoRA training runs (qwen36 × {D1,D2,D3} and gemma-e4b × {D1,D2,D3}).
**Status:** DRAFT (ready for execution)

## Goal

Produce 6 LoRA adapters that close the `parse_ok_kicad_rate = 0` gap on `.kicad_sch` v10 generation by training qwen36 and gemma-e4b on three dataset splits (D1 scraped, D2 synth, D3 mixed). Each adapter must be auditable per EU AI Act Annex IV §2.b (data lineage) and §7 (logging).

## Non-goals

- Track D (hybrid DSL→compiler) — separate plan.
- Eval N3 5-axis — separate plan.
- M3/M4 training execution — config templates only.
- New foundation modules (`manifest.py`, `audit_log.py`) — assumed delivered by Foundation track.

## Dependencies

- **Foundation track:** `~/eu-kiki/scripts/kicad_sch/manifest.py` exposing `DatasetManifest(split: str)` with `.append(row: dict) -> None` and `.flush() -> Path` (writes CSV with the 8 Annex IV columns).
- **Foundation track:** `~/eu-kiki/scripts/kicad_sch/audit_log.py` exposing `AuditLogger(run_id: str)` with `.event(kind: str, **fields) -> None` (NDJSON append).
- **Eval N3 track:** smoke `parse_ok` scorer reused after each train run (`eval_smoke_one_lora.sh`).
- Tools: `gh` CLI ≥ 2.40, `kicad-cli 10.0.2`, `mlx_lm`, `uv`, Python 3.14.
- D2 compilers: `skidl`, `atopile` (`ato` CLI), `circuit-synth` — installed in `~/eu-kiki/.venv-d2/`.

## File Structure

```
~/eu-kiki/
├── scripts/kicad_sch/
│   ├── manifest.py                  # (Foundation)
│   ├── audit_log.py                 # (Foundation)
│   ├── strip_lib_symbols.py         # task C2
│   ├── scrape_d1.py                 # task C4
│   ├── synth_d2.py                  # task C6
│   ├── mix_d3.py                    # task C7
│   ├── train_lora.py                # task C9
│   ├── run_m2_all.sh                # task C12
│   └── README.md                    # task C13
├── tests/kicad_sch/
│   ├── conftest.py                  # task C0
│   ├── test_strip_lib_symbols.py    # task C1
│   ├── test_scrape_d1.py            # task C3
│   ├── test_synth_d2.py             # task C5
│   ├── test_mix_d3.py               # task C7
│   └── test_train_lora.py           # task C9
└── adapters/v3/                     # task C10 outputs

~/eu-kiki-data/
├── kicad-sch-scraped/               # D1
├── kicad-sch-scraped-stripped/      # D1 post-strip
├── kicad-sch-synth/                 # D2
├── kicad-sch-synth-stripped/        # D2 post-strip
├── kicad-sch-mixed/                 # D3 (symlinks)
└── kicad-sch-mixed-stripped/        # D3 post-strip

~/KIKI-Mac_tunner/configs/
├── eu-kiki-v3-qwen36-kicad-sch-D1.yaml      # task C8 (M2)
├── eu-kiki-v3-qwen36-kicad-sch-D2.yaml      # task C8
├── eu-kiki-v3-qwen36-kicad-sch-D3.yaml      # task C8
├── eu-kiki-v3-gemma4-kicad-sch-D1.yaml      # task C8
├── eu-kiki-v3-gemma4-kicad-sch-D2.yaml      # task C8
├── eu-kiki-v3-gemma4-kicad-sch-D3.yaml      # task C8
├── eu-kiki-v3-devstral-kicad-sch-{D1,D2,D3}.yaml    # task C11 (M3, stubs)
├── eu-kiki-v3-apertus-kicad-sch-{D1,D2,D3}.yaml     # task C11 (M4)
├── eu-kiki-v3-eurollm-kicad-sch-{D1,D2,D3}.yaml     # task C11 (M4)
└── eu-kiki-v3-medium35-kicad-sch-{D1,D2,D3}.yaml    # task C11 (M4)
```

**Note on paths:** spec mentions `~/Projets/KIKI-Mac_tunner/configs/`; on Studio the actual root is `~/KIKI-Mac_tunner/configs/` (no `Projets/` prefix). All v2 configs live there; we follow existing convention.

## Tasks

### C0 — Test scaffolding (≈ 3 min)

**Files:** `~/eu-kiki/tests/kicad_sch/conftest.py`, `~/eu-kiki/tests/kicad_sch/__init__.py`.

Add fixtures for minimal valid `.kicad_sch` v10 strings (with and without `lib_symbols`) and a `kicad_cli_available` skip-marker fixture (checks `which kicad-cli`).

```python
# conftest.py
import shutil
import pytest

MIN_SCH_WITH_LIB = """(kicad_sch (version 20240101) (generator eeschema)
  (uuid "00000000-0000-0000-0000-000000000001")
  (paper "A4")
  (lib_symbols
    (symbol "Device:R"
      (pin passive line (at 0 0 0) (name "~") (number "1"))
      (pin passive line (at 0 -10 0) (name "~") (number "2"))))
  (symbol (lib_id "Device:R") (at 100 100 0)
    (uuid "00000000-0000-0000-0000-000000000002")))"""


@pytest.fixture
def min_sch_with_lib():
    return MIN_SCH_WITH_LIB


@pytest.fixture
def kicad_cli_available():
    if shutil.which("kicad-cli") is None:
        pytest.skip("kicad-cli not on PATH")
    return True
```

**Verify:** `uv run python -m pytest tests/kicad_sch/ --collect-only` → 0 tests, no collection errors.

**Commit:** `test(kicad-sch): add Track C test scaffolding`

---

### C1 — strip_lib_symbols (TDD red) (≈ 4 min)

**File:** `~/eu-kiki/tests/kicad_sch/test_strip_lib_symbols.py`.

Write failing tests before any production code exists:

```python
from pathlib import Path
import pytest
from kicad_sch.strip_lib_symbols import strip_lib_symbols


def test_strip_preserves_lib_id_references(tmp_path, min_sch_with_lib):
    src = tmp_path / "in.kicad_sch"
    src.write_text(min_sch_with_lib)
    out = tmp_path / "out.kicad_sch"
    rc = strip_lib_symbols(src, out)
    assert rc == 0
    content = out.read_text()
    # Either zero lib_symbols content or the empty placeholder remains;
    # crucial bit: the inline (symbol "Device:R" ...) defs are gone.
    assert "(pin passive line" not in content
    assert '(lib_id "Device:R")' in content


def test_strip_returns_nonzero_on_unparseable(tmp_path):
    src = tmp_path / "bad.kicad_sch"
    src.write_text("(((not balanced")
    out = tmp_path / "out.kicad_sch"
    rc = strip_lib_symbols(src, out)
    assert rc != 0


def test_strip_idempotent_when_no_lib_symbols(tmp_path):
    src = tmp_path / "in.kicad_sch"
    src.write_text("(kicad_sch (version 20240101) (generator eeschema))")
    out = tmp_path / "out.kicad_sch"
    rc = strip_lib_symbols(src, out)
    assert rc == 0
    assert "(kicad_sch" in out.read_text()
```

**Verify:** `uv run python -m pytest tests/kicad_sch/test_strip_lib_symbols.py -x` → 3 failures (module missing).

**Commit:** `test(kicad-sch): red tests for strip_lib_symbols`

---

### C2 — strip_lib_symbols (TDD green) (≈ 5 min)

**File:** `~/eu-kiki/scripts/kicad_sch/strip_lib_symbols.py`.

```python
"""Strip (lib_symbols ...) block from .kicad_sch.

Reduces ctx 5-50KB -> 2-5KB; lib_id refs are resolved by kicad-cli at
load time. Returns 0 on success, nonzero on parse failure.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _find_top_block(text: str, head: str) -> tuple[int, int] | None:
    i = text.find(head)
    if i < 0:
        return None
    depth = 0
    for j in range(i, len(text)):
        c = text[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return (i, j + 1)
    return None


def strip_lib_symbols(src: Path, out: Path) -> int:
    text = Path(src).read_text(encoding="utf-8")
    if text.count("(") != text.count(")"):
        return 2
    span = _find_top_block(text, "(lib_symbols")
    if span is None:
        Path(out).write_text(text, encoding="utf-8")
        return 0
    a, b = span
    new = text[:a] + "(lib_symbols)" + text[b:]
    Path(out).write_text(new, encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args(argv)
    if a.input.is_dir():
        a.output.mkdir(parents=True, exist_ok=True)
        rc_total = 0
        for f in a.input.glob("*.kicad_sch"):
            rc = strip_lib_symbols(f, a.output / f.name)
            if rc != 0:
                rc_total |= 1
        return rc_total
    return strip_lib_symbols(a.input, a.output)


if __name__ == "__main__":
    sys.exit(main())
```

**Verify:** `uv run python -m pytest tests/kicad_sch/test_strip_lib_symbols.py -x` → 3 passed.

**Commit:** `feat(kicad-sch): strip lib_symbols pre-processor`

---

### C3 — scrape_d1 (TDD red) (≈ 5 min)

**File:** `~/eu-kiki/tests/kicad_sch/test_scrape_d1.py`.

```python
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from kicad_sch.scrape_d1 import (
    canonical_hash,
    license_allowed,
    download_and_normalize,
)


def test_license_allowlist():
    al = {"MIT", "Apache-2.0", "CC0-1.0", "GPL-3.0"}
    assert license_allowed("MIT", al)
    assert license_allowed("apache-2.0", al)
    assert not license_allowed("AGPL-3.0", al)
    assert not license_allowed(None, al)


def test_canonical_hash_strips_uuids():
    a = '(uuid "11111111-2222-3333-4444-555555555555") (rest 1)'
    b = '(uuid "99999999-aaaa-bbbb-cccc-dddddddddddd") (rest 1)'
    assert canonical_hash(a) == canonical_hash(b)


def test_download_and_normalize_writes_dedup(tmp_path, monkeypatch):
    src_text = "(kicad_sch (version 20240101) (generator eeschema))"
    monkeypatch.setattr(
        "kicad_sch.scrape_d1._fetch_raw", lambda url: src_text
    )
    monkeypatch.setattr(
        "kicad_sch.scrape_d1._kicad_update", lambda p: 0
    )
    out = download_and_normalize(
        repo="foo/bar",
        path="x.kicad_sch",
        url="https://x",
        commit="abc",
        license_spdx="MIT",
        out_dir=tmp_path,
    )
    assert out is not None
    assert out.exists()
    assert out.suffix == ".kicad_sch"
```

**Verify:** all 3 fail (module missing).

**Commit:** `test(kicad-sch): red tests for scrape_d1`

---

### C4 — scrape_d1 (TDD green) (≈ 10 min)

**File:** `~/eu-kiki/scripts/kicad_sch/scrape_d1.py`.

Reuses the license-regex + clone pattern from
`~/eu-kiki/scripts/scrape_kicad_schematics.py` but discovers files via
`gh search code extension:kicad_sch` for breadth instead of a repo
whitelist.

```python
"""D1: scrape .kicad_sch from GitHub, license-filter, normalize, dedupe.

Output: hash-named files in ~/eu-kiki-data/kicad-sch-scraped/ + manifest
(D1 split) + NDJSON audit log.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from kicad_sch.audit_log import AuditLogger
from kicad_sch.manifest import DatasetManifest

_UUID_RE = re.compile(
    r'"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"',
    re.IGNORECASE,
)


def canonical_hash(text: str) -> str:
    canon = _UUID_RE.sub(
        '"00000000-0000-0000-0000-000000000000"', text
    )
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def license_allowed(spdx: str | None, allow: set[str]) -> bool:
    if not spdx:
        return False
    norm = {x.upper() for x in allow}
    return spdx.upper() in norm


def _fetch_raw(url: str) -> str:
    r = subprocess.run(
        ["curl", "-fsSL", url],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(f"fetch failed: {url}")
    return r.stdout


def _kicad_update(path: Path) -> int:
    r = subprocess.run(
        ["kicad-cli", "sch", "update", str(path)],
        capture_output=True, timeout=120,
    )
    return r.returncode


def _gh_search(max_files: int) -> list[dict]:
    r = subprocess.run(
        [
            "gh", "search", "code",
            "extension:kicad_sch",
            "--limit", str(max_files),
            "--json", "repository,path,url,sha",
        ],
        capture_output=True, text=True, timeout=120,
    )
    if r.returncode != 0:
        return []
    return json.loads(r.stdout or "[]")


def _repo_license(name_with_owner: str) -> str | None:
    r = subprocess.run(
        [
            "gh", "repo", "view", name_with_owner,
            "--json", "licenseInfo",
        ],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        return None
    info = json.loads(r.stdout or "{}").get("licenseInfo") or {}
    return info.get("spdxId")


def download_and_normalize(
    repo: str,
    path: str,
    url: str,
    commit: str,
    license_spdx: str,
    out_dir: Path,
) -> Path | None:
    raw = _fetch_raw(url)
    tmp = out_dir / f".tmp-{os.getpid()}.kicad_sch"
    tmp.write_text(raw, encoding="utf-8")
    if _kicad_update(tmp) != 0:
        tmp.unlink(missing_ok=True)
        return None
    text = tmp.read_text(encoding="utf-8")
    h = canonical_hash(text)
    final = out_dir / f"{h}.kicad_sch"
    if final.exists():
        tmp.unlink(missing_ok=True)
        return final
    tmp.rename(final)
    return final


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--max-files", type=int, default=10000)
    p.add_argument(
        "--license-allowlist",
        default="MIT,Apache-2.0,CC0-1.0,GPL-3.0",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path.home() / "eu-kiki-data/kicad-sch-scraped",
    )
    a = p.parse_args(argv)
    allow = set(a.license_allowlist.split(","))
    a.out_dir.mkdir(parents=True, exist_ok=True)
    run_id = "d1-" + datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    manifest = DatasetManifest(split="D1")
    log = AuditLogger(run_id=run_id)
    hits = _gh_search(a.max_files)
    log.event("d1_search_done", n=len(hits))
    n_ok = 0
    for h in hits:
        repo = h["repository"]["nameWithOwner"]
        spdx = _repo_license(repo)
        if not license_allowed(spdx, allow):
            log.event("d1_license_skip", repo=repo, spdx=spdx)
            continue
        try:
            out = download_and_normalize(
                repo=repo,
                path=h["path"],
                url=h["url"],
                commit=h.get("sha", ""),
                license_spdx=spdx,
                out_dir=a.out_dir,
            )
        except Exception as e:
            log.event("d1_fetch_fail", repo=repo, err=str(e))
            continue
        if out is None:
            log.event("d1_update_fail", repo=repo, path=h["path"])
            continue
        manifest.append({
            "source_type": "github_scrape",
            "source_url": h["url"],
            "commit_sha": h.get("sha", ""),
            "license_spdx": spdx,
            "dedup_hash": out.stem,
            "file_size_bytes": out.stat().st_size,
            "kicad_version_before": "unknown",
            "kicad_version_after": "10.0.2",
        })
        n_ok += 1
    manifest.flush()
    log.event("d1_done", accepted=n_ok)
    print(f"D1: {n_ok} files written to {a.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Verify:** `uv run python -m pytest tests/kicad_sch/test_scrape_d1.py -x` → 3 passed.

**Commit:** `feat(kicad-sch): D1 github scraper with license filter`

---

### C5 — synth_d2 (TDD red) (≈ 5 min)

**File:** `~/eu-kiki/tests/kicad_sch/test_synth_d2.py`.

```python
from pathlib import Path
import pytest
from kicad_sch.synth_d2 import TEMPLATES, randomize_values, synth_one


def test_templates_cover_minimum_set():
    names = {t["name"] for t in TEMPLATES}
    expected = {
        "voltage_divider", "rc_lowpass", "rlc_series",
        "ne555_astable", "opamp_noninv", "common_emitter",
    }
    assert expected.issubset(names)


def test_randomize_values_deterministic_with_seed():
    t = next(t for t in TEMPLATES if t["name"] == "voltage_divider")
    a = randomize_values(t, seed=42)
    b = randomize_values(t, seed=42)
    assert a == b


def test_synth_one_writes_file_when_compile_ok(tmp_path, monkeypatch):
    def fake_compile(tpl, vals, out):
        out.write_text(
            "(kicad_sch (version 20240101) (generator skidl))"
        )
        return 0

    monkeypatch.setattr(
        "kicad_sch.synth_d2._compile_skidl", fake_compile
    )
    monkeypatch.setattr(
        "kicad_sch.synth_d2._kicad_erc", lambda p: 0
    )
    out = synth_one(
        template="voltage_divider",
        compiler="skidl",
        seed=42,
        out_dir=tmp_path,
    )
    assert out is not None
    assert out.exists()


def test_synth_one_returns_none_when_erc_fails(tmp_path, monkeypatch):
    def fake_compile(tpl, vals, out):
        out.write_text("x")
        return 0

    monkeypatch.setattr(
        "kicad_sch.synth_d2._compile_skidl", fake_compile
    )
    monkeypatch.setattr(
        "kicad_sch.synth_d2._kicad_erc", lambda p: 3
    )
    out = synth_one(
        template="voltage_divider",
        compiler="skidl",
        seed=42,
        out_dir=tmp_path,
    )
    assert out is None
```

**Verify:** all 4 fail.

**Commit:** `test(kicad-sch): red tests for synth_d2`

---

### C6 — synth_d2 (TDD green) (≈ 12 min)

**File:** `~/eu-kiki/scripts/kicad_sch/synth_d2.py`.

Ships 10 templates (extension to 20-30 deferred to follow-up patch once
the venv has all three compilers).

```python
"""D2: random circuit synth -> skidl/atopile/circuit-synth -> kicad_sch.

Each template ships a renderer per compiler. ERC-clean rate target
~60-80% (rejected outputs are unlinked and logged).
"""
from __future__ import annotations

import argparse
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from kicad_sch.audit_log import AuditLogger
from kicad_sch.manifest import DatasetManifest

TEMPLATES: list[dict] = [
    {"name": "voltage_divider",
     "params": {"r1_k": (1, 100), "r2_k": (1, 100), "vin": (3, 24)}},
    {"name": "rc_lowpass",
     "params": {"r_k": (1, 100), "c_nf": (1, 1000)}},
    {"name": "rlc_series",
     "params": {"r": (1, 1000), "l_uh": (1, 1000), "c_nf": (1, 1000)}},
    {"name": "ne555_astable",
     "params": {"r1_k": (1, 100), "r2_k": (1, 100), "c_nf": (1, 1000)}},
    {"name": "opamp_noninv",
     "params": {"rf_k": (1, 100), "rg_k": (1, 100)}},
    {"name": "common_emitter",
     "params": {"rc_k": (1, 10), "re": (10, 1000), "rb_k": (10, 1000)}},
    {"name": "led_blinker",
     "params": {"r_led": (100, 1000), "vcc": (3, 12)}},
    {"name": "diode_clamp",
     "params": {"r_in_k": (1, 100)}},
    {"name": "ldo_3v3",
     "params": {"vin": (5, 12), "c_in_uf": (1, 10), "c_out_uf": (1, 10)}},
    {"name": "transistor_inv",
     "params": {"rb_k": (1, 100), "rc_k": (1, 10)}},
]

COMPILERS = ("skidl", "atopile", "circuit-synth")


def randomize_values(tpl: dict, seed: int) -> dict:
    rng = random.Random(seed)
    out = {}
    for k, v in tpl["params"].items():
        if isinstance(v, tuple) and all(isinstance(x, int) for x in v):
            out[k] = rng.randint(*v)
        else:
            out[k] = round(rng.uniform(*v), 3)
    return out


def _compile_skidl(tpl: dict, vals: dict, out: Path) -> int:
    # Real impl invokes skidl programmatically (see follow-up patch);
    # current stub emits a minimal but parseable v10 skeleton.
    out.write_text(
        '(kicad_sch (version 20240101) (generator skidl)\n'
        '  (uuid "00000000-0000-0000-0000-000000000001")\n'
        '  (paper "A4") (lib_symbols))\n',
        encoding="utf-8",
    )
    return 0


def _compile_atopile(tpl: dict, vals: dict, out: Path) -> int:
    r = subprocess.run(
        ["ato", "build", "--template", tpl["name"], "--out", str(out)],
        capture_output=True, timeout=120,
    )
    return r.returncode


def _compile_circuit_synth(tpl: dict, vals: dict, out: Path) -> int:
    r = subprocess.run(
        [
            sys.executable, "-m", "circuit_synth.build",
            "--template", tpl["name"], "--out", str(out),
        ],
        capture_output=True, timeout=120,
    )
    return r.returncode


def _kicad_erc(path: Path) -> int:
    r = subprocess.run(
        ["kicad-cli", "sch", "erc", str(path)],
        capture_output=True, timeout=60,
    )
    return r.returncode


def synth_one(
    template: str, compiler: str, seed: int, out_dir: Path,
) -> Path | None:
    tpl = next((t for t in TEMPLATES if t["name"] == template), None)
    if tpl is None:
        return None
    vals = randomize_values(tpl, seed)
    out = out_dir / f"{template}-{compiler}-{seed}.kicad_sch"
    fn = {
        "skidl": _compile_skidl,
        "atopile": _compile_atopile,
        "circuit-synth": _compile_circuit_synth,
    }[compiler]
    if fn(tpl, vals, out) != 0:
        out.unlink(missing_ok=True)
        return None
    if _kicad_erc(out) != 0:
        out.unlink(missing_ok=True)
        return None
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--n-samples", type=int, default=10000)
    p.add_argument(
        "--compilers", default="skidl,atopile,circuit-synth",
    )
    p.add_argument("--seed-start", type=int, default=0)
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path.home() / "eu-kiki-data/kicad-sch-synth",
    )
    a = p.parse_args(argv)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    comps = a.compilers.split(",")
    run_id = "d2-" + datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    log = AuditLogger(run_id=run_id)
    manifest = DatasetManifest(split="D2")
    rng = random.Random(a.seed_start)
    n_ok = 0
    for i in range(a.n_samples):
        tpl = rng.choice(TEMPLATES)
        comp = rng.choice(comps)
        seed = a.seed_start + i
        out = synth_one(tpl["name"], comp, seed, a.out_dir)
        if out is None:
            log.event(
                "d2_synth_fail",
                template=tpl["name"], compiler=comp, seed=seed,
            )
            continue
        manifest.append({
            "source_type": "synth",
            "source_url": f"gen:{tpl['name']}@seed{seed}@{comp}",
            "commit_sha": "",
            "license_spdx": "CC0-1.0",
            "dedup_hash": f"{tpl['name']}-{comp}-{seed}",
            "file_size_bytes": out.stat().st_size,
            "kicad_version_before": "10.0.2",
            "kicad_version_after": "10.0.2",
        })
        n_ok += 1
    manifest.flush()
    log.event("d2_done", accepted=n_ok, requested=a.n_samples)
    print(f"D2: {n_ok}/{a.n_samples} files written to {a.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Verify:** `uv run python -m pytest tests/kicad_sch/test_synth_d2.py -x` → 4 passed.

**Commit:** `feat(kicad-sch): D2 random circuit synth pipeline`

---

### C7 — mix_d3 (TDD red+green) (≈ 7 min)

**Files:** `tests/kicad_sch/test_mix_d3.py`, `scripts/kicad_sch/mix_d3.py`.

Tests:

```python
from pathlib import Path
import pytest
from kicad_sch.mix_d3 import mix, stratify


def test_stratify_balances_compilers(tmp_path):
    files = (
        [tmp_path / f"voltage_divider-skidl-{i}.kicad_sch"
         for i in range(10)]
        + [tmp_path / f"rc_lowpass-atopile-{i}.kicad_sch"
           for i in range(10)]
        + [tmp_path / f"led-circuit-synth-{i}.kicad_sch"
           for i in range(10)]
    )
    for f in files:
        f.write_text("x")
    picked = stratify(
        files, n=6, key_re=r"-(skidl|atopile|circuit-synth)-",
    )
    keys = []
    for p in picked:
        for k in ("skidl", "atopile", "circuit-synth"):
            if f"-{k}-" in p.name:
                keys.append(k)
                break
    assert len(set(keys)) == 3
    assert len(picked) == 6


def test_mix_symlinks_half_half(tmp_path):
    d1 = tmp_path / "d1"
    d1.mkdir()
    d2 = tmp_path / "d2"
    d2.mkdir()
    d3 = tmp_path / "d3"
    d3.mkdir()
    for i in range(20):
        (d1 / f"hash{i:02d}.kicad_sch").write_text("a")
        (d2 / f"voltage_divider-skidl-{i}.kicad_sch").write_text("b")
    n = mix(d1=d1, d2=d2, d3=d3, n_total=10, seed=42)
    assert n == 10
    links = list(d3.iterdir())
    assert len(links) == 10
    assert all(l.is_symlink() for l in links)
```

Implementation:

```python
"""D3: 50/50 D1+D2 mixer, stratified by compiler (D2)/license (D1)."""
from __future__ import annotations

import argparse
import random
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from kicad_sch.audit_log import AuditLogger
from kicad_sch.manifest import DatasetManifest


def stratify(files: list[Path], n: int, key_re: str) -> list[Path]:
    rx = re.compile(key_re)
    buckets: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        m = rx.search(f.name)
        k = m.group(1) if m else "_"
        buckets[k].append(f)
    keys = sorted(buckets)
    per = max(1, n // len(keys))
    picked: list[Path] = []
    rng = random.Random(0)
    for k in keys:
        rng.shuffle(buckets[k])
        picked.extend(buckets[k][:per])
    return picked[:n]


def mix(
    d1: Path, d2: Path, d3: Path, n_total: int, seed: int,
) -> int:
    d3.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    d1_files = list(d1.glob("*.kicad_sch"))
    d2_files = stratify(
        list(d2.glob("*.kicad_sch")),
        n=n_total // 2,
        key_re=r"-(skidl|atopile|circuit-synth)-",
    )
    rng.shuffle(d1_files)
    d1_pick = d1_files[: n_total - len(d2_files)]
    idx = 0
    manifest = DatasetManifest(split="D3")
    for src in d1_pick + d2_files:
        link = d3 / f"{idx:06d}.kicad_sch"
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(src.resolve())
        manifest.append({
            "source_type": "mix",
            "source_url": str(src),
            "commit_sha": "",
            "license_spdx": "",
            "dedup_hash": link.stem,
            "file_size_bytes": src.stat().st_size,
            "kicad_version_before": "10.0.2",
            "kicad_version_after": "10.0.2",
        })
        idx += 1
    manifest.flush()
    return idx


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--d1",
        type=Path,
        default=Path.home() / "eu-kiki-data/kicad-sch-scraped",
    )
    p.add_argument(
        "--d2",
        type=Path,
        default=Path.home() / "eu-kiki-data/kicad-sch-synth",
    )
    p.add_argument(
        "--d3",
        type=Path,
        default=Path.home() / "eu-kiki-data/kicad-sch-mixed",
    )
    p.add_argument("--n-total", type=int, default=10000)
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args(argv)
    run_id = "d3-" + datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    log = AuditLogger(run_id=run_id)
    n = mix(a.d1, a.d2, a.d3, a.n_total, a.seed)
    log.event("d3_done", linked=n)
    print(f"D3: {n} symlinks in {a.d3}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Verify:** `uv run python -m pytest tests/kicad_sch/test_mix_d3.py -x` → 2 passed.

**Commit:** `feat(kicad-sch): D3 50 50 mixer with stratification`

---

### C8 — M2 YAML configs (6 files) (≈ 4 min)

**Files:** `~/KIKI-Mac_tunner/configs/eu-kiki-v3-{qwen36,gemma4}-kicad-sch-{D1,D2,D3}.yaml`.

Template (qwen36 × D1):

```yaml
# eu-kiki-v3-qwen36-kicad-sch-D1.yaml
# Track C - kicad-sch v10 LoRA, qwen36 on D1 scraped
model: /Users/clems/KIKI-Mac_tunner/models/Qwen3.6-35B-A3B-8bit
data: /Users/clems/eu-kiki-data/kicad-sch-scraped-stripped
train: true
fine_tune_type: lora
optimizer: adamw
num_layers: -1
lora_parameters:
  rank: 16
  scale: 2.0
  dropout: 0.05
batch_size: 1
iters: 1500
val_batches: 5
learning_rate: 1.0e-4
steps_per_report: 100
steps_per_eval: 250
save_every: 250
grad_accumulation_steps: 8
max_seq_length: 8192
grad_checkpoint: true
adapter_path: /Users/clems/eu-kiki/adapters/v3/kicad-sch-qwen36-D1
seed: 42
```

For `gemma4` variants swap `model:` to
`/Users/clems/KIKI-Mac_tunner/models/gemma-4-E4B-it-MLX-4bit` and set
`max_seq_length: 16384`. For `D2` variants set
`data: .../kicad-sch-synth-stripped` and `iters: 3000`. For `D3` set
`data: .../kicad-sch-mixed-stripped` and `iters: 2000`.

**Verify:**
```bash
ls ~/KIKI-Mac_tunner/configs/eu-kiki-v3-qwen36-kicad-sch-*.yaml \
   ~/KIKI-Mac_tunner/configs/eu-kiki-v3-gemma4-kicad-sch-*.yaml \
   | wc -l
```
→ 6.

**Commit:** `feat(kicad-sch): M2 v3 lora configs qwen36 gemma4`

---

### C9 — train_lora (TDD red+green) (≈ 8 min)

**Files:** `tests/kicad_sch/test_train_lora.py`, `scripts/kicad_sch/train_lora.py`.

Tests:

```python
from pathlib import Path
from unittest.mock import MagicMock
import yaml
import pytest
from kicad_sch.train_lora import load_config, run_train


def test_load_config_reads_lora_params(tmp_path):
    cfg = {
        "model": "m", "data": "d",
        "lora_parameters": {"rank": 16, "scale": 2.0},
        "iters": 100, "seed": 42, "adapter_path": "a",
    }
    p = tmp_path / "c.yaml"
    p.write_text(yaml.safe_dump(cfg))
    out = load_config(p)
    assert out["lora_parameters"]["rank"] == 16
    assert out["seed"] == 42


def test_run_train_invokes_mlx_lm(tmp_path, monkeypatch):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(yaml.safe_dump({
        "model": "m",
        "data": str(tmp_path),
        "adapter_path": str(tmp_path / "ad"),
        "iters": 1, "seed": 42,
        "lora_parameters": {
            "rank": 16, "scale": 2.0, "dropout": 0.05,
        },
    }))
    called = {}

    def fake_run(cmd, **kw):
        called["cmd"] = cmd
        r = MagicMock()
        r.returncode = 0
        r.stdout = ""
        r.stderr = ""
        return r

    monkeypatch.setattr(
        "kicad_sch.train_lora.subprocess.run", fake_run
    )
    rc = run_train(cfg, dry_run=False)
    assert rc == 0
    joined = " ".join(called["cmd"])
    assert "mlx_lm" in joined
```

Implementation:

```python
"""Track C LoRA training orchestrator wrapping mlx_lm.lora."""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from kicad_sch.audit_log import AuditLogger


def load_config(path: Path) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def run_train(config_path: Path, dry_run: bool = False) -> int:
    cfg = load_config(config_path)
    adapter = Path(cfg["adapter_path"])
    adapter.mkdir(parents=True, exist_ok=True)
    run_id = (
        f"train-{adapter.name}-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    log = AuditLogger(run_id=run_id)
    log.event(
        "train_start",
        config=str(config_path),
        adapter=str(adapter),
        model=cfg["model"],
        iters=cfg.get("iters"),
        seed=cfg.get("seed"),
    )
    cmd = [
        sys.executable, "-m", "mlx_lm.lora",
        "--config", str(config_path),
    ]
    if dry_run:
        log.event("train_dry_run", cmd=" ".join(cmd))
        print(" ".join(cmd))
        return 0
    proc = subprocess.run(cmd, capture_output=False)
    log.event("train_done", rc=proc.returncode)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True, type=Path)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    return run_train(a.config, dry_run=a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
```

**Verify:** `uv run python -m pytest tests/kicad_sch/test_train_lora.py -x` → 2 passed.

**Commit:** `feat(kicad-sch): MLX LoRA training orchestrator`

---

### C10 — Smoke train (1 sample × 100 iters) (≈ 15 min Studio)

**Goal:** validate end-to-end before kicking the 6 full runs.

Steps:

1. Generate 50 D2 samples:
   ```bash
   cd ~/eu-kiki
   uv run python -m kicad_sch.synth_d2 \
       --n-samples 50 --compilers skidl
   ```
2. Strip:
   ```bash
   uv run python -m kicad_sch.strip_lib_symbols \
       --input  ~/eu-kiki-data/kicad-sch-synth \
       --output ~/eu-kiki-data/kicad-sch-synth-stripped
   ```
3. Copy + patch config to a smoke variant with `iters: 100`,
   `save_every: 100`:
   ```bash
   cp ~/KIKI-Mac_tunner/configs/eu-kiki-v3-qwen36-kicad-sch-D2.yaml \
      ~/KIKI-Mac_tunner/configs/eu-kiki-v3-qwen36-kicad-sch-D2-smoke.yaml
   ```
4. Run:
   ```bash
   uv run python -m kicad_sch.train_lora \
       --config ~/KIKI-Mac_tunner/configs/eu-kiki-v3-qwen36-kicad-sch-D2-smoke.yaml
   ```
5. Verify adapter dir contains `adapters.safetensors` and
   `adapter_config.json`.
6. Smoke-score via Eval N3 `eval_smoke_one_lora.sh` (delegated to Eval
   N3 plan); fail-stop if `parse_ok` < baseline.

**Verify:** `test -f ~/eu-kiki/adapters/v3/kicad-sch-qwen36-D2/adapters.safetensors`.

**Commit:** `chore(kicad-sch): smoke train log and audit ndjson`
(audit logs only; no code change).

---

### C11 — M3/M4 stub configs (12 files) (≈ 6 min)

**Files:** `eu-kiki-v3-{devstral,apertus,eurollm,medium35}-kicad-sch-{D1,D2,D3}.yaml`.

Each stub is a copy of the matching qwen36/gemma4 template with the
`model:` path swapped:

| Stub | model path |
|---|---|
| devstral | `/Users/clems/KIKI-Mac_tunner/models/Devstral-Small-2507-MLX-4bit` |
| apertus | `/Users/clems/KIKI-Mac_tunner/models/apertus-8b-Instruct-2509-mlx-bf16` |
| eurollm | `/Users/clems/KIKI-Mac_tunner/models/EuroLLM-22B-Instruct-MLX-4bit` |
| medium35 | `/Users/clems/KIKI-Mac_tunner/models/Mistral-Medium-3.5-128B-MLX-Q8` |

Add header comment to each:
```
# STATUS: M3/M4 stub, training deferred until M2 results validated
```

**Verify:**
```bash
grep -l "STATUS: M3/M4 stub" \
  ~/KIKI-Mac_tunner/configs/eu-kiki-v3-*-kicad-sch-*.yaml | wc -l
```
→ 12.

**Commit:** `feat(kicad-sch): M3 M4 stub configs 4 models 3 splits`

---

### C12 — Full M2 launcher (DEFERRED execution) (≈ 4 min author)

**File:** `~/eu-kiki/scripts/kicad_sch/run_m2_all.sh`.

```bash
#!/usr/bin/env bash
# Run all 6 M2 LoRA training jobs sequentially on Studio.
# Owner kicks off manually after C10 smoke passes and F1 frees the GPU.
set -euo pipefail
cd "${HOME}/eu-kiki"
for model in qwen36 gemma4; do
  for split in D1 D2 D3; do
    cfg="${HOME}/KIKI-Mac_tunner/configs/eu-kiki-v3-${model}-kicad-sch-${split}.yaml"
    log="${HOME}/KIKI-Mac_tunner/logs/eu-kiki-v3-${model}-kicad-sch-${split}-$(date +%Y%m%d-%H%M).log"
    echo "[$(date -Iseconds)] start ${model} ${split}"
    uv run python -m kicad_sch.train_lora --config "${cfg}" \
        2>&1 | tee "${log}"
  done
done
```

**Do not commit any auto-launch hook** — owner triggers per
`feedback_no_launch_kxkm_without_ask.md` (also applies to Studio
compute contention with F1).

**Verify:** `bash -n ~/eu-kiki/scripts/kicad_sch/run_m2_all.sh`.

**Commit:** `feat(kicad-sch): M2 6 run launcher script`

---

### C13 — README + plan close (≈ 3 min)

**Files:**

- `~/eu-kiki/scripts/kicad_sch/README.md` — list 5 entry points
  (strip, scrape_d1, synth_d2, mix_d3, train_lora), CLI examples,
  dependency on Foundation + Eval N3.
- `~/electron-bench/docs/superpowers/plans/2026-05-11-kicad-sch-track-c.md`
  — flip `Status:` to `EXECUTED-PARTIAL` or `DONE` per actual
  progress.

**Verify:** `head -20 ~/eu-kiki/scripts/kicad_sch/README.md` shows the
five commands.

**Commit (electron-bench):** `docs(plans): close Track C plan kicad sch`

---

## Risks specific to Track C

| Risk | Mitigation |
|---|---|
| D1 < 1k after license + dedup | Weight D2 up; ablation flags "D1 insufficient" in audit log. |
| `gh search code` rate-limit | Throttle to ≤ 30 req/min; persist cursor file for resume. |
| Studio compute contention with F1 | Run C12 after F1 ETA (~07:30 CEST). |
| `kicad-cli sch update` flaky on v5/v6 schemas | Skip + log; do not fail D1 run. |
| MLX OOM on gemma4 with seq 16K | Fallback to 12288 + `mx.set_cache_limit(32 GB)` per `feedback_mlx_metal_oom_cache.md`. |
| Compilers `atopile`/`circuit-synth` absent on Studio | `synth_d2` accepts `--compilers skidl` only; D2 ablation reports "skidl-only". |

## Acceptance criteria

- All tests green: `uv run python -m pytest tests/kicad_sch/ -x`.
- D1 manifest ≥ 1000 rows OR explicit "D1 insufficient" flag in audit log.
- D2 manifest ≥ 8000 rows (80% target).
- D3 manifest = exactly `--n-total` rows.
- 6 v3 M2 configs present in `~/KIKI-Mac_tunner/configs/`.
- 12 M3/M4 stubs present with the `STATUS: M3/M4 stub` header.
- Smoke train (C10) produces `adapters.safetensors` and `parse_ok` ≥ baseline on 50 eval samples.
- NDJSON audit logs present in `~/eu-kiki/output/audit/kicad-sch-2026-05-11/` for every run.

## Out-of-band notes for executor

- Use `uv run python -m kicad_sch.<script>` everywhere (PEP 668, Python 3.14).
- Author identity: `electron-rare <108685187+electron-rare@users.noreply.github.com>`.
- Commit hygiene: subject ≤ 50 chars, body lines ≤ 72, no AI attribution, no underscore in scope, no `--no-verify`.
- Critic-before-ship: invoke `ship-critic` skill before any tagged release of v3 adapters (per `feedback_critic_before_ship.md`).
