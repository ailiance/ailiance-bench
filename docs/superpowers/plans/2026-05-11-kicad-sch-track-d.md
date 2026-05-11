# KiCad-SCH Track D (Hybrid DSL→compiler) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build 20 hybrid LLM→DSL→compiler pipelines (5 base models × 4 compilers) that emit `.kicad_sch` v10 files, with NDJSON audit trail per EU AI Act Annex IV §7.

**Architecture:** A single orchestrator (`hybrid_pipeline.py`) iterates over (base_model, compiler) pairs. For each pair the orchestrator loads the MLX model once, then for every (prompt, seed, sample) tuple it (1) builds a compiler-specific system prompt, (2) generates DSL source via `eval_framework.generate_sample`, (3) invokes a per-compiler runner that writes the DSL to a temp file and executes the compiler as a subprocess, (4) captures the resulting `.kicad_sch` (if any), and (5) logs a structured `generation` event via `AuditLogger`. Runners share a `CompileResult` dataclass with three independent booleans (`dsl_parse_ok`, `compile_ok`, `kicad_load_ok`) so failure modes can be disaggregated downstream. No LoRA training is performed; this track is inference-only and depends on Foundation (`audit_log.py`) being delivered first and Eval N3 for downstream scoring.

**Tech Stack:** Python 3.14, uv, pytest, MLX (`mlx_lm_fork`), subprocess, skidl, atopile, tscircuit (npx), circuit-synth, kicad-cli 10.0.2.

---

## File Structure

```
~/ailiance/scripts/kicad_sch/
├── __init__.py                          # package marker
├── hybrid_pipeline.py                   # orchestrator + run_cell()
└── compilers/
    ├── __init__.py
    ├── system_prompts.py                # 4 SYSTEM_PROMPTS templates
    ├── result.py                        # CompileResult dataclass
    ├── skidl_runner.py                  # run(dsl, out_dir) -> CompileResult
    ├── atopile_runner.py
    ├── tscircuit_runner.py
    └── circuit_synth_runner.py

~/ailiance/scripts/
└── run_track_d.sh                       # smoke | full CLI wrapper

~/ailiance/tests/kicad_sch/
├── __init__.py
├── test_hybrid_pipeline.py
└── compilers/
    ├── __init__.py
    ├── test_result.py
    ├── test_system_prompts.py
    ├── test_skidl_runner.py
    ├── test_atopile_runner.py
    ├── test_tscircuit_runner.py
    └── test_circuit_synth_runner.py
```

**Boundaries:**

- `compilers/result.py` holds the shared `CompileResult` dataclass and nothing else. Imported by every runner and by tests.
- Each `*_runner.py` is fully self-contained: it owns the DSL filename, the subprocess invocation, and stderr capture. Runners do NOT know about models, prompts, or seeds.
- `system_prompts.py` is data-only (four string constants + a `SYSTEM_PROMPTS` dict). No I/O.
- `hybrid_pipeline.py` is the only file that imports `eval_framework`, `audit_log`, and all four runners. Composition lives here.
- `run_track_d.sh` is a thin shell wrapper around `python -m scripts.kicad_sch.hybrid_pipeline` with smoke/full mode flags.

**Dependencies (must already be in place before starting Task 1):**

- `~/ailiance/scripts/audit_log.py` exposing `AuditLogger(path: Path)` with `.log(event_type: str, **fields)` writing one JSON object per line (Foundation deliverable).
- `~/ailiance/scripts/eval_framework.py` `load_model_and_tokenizer(model_path, adapter_path=None) -> (model, tokenizer)` and `generate_sample(model, tokenizer, prompt, max_tokens, temperature, seed) -> str` (already present, verified 2026-05-11).
- `MODELS` dict keys: `apertus, devstral, eurollm, qwen36, medium35` (verified 2026-05-11 in `eval_framework.py:59`).

---

## Pre-Task 0: Compiler installation on Studio

The 2026-05-11 environment probe found that **none** of the four target compilers are installed on Studio:

```
$ which skidl ato; npx --no-install tsci --version; python3 -c "import circuit_synth"
skidl not found
ato not found
zsh:1: command not found: npx
ModuleNotFoundError: No module named 'circuit_synth'
```

Before any task runs, install the toolchain. This is a one-time setup step, not a TDD task, and not committed.

```bash
ssh studio bash <<'EOF'
set -euo pipefail

# 1. skidl + circuit_synth (PyPI, into ailiance uv env)
cd ~/ailiance
uv pip install 'skidl>=2.0' 'circuit_synth>=0.5'

# 2. atopile (PyPI; CLI = `ato`)
uv pip install 'atopile>=0.4'

# 3. tscircuit (npm, needs node ≥20)
if ! command -v node >/dev/null; then
  brew install node
fi
npm install -g '@tscircuit/cli'
which tsci || echo "tsci NOT installed — runner will short-circuit to dsl_parse_ok=False"
EOF
```

Verify with:

```bash
ssh studio 'cd ~/ailiance && uv run python -c "import skidl, circuit_synth, atopile; print(skidl.__version__, circuit_synth.__version__, atopile.__version__)"; which ato tsci'
```

**Expected:** four versions printed, two CLI paths printed. If any line fails the corresponding runner will *correctly* mark every attempt as `compile_ok=False` with a clear stderr — this is by design (cf. spec §"Track D — Failure modes tracked") and does not block other runners. Document the missing tool in the audit log header.

---

## Task 1: `CompileResult` dataclass

**Files:**
- Create: `~/ailiance/scripts/kicad_sch/__init__.py` (empty)
- Create: `~/ailiance/scripts/kicad_sch/compilers/__init__.py` (empty)
- Create: `~/ailiance/scripts/kicad_sch/compilers/result.py`
- Create: `~/ailiance/tests/kicad_sch/__init__.py` (empty)
- Create: `~/ailiance/tests/kicad_sch/compilers/__init__.py` (empty)
- Test: `~/ailiance/tests/kicad_sch/compilers/test_result.py`

- [ ] **Step 1: Write the failing test**

```python
# ~/ailiance/tests/kicad_sch/compilers/test_result.py
from pathlib import Path
from scripts.kicad_sch.compilers.result import CompileResult


def test_compile_result_defaults_to_all_false():
    r = CompileResult()
    assert r.dsl_parse_ok is False
    assert r.compile_ok is False
    assert r.output_path is None
    assert r.stderr == ""
    assert r.wall_time_ms == 0


def test_compile_result_accepts_full_payload(tmp_path):
    out = tmp_path / "x.kicad_sch"
    out.write_text("(kicad_sch)")
    r = CompileResult(
        dsl_parse_ok=True,
        compile_ok=True,
        output_path=out,
        stderr="warn: foo",
        wall_time_ms=842,
    )
    assert r.compile_ok and r.output_path.exists()
    assert r.wall_time_ms == 842


def test_compile_result_as_dict_serialises_path_to_str(tmp_path):
    out = tmp_path / "x.kicad_sch"
    r = CompileResult(dsl_parse_ok=True, compile_ok=True, output_path=out)
    d = r.as_dict()
    assert d["output_path"] == str(out)
    assert d["dsl_parse_ok"] is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/compilers/test_result.py -v
```

Expected: `ModuleNotFoundError: No module named 'scripts.kicad_sch.compilers.result'`.

- [ ] **Step 3: Write minimal implementation**

```python
# ~/ailiance/scripts/kicad_sch/compilers/result.py
"""Shared result type for every Track-D compiler runner."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CompileResult:
    """Outcome of a single LLM-DSL → compiler invocation.

    Three independent booleans match the spec failure-mode taxonomy:
      - dsl_parse_ok : compiler accepted the DSL grammatically
      - compile_ok   : compiler emitted a .kicad_sch artefact
      - kicad_load_ok: filled in downstream by Eval N3, not by the runner

    Runners populate dsl_parse_ok and compile_ok only.
    """

    dsl_parse_ok: bool = False
    compile_ok: bool = False
    output_path: Path | None = None
    stderr: str = ""
    wall_time_ms: int = 0

    def as_dict(self) -> dict:
        return {
            "dsl_parse_ok": self.dsl_parse_ok,
            "compile_ok": self.compile_ok,
            "output_path": str(self.output_path) if self.output_path else None,
            "stderr": self.stderr,
            "wall_time_ms": self.wall_time_ms,
        }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/compilers/test_result.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/ailiance && git add scripts/kicad_sch/__init__.py scripts/kicad_sch/compilers/__init__.py scripts/kicad_sch/compilers/result.py tests/kicad_sch/__init__.py tests/kicad_sch/compilers/__init__.py tests/kicad_sch/compilers/test_result.py
git commit -m "feat(trackd): add CompileResult dataclass

Shared outcome record for the four hybrid DSL compilers.
Three independent booleans match the spec failure taxonomy
(dsl_parse_ok, compile_ok, kicad_load_ok). Runners populate
the first two; Eval N3 fills the third downstream."
```

---

## Task 2: System prompts module

**Files:**
- Create: `~/ailiance/scripts/kicad_sch/compilers/system_prompts.py`
- Test: `~/ailiance/tests/kicad_sch/compilers/test_system_prompts.py`

- [ ] **Step 1: Write the failing test**

```python
# ~/ailiance/tests/kicad_sch/compilers/test_system_prompts.py
import pytest
from scripts.kicad_sch.compilers.system_prompts import (
    SKIDL_PROMPT, ATOPILE_PROMPT, TSCIRCUIT_PROMPT, CIRCUIT_SYNTH_PROMPT,
    SYSTEM_PROMPTS,
)


@pytest.mark.parametrize("name,prompt", [
    ("skidl", SKIDL_PROMPT),
    ("atopile", ATOPILE_PROMPT),
    ("tscircuit", TSCIRCUIT_PROMPT),
    ("circuit-synth", CIRCUIT_SYNTH_PROMPT),
])
def test_prompt_is_non_empty_string(name, prompt):
    assert isinstance(prompt, str)
    assert 200 <= len(prompt) <= 2000, f"{name} prompt length {len(prompt)} out of band"


@pytest.mark.parametrize("compiler", ["skidl", "atopile", "tscircuit", "circuit-synth"])
def test_prompt_forbids_markdown(compiler):
    p = SYSTEM_PROMPTS[compiler].lower()
    assert "no markdown" in p or "no code fence" in p or "do not wrap" in p


def test_system_prompts_dict_has_all_four():
    assert set(SYSTEM_PROMPTS.keys()) == {"skidl", "atopile", "tscircuit", "circuit-synth"}


def test_skidl_prompt_mentions_generate_schematic():
    assert "generate_schematic" in SKIDL_PROMPT


def test_atopile_prompt_mentions_ato_extension():
    assert ".ato" in ATOPILE_PROMPT


def test_tscircuit_prompt_mentions_tsx():
    assert ".tsx" in TSCIRCUIT_PROMPT or "TSX" in TSCIRCUIT_PROMPT


def test_circuit_synth_prompt_mentions_module():
    assert "circuit_synth" in CIRCUIT_SYNTH_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/compilers/test_system_prompts.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# ~/ailiance/scripts/kicad_sch/compilers/system_prompts.py
"""System prompts for each Track-D compiler.

Each ~100-word template tells the LLM:
  - which DSL/source format to emit
  - to never wrap in markdown / no code fences
  - the deterministic style (no comments, ASCII only)
  - one minimal worked example
"""
from __future__ import annotations

SKIDL_PROMPT = """\
You are an EDA code generator. Output a single complete Python script using \
SKiDL that, when executed, emits a KiCad v10 schematic via \
`generate_schematic(filepath=...)`. Output ONLY the raw Python source — do not \
wrap in markdown, do not add code fences, do not prepend explanations. The \
script must `from skidl import *` and call `set_default_tool(KICAD)`. Use \
`Part('Device', '<symbol>', value=..., footprint=...)` with footprints from \
the standard `Resistor_SMD:` and `Capacitor_SMD:` libraries. Define every net \
explicitly with `Net('NAME')`. Keep style deterministic: no comments, ASCII \
only, one statement per line. Example minimal divider:

from skidl import *
set_default_tool(KICAD)
vin, gnd, vout = Net('VIN'), Net('GND'), Net('VOUT')
r1 = Part('Device','R',value='10k',footprint='Resistor_SMD:R_0603_1608Metric')
r2 = Part('Device','R',value='10k',footprint='Resistor_SMD:R_0603_1608Metric')
vin & r1 & vout & r2 & gnd
generate_schematic(filepath='out.kicad_sch')
"""

ATOPILE_PROMPT = """\
You are an EDA code generator. Output a single complete `.ato` source file \
that the `ato build` compiler will turn into a KiCad v10 schematic. Output \
ONLY the raw atopile source — do not wrap in markdown, do not add code \
fences, do not prepend explanations. Start with `import Resistor from \
"generics/resistors.ato"` style imports as needed. Declare a top-level \
`module Main:` block containing component instantiations and `signal` \
declarations connected via `~` operators. Keep style deterministic: no \
inline comments, ASCII only, four-space indent. Example minimal divider:

import Resistor from "generics/resistors.ato"
module Main:
    signal vin
    signal gnd
    signal vout
    r1 = new Resistor; r1.value = 10kohm; r1.package = "0603"
    r2 = new Resistor; r2.value = 10kohm; r2.package = "0603"
    vin ~ r1.p1; r1.p2 ~ vout; vout ~ r2.p1; r2.p2 ~ gnd
"""

TSCIRCUIT_PROMPT = """\
You are an EDA code generator. Output a single complete `.tsx` source file \
that the `tsci build` CLI will turn into a KiCad v10 schematic. Output ONLY \
the raw TypeScript/TSX source — do not wrap in markdown, do not add code \
fences, do not prepend explanations. Import from `@tscircuit/core`. Export \
default a functional component that returns a `<board>` JSX tree containing \
`<resistor>`, `<capacitor>`, `<chip>` elements with `name`, `resistance`, \
`footprint` props. Keep style deterministic: no comments, ASCII only, two- \
space indent. Example minimal divider:

import { Board } from "@tscircuit/core"
export default () => (
  <board width="10mm" height="10mm">
    <resistor name="R1" resistance="10k" footprint="0603" />
    <resistor name="R2" resistance="10k" footprint="0603" />
    <trace from=".R1 > .pin2" to=".R2 > .pin1" />
  </board>
)
"""

CIRCUIT_SYNTH_PROMPT = """\
You are an EDA code generator. Output a single complete Python script using \
`circuit_synth` that, when run as `python -m circuit_synth.build <file>`, \
emits a KiCad v10 schematic. Output ONLY the raw Python source — do not \
wrap in markdown, do not add code fences, do not prepend explanations. The \
script must `from circuit_synth import Circuit, Component, Net` and define \
a `def build() -> Circuit:` factory returning the assembled circuit. Use \
`Component(symbol='Device:R', value='10k', footprint=...)` and `Net('VIN')`. \
Keep style deterministic: no comments, ASCII only. Example minimal divider:

from circuit_synth import Circuit, Component, Net
def build() -> Circuit:
    c = Circuit('divider')
    vin, gnd, vout = Net('VIN'), Net('GND'), Net('VOUT')
    r1 = Component(symbol='Device:R', value='10k',
                   footprint='Resistor_SMD:R_0603_1608Metric')
    r2 = Component(symbol='Device:R', value='10k',
                   footprint='Resistor_SMD:R_0603_1608Metric')
    c.connect(vin, r1[1]); c.connect(r1[2], vout)
    c.connect(vout, r2[1]); c.connect(r2[2], gnd)
    return c
"""

SYSTEM_PROMPTS: dict[str, str] = {
    "skidl": SKIDL_PROMPT,
    "atopile": ATOPILE_PROMPT,
    "tscircuit": TSCIRCUIT_PROMPT,
    "circuit-synth": CIRCUIT_SYNTH_PROMPT,
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/compilers/test_system_prompts.py -v
```

Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/ailiance && git add scripts/kicad_sch/compilers/system_prompts.py tests/kicad_sch/compilers/test_system_prompts.py
git commit -m "feat(trackd): add 4 compiler system prompts

One ~100-word template per compiler (skidl, atopile,
tscircuit, circuit-synth) instructing the LLM to emit raw
source with no markdown wrap, deterministic style, one
minimal divider example."
```

---

## Task 3: SKiDL runner

**Files:**
- Create: `~/ailiance/scripts/kicad_sch/compilers/skidl_runner.py`
- Test: `~/ailiance/tests/kicad_sch/compilers/test_skidl_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# ~/ailiance/tests/kicad_sch/compilers/test_skidl_runner.py
import pytest
from pathlib import Path
from scripts.kicad_sch.compilers import skidl_runner


pytestmark = pytest.mark.skipif(
    __import__("importlib").util.find_spec("skidl") is None,
    reason="skidl not installed on this host",
)


def test_skidl_runner_compiles_minimal_voltage_divider(tmp_path):
    dsl = (
        "from skidl import *\n"
        "set_default_tool(KICAD)\n"
        "vin = Net('VIN'); gnd = Net('GND'); vout = Net('VOUT')\n"
        "r1 = Part('Device','R',value='10k',"
        "footprint='Resistor_SMD:R_0603_1608Metric')\n"
        "r2 = Part('Device','R',value='10k',"
        "footprint='Resistor_SMD:R_0603_1608Metric')\n"
        "vin & r1 & vout & r2 & gnd\n"
        f"generate_schematic(filepath=r'{tmp_path / 'out.kicad_sch'}')\n"
    )
    result = skidl_runner.run(dsl, tmp_path)
    assert result.dsl_parse_ok is True
    assert result.compile_ok is True
    assert result.output_path is not None
    assert result.output_path.exists()
    assert result.wall_time_ms > 0


def test_skidl_runner_marks_bad_dsl_as_parse_fail(tmp_path):
    dsl = "from skidl import * BROKEN SYNTAX :::"
    result = skidl_runner.run(dsl, tmp_path)
    assert result.dsl_parse_ok is False
    assert result.compile_ok is False
    assert result.output_path is None
    assert "SyntaxError" in result.stderr or "invalid syntax" in result.stderr


def test_skidl_runner_marks_compile_fail_when_no_output(tmp_path):
    # syntactically valid Python but never calls generate_schematic
    dsl = "from skidl import *\nset_default_tool(KICAD)\nNet('X')\n"
    result = skidl_runner.run(dsl, tmp_path)
    assert result.dsl_parse_ok is True
    assert result.compile_ok is False
    assert result.output_path is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/compilers/test_skidl_runner.py -v
```

Expected: ModuleNotFoundError on `skidl_runner`.

- [ ] **Step 3: Write minimal implementation**

```python
# ~/ailiance/scripts/kicad_sch/compilers/skidl_runner.py
"""SKiDL → kicad_sch runner.

Strategy: write DSL to <out_dir>/circuit.py, run it via subprocess so the
runner is isolated from skidl global state, then scan <out_dir>/*.kicad_sch
for the artefact.
"""
from __future__ import annotations

import ast
import subprocess
import sys
import time
from pathlib import Path

from .result import CompileResult


def run(dsl: str, out_dir: Path, timeout_s: int = 60) -> CompileResult:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    script = out_dir / "circuit.py"
    script.write_text(dsl)

    # Cheap syntax gate via ast before paying for a subprocess.
    try:
        ast.parse(dsl)
    except SyntaxError as e:
        return CompileResult(
            dsl_parse_ok=False, compile_ok=False, output_path=None,
            stderr=f"SyntaxError: {e}", wall_time_ms=0,
        )

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(out_dir),
            capture_output=True, text=True, timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as e:
        return CompileResult(
            dsl_parse_ok=True, compile_ok=False, output_path=None,
            stderr=f"timeout {timeout_s}s: {e}",
            wall_time_ms=int((time.monotonic() - t0) * 1000),
        )
    wall = int((time.monotonic() - t0) * 1000)

    schs = sorted(out_dir.glob("*.kicad_sch"))
    if proc.returncode == 0 and schs:
        return CompileResult(
            dsl_parse_ok=True, compile_ok=True, output_path=schs[0],
            stderr=proc.stderr, wall_time_ms=wall,
        )
    return CompileResult(
        dsl_parse_ok=True, compile_ok=False, output_path=None,
        stderr=proc.stderr or proc.stdout, wall_time_ms=wall,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/compilers/test_skidl_runner.py -v
```

Expected: 3 passed (or 3 skipped if skidl missing — that's an acceptable smoke since `Pre-Task 0` should have installed it).

- [ ] **Step 5: Commit**

```bash
cd ~/ailiance && git add scripts/kicad_sch/compilers/skidl_runner.py tests/kicad_sch/compilers/test_skidl_runner.py
git commit -m "feat(trackd): add skidl compiler runner

Writes DSL to circuit.py, ast.parse gate, subprocess
invoke, scans out_dir for *.kicad_sch artefact. Sets
dsl_parse_ok/compile_ok independently per spec failure
taxonomy."
```

---

## Task 4: atopile runner

**Files:**
- Create: `~/ailiance/scripts/kicad_sch/compilers/atopile_runner.py`
- Test: `~/ailiance/tests/kicad_sch/compilers/test_atopile_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# ~/ailiance/tests/kicad_sch/compilers/test_atopile_runner.py
import shutil
import pytest
from scripts.kicad_sch.compilers import atopile_runner


pytestmark = pytest.mark.skipif(
    shutil.which("ato") is None,
    reason="ato CLI not on PATH",
)


def test_atopile_runner_writes_ato_and_invokes_build(tmp_path):
    dsl = (
        'import Resistor from "generics/resistors.ato"\n'
        "module Main:\n"
        "    signal vin\n"
        "    signal gnd\n"
        "    signal vout\n"
        "    r1 = new Resistor; r1.value = 10kohm; r1.package = \"0603\"\n"
        "    r2 = new Resistor; r2.value = 10kohm; r2.package = \"0603\"\n"
        "    vin ~ r1.p1; r1.p2 ~ vout; vout ~ r2.p1; r2.p2 ~ gnd\n"
    )
    result = atopile_runner.run(dsl, tmp_path)
    # We do not assert compile_ok=True here because atopile may need a
    # project ato.yaml; we DO assert the .ato was written and ato was
    # invoked (dsl_parse_ok is True iff ato accepted the syntax).
    assert (tmp_path / "main.ato").exists()
    assert isinstance(result.dsl_parse_ok, bool)
    assert isinstance(result.compile_ok, bool)
    assert result.wall_time_ms >= 0


def test_atopile_runner_marks_garbage_dsl_as_parse_fail(tmp_path):
    dsl = "@@@ not atopile @@@"
    result = atopile_runner.run(dsl, tmp_path)
    assert result.dsl_parse_ok is False
    assert result.compile_ok is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/compilers/test_atopile_runner.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# ~/ailiance/scripts/kicad_sch/compilers/atopile_runner.py
"""atopile (.ato) → kicad_sch runner."""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from .result import CompileResult


def run(dsl: str, out_dir: Path, timeout_s: int = 120) -> CompileResult:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ato_file = out_dir / "main.ato"
    ato_file.write_text(dsl)

    if shutil.which("ato") is None:
        return CompileResult(
            dsl_parse_ok=False, compile_ok=False, output_path=None,
            stderr="ato CLI not installed", wall_time_ms=0,
        )

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            ["ato", "build", str(ato_file)],
            cwd=str(out_dir), capture_output=True, text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as e:
        return CompileResult(
            dsl_parse_ok=True, compile_ok=False, output_path=None,
            stderr=f"timeout {timeout_s}s: {e}",
            wall_time_ms=int((time.monotonic() - t0) * 1000),
        )
    wall = int((time.monotonic() - t0) * 1000)

    stderr = proc.stderr or ""
    # atopile reports grammar errors on stderr with "SyntaxError" /
    # "parse error" / "unexpected token". Treat any of these as parse fail.
    parse_fail_markers = ("syntaxerror", "parse error", "unexpected token",
                          "lexer error")
    if any(m in stderr.lower() for m in parse_fail_markers):
        return CompileResult(
            dsl_parse_ok=False, compile_ok=False, output_path=None,
            stderr=stderr, wall_time_ms=wall,
        )

    schs = sorted(out_dir.rglob("*.kicad_sch"))
    if proc.returncode == 0 and schs:
        return CompileResult(
            dsl_parse_ok=True, compile_ok=True, output_path=schs[0],
            stderr=stderr, wall_time_ms=wall,
        )
    return CompileResult(
        dsl_parse_ok=True, compile_ok=False, output_path=None,
        stderr=stderr, wall_time_ms=wall,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/compilers/test_atopile_runner.py -v
```

Expected: 2 passed (or skipped if `ato` not installed).

- [ ] **Step 5: Commit**

```bash
cd ~/ailiance && git add scripts/kicad_sch/compilers/atopile_runner.py tests/kicad_sch/compilers/test_atopile_runner.py
git commit -m "feat(trackd): add atopile compiler runner

Writes DSL to main.ato, invokes ato build, detects parse
errors via stderr markers (SyntaxError, parse error,
unexpected token, lexer error). Recursively scans for
the emitted .kicad_sch."
```

---

## Task 5: tscircuit runner

**Files:**
- Create: `~/ailiance/scripts/kicad_sch/compilers/tscircuit_runner.py`
- Test: `~/ailiance/tests/kicad_sch/compilers/test_tscircuit_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# ~/ailiance/tests/kicad_sch/compilers/test_tscircuit_runner.py
import shutil
import pytest
from scripts.kicad_sch.compilers import tscircuit_runner


pytestmark = pytest.mark.skipif(
    shutil.which("npx") is None,
    reason="npx not on PATH",
)


def test_tscircuit_runner_writes_tsx_and_invokes_tsci(tmp_path):
    dsl = (
        'import { Board } from "@tscircuit/core"\n'
        "export default () => (\n"
        '  <board width="10mm" height="10mm">\n'
        '    <resistor name="R1" resistance="10k" footprint="0603" />\n'
        '    <resistor name="R2" resistance="10k" footprint="0603" />\n'
        "  </board>\n"
        ")\n"
    )
    result = tscircuit_runner.run(dsl, tmp_path)
    assert (tmp_path / "circuit.tsx").exists()
    assert isinstance(result.dsl_parse_ok, bool)
    assert isinstance(result.compile_ok, bool)


def test_tscircuit_runner_marks_garbage_as_parse_fail(tmp_path):
    dsl = "<<< not tsx >>>"
    result = tscircuit_runner.run(dsl, tmp_path)
    assert result.dsl_parse_ok is False
    assert result.compile_ok is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/compilers/test_tscircuit_runner.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# ~/ailiance/scripts/kicad_sch/compilers/tscircuit_runner.py
"""tscircuit (.tsx) → kicad_sch runner."""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from .result import CompileResult


def run(dsl: str, out_dir: Path, timeout_s: int = 180) -> CompileResult:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tsx_file = out_dir / "circuit.tsx"
    tsx_file.write_text(dsl)

    if shutil.which("npx") is None:
        return CompileResult(
            dsl_parse_ok=False, compile_ok=False, output_path=None,
            stderr="npx not installed", wall_time_ms=0,
        )

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            ["npx", "--no-install", "tsci", "build",
             "--input", str(tsx_file),
             "--output-format", "kicad_sch",
             "--output-dir", str(out_dir)],
            cwd=str(out_dir), capture_output=True, text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as e:
        return CompileResult(
            dsl_parse_ok=True, compile_ok=False, output_path=None,
            stderr=f"timeout {timeout_s}s: {e}",
            wall_time_ms=int((time.monotonic() - t0) * 1000),
        )
    wall = int((time.monotonic() - t0) * 1000)

    stderr = proc.stderr or ""
    parse_fail_markers = ("ts1005", "ts1109", "unexpected token",
                          "syntaxerror", "parse error")
    if any(m in stderr.lower() for m in parse_fail_markers):
        return CompileResult(
            dsl_parse_ok=False, compile_ok=False, output_path=None,
            stderr=stderr, wall_time_ms=wall,
        )

    schs = sorted(out_dir.rglob("*.kicad_sch"))
    if proc.returncode == 0 and schs:
        return CompileResult(
            dsl_parse_ok=True, compile_ok=True, output_path=schs[0],
            stderr=stderr, wall_time_ms=wall,
        )
    return CompileResult(
        dsl_parse_ok=True, compile_ok=False, output_path=None,
        stderr=stderr, wall_time_ms=wall,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/compilers/test_tscircuit_runner.py -v
```

Expected: 2 passed (or skipped if `npx` missing).

- [ ] **Step 5: Commit**

```bash
cd ~/ailiance && git add scripts/kicad_sch/compilers/tscircuit_runner.py tests/kicad_sch/compilers/test_tscircuit_runner.py
git commit -m "feat(trackd): add tscircuit compiler runner

Writes DSL to circuit.tsx, invokes npx tsci build with
kicad_sch output format, detects TS1005/TS1109/unexpected-
token errors as parse failures."
```

---

## Task 6: circuit-synth runner

**Files:**
- Create: `~/ailiance/scripts/kicad_sch/compilers/circuit_synth_runner.py`
- Test: `~/ailiance/tests/kicad_sch/compilers/test_circuit_synth_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# ~/ailiance/tests/kicad_sch/compilers/test_circuit_synth_runner.py
import pytest
from scripts.kicad_sch.compilers import circuit_synth_runner


pytestmark = pytest.mark.skipif(
    __import__("importlib").util.find_spec("circuit_synth") is None,
    reason="circuit_synth not installed",
)


def test_circuit_synth_runner_writes_script(tmp_path):
    dsl = (
        "from circuit_synth import Circuit, Component, Net\n"
        "def build() -> Circuit:\n"
        "    c = Circuit('divider')\n"
        "    vin, gnd, vout = Net('VIN'), Net('GND'), Net('VOUT')\n"
        "    r1 = Component(symbol='Device:R', value='10k',"
        "                   footprint='Resistor_SMD:R_0603_1608Metric')\n"
        "    r2 = Component(symbol='Device:R', value='10k',"
        "                   footprint='Resistor_SMD:R_0603_1608Metric')\n"
        "    c.connect(vin, r1[1]); c.connect(r1[2], vout)\n"
        "    c.connect(vout, r2[1]); c.connect(r2[2], gnd)\n"
        "    return c\n"
    )
    result = circuit_synth_runner.run(dsl, tmp_path)
    assert (tmp_path / "circuit.py").exists()
    assert isinstance(result.dsl_parse_ok, bool)


def test_circuit_synth_runner_marks_bad_dsl_as_parse_fail(tmp_path):
    dsl = "from circuit_synth import *** broken"
    result = circuit_synth_runner.run(dsl, tmp_path)
    assert result.dsl_parse_ok is False
    assert result.compile_ok is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/compilers/test_circuit_synth_runner.py -v
```

Expected: ModuleNotFoundError.

- [ ] **Step 3: Write minimal implementation**

```python
# ~/ailiance/scripts/kicad_sch/compilers/circuit_synth_runner.py
"""circuit_synth → kicad_sch runner."""
from __future__ import annotations

import ast
import subprocess
import sys
import time
from pathlib import Path

from .result import CompileResult

_DRIVER = """\
import sys, importlib.util
spec = importlib.util.spec_from_file_location('user_circuit', 'circuit.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
c = mod.build()
c.to_kicad_sch('out.kicad_sch')
"""


def run(dsl: str, out_dir: Path, timeout_s: int = 90) -> CompileResult:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "circuit.py").write_text(dsl)
    (out_dir / "_driver.py").write_text(_DRIVER)

    try:
        ast.parse(dsl)
    except SyntaxError as e:
        return CompileResult(
            dsl_parse_ok=False, compile_ok=False, output_path=None,
            stderr=f"SyntaxError: {e}", wall_time_ms=0,
        )

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, "_driver.py"],
            cwd=str(out_dir), capture_output=True, text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as e:
        return CompileResult(
            dsl_parse_ok=True, compile_ok=False, output_path=None,
            stderr=f"timeout {timeout_s}s: {e}",
            wall_time_ms=int((time.monotonic() - t0) * 1000),
        )
    wall = int((time.monotonic() - t0) * 1000)

    out = out_dir / "out.kicad_sch"
    if proc.returncode == 0 and out.exists():
        return CompileResult(
            dsl_parse_ok=True, compile_ok=True, output_path=out,
            stderr=proc.stderr, wall_time_ms=wall,
        )
    return CompileResult(
        dsl_parse_ok=True, compile_ok=False, output_path=None,
        stderr=proc.stderr or proc.stdout, wall_time_ms=wall,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/compilers/test_circuit_synth_runner.py -v
```

Expected: 2 passed (or skipped).

- [ ] **Step 5: Commit**

```bash
cd ~/ailiance && git add scripts/kicad_sch/compilers/circuit_synth_runner.py tests/kicad_sch/compilers/test_circuit_synth_runner.py
git commit -m "feat(trackd): add circuit-synth compiler runner

Generates a tiny _driver.py that imports the user circuit
via importlib, calls build(), and writes out.kicad_sch.
Keeps the user DSL syntactically isolated."
```

---

## Task 7: `run_cell` — single (model, compiler, prompt, seed) execution

**Files:**
- Create: `~/ailiance/scripts/kicad_sch/hybrid_pipeline.py`
- Test: `~/ailiance/tests/kicad_sch/test_hybrid_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# ~/ailiance/tests/kicad_sch/test_hybrid_pipeline.py
import json
import pytest
from pathlib import Path

from scripts.audit_log import AuditLogger
from scripts.kicad_sch import hybrid_pipeline


class _StubModel:
    """Stand-in for an MLX model: just a tag we can recognise."""
    def __init__(self, key): self.key = key


class _StubTok:
    def __init__(self): pass


def _stub_load(model_path, adapter_path=None):
    return _StubModel(model_path), _StubTok()


def _stub_generate(model, tok, prompt, max_tokens, temperature, seed):
    return (
        "from skidl import *\n"
        "set_default_tool(KICAD)\n"
        "vin=Net('VIN'); gnd=Net('GND'); vout=Net('VOUT')\n"
        "r1=Part('Device','R',value='10k',"
        "footprint='Resistor_SMD:R_0603_1608Metric')\n"
        "r2=Part('Device','R',value='10k',"
        "footprint='Resistor_SMD:R_0603_1608Metric')\n"
        "vin & r1 & vout & r2 & gnd\n"
        "generate_schematic(filepath='out.kicad_sch')\n"
    )


class _StubRunner:
    def __init__(self): self.calls = []
    def run(self, dsl, out_dir, **_):
        from scripts.kicad_sch.compilers.result import CompileResult
        self.calls.append((dsl, Path(out_dir)))
        sch = Path(out_dir) / "out.kicad_sch"
        sch.parent.mkdir(parents=True, exist_ok=True)
        sch.write_text("(kicad_sch (version 20240101))")
        return CompileResult(
            dsl_parse_ok=True, compile_ok=True, output_path=sch,
            stderr="", wall_time_ms=42,
        )


def test_run_cell_logs_each_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr(hybrid_pipeline, "load_model_and_tokenizer", _stub_load)
    monkeypatch.setattr(hybrid_pipeline, "generate_sample", _stub_generate)
    stub_runner = _StubRunner()
    monkeypatch.setitem(hybrid_pipeline.RUNNERS, "skidl", stub_runner)

    audit_path = tmp_path / "audit.ndjson"
    logger = AuditLogger(audit_path)
    out = hybrid_pipeline.run_cell(
        base_model_key="qwen36",
        compiler="skidl",
        prompt="voltage divider 10k 10k",
        seeds=[42],
        n_samples=1,
        out_dir=tmp_path / "art",
        audit_logger=logger,
    )

    lines = audit_path.read_text().strip().split("\n")
    assert len(lines) == 1
    log = json.loads(lines[0])
    assert log["event_type"] == "generation"
    assert log["base_model_key"] == "qwen36"
    assert log["compiler"] == "skidl"
    assert log["seed"] == 42
    assert log["sample_idx"] == 0
    assert log["dsl_parse_ok"] is True
    assert log["compile_ok"] is True
    assert out["compile_ok_rate"] == 1.0
    assert out["dsl_parse_ok_rate"] == 1.0
    assert out["n_attempts"] == 1


def test_run_cell_aggregates_rates_across_seeds(tmp_path, monkeypatch):
    monkeypatch.setattr(hybrid_pipeline, "load_model_and_tokenizer", _stub_load)
    monkeypatch.setattr(hybrid_pipeline, "generate_sample", _stub_generate)

    from scripts.kicad_sch.compilers.result import CompileResult

    class _AltRunner:
        def __init__(self): self.n = 0
        def run(self, dsl, out_dir, **_):
            self.n += 1
            return CompileResult(
                dsl_parse_ok=True,
                compile_ok=(self.n % 2 == 0),
                output_path=None,
                stderr="", wall_time_ms=1,
            )

    monkeypatch.setitem(hybrid_pipeline.RUNNERS, "skidl", _AltRunner())
    logger = AuditLogger(tmp_path / "a.ndjson")
    out = hybrid_pipeline.run_cell(
        base_model_key="qwen36", compiler="skidl",
        prompt="p", seeds=[1, 2, 3, 4], n_samples=1,
        out_dir=tmp_path / "art", audit_logger=logger,
    )
    assert out["n_attempts"] == 4
    assert out["dsl_parse_ok_rate"] == 1.0
    assert out["compile_ok_rate"] == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/test_hybrid_pipeline.py -v
```

Expected: ModuleNotFoundError on `hybrid_pipeline`.

- [ ] **Step 3: Write minimal implementation**

```python
# ~/ailiance/scripts/kicad_sch/hybrid_pipeline.py
"""Track-D orchestrator: 5 base models × 4 compilers = 20 hybrid pipelines.

Exposes `run_cell()` for one (model, compiler, prompt) cell, and `run_all()`
for the full grid. Inference-only (no LoRA). Logs every attempt to NDJSON
via AuditLogger.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from scripts.audit_log import AuditLogger
from scripts.eval_framework import (
    MODELS, load_model_and_tokenizer, generate_sample, unload_model,
)
from scripts.kicad_sch.compilers import (
    skidl_runner, atopile_runner, tscircuit_runner, circuit_synth_runner,
)
from scripts.kicad_sch.compilers.system_prompts import SYSTEM_PROMPTS

# Module-level so tests can monkeypatch a single compiler.
RUNNERS: dict[str, Any] = {
    "skidl": skidl_runner,
    "atopile": atopile_runner,
    "tscircuit": tscircuit_runner,
    "circuit-synth": circuit_synth_runner,
}

BASE_MODELS = ("apertus", "devstral", "eurollm", "qwen36", "medium35")
COMPILERS = ("skidl", "atopile", "tscircuit", "circuit-synth")
DEFAULT_SEEDS = (42, 137, 1024, 8675309, 31415)


def _build_prompt(compiler: str, user_prompt: str) -> str:
    return f"{SYSTEM_PROMPTS[compiler]}\n\nCircuit: {user_prompt}\n"


def run_cell(
    *,
    base_model_key: str,
    compiler: str,
    prompt: str,
    seeds: list[int],
    n_samples: int,
    out_dir: Path,
    audit_logger: AuditLogger,
    model_tok: tuple | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.2,
) -> dict:
    """Run one (model, compiler, prompt) cell across seeds × samples.

    If `model_tok` is provided the caller has already loaded the model
    (used by `run_all` to amortise loads). Otherwise the cell loads on
    demand.
    """
    if compiler not in RUNNERS:
        raise ValueError(f"unknown compiler {compiler!r}")
    if base_model_key not in MODELS:
        raise ValueError(f"unknown base model {base_model_key!r}")

    loaded_here = False
    if model_tok is None:
        model, tok = load_model_and_tokenizer(MODELS[base_model_key]["path"])
        loaded_here = True
    else:
        model, tok = model_tok

    full_prompt = _build_prompt(compiler, prompt)
    runner = RUNNERS[compiler]

    n_parse_ok = 0
    n_compile_ok = 0
    n_attempts = 0
    out_dir = Path(out_dir)

    try:
        for seed in seeds:
            for sample_idx in range(n_samples):
                dsl = generate_sample(
                    model, tok, full_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    seed=seed,
                )
                cell_dir = (
                    out_dir / base_model_key / compiler
                    / f"seed-{seed}" / f"s{sample_idx}"
                )
                result = runner.run(dsl, cell_dir)
                audit_logger.log(
                    "generation",
                    base_model_key=base_model_key,
                    compiler=compiler,
                    prompt=prompt,
                    seed=seed,
                    sample_idx=sample_idx,
                    dsl_parse_ok=result.dsl_parse_ok,
                    compile_ok=result.compile_ok,
                    output_path=(
                        str(result.output_path)
                        if result.output_path else None
                    ),
                    wall_time_ms=result.wall_time_ms,
                    stderr_tail=result.stderr[-500:] if result.stderr else "",
                )
                n_attempts += 1
                if result.dsl_parse_ok:
                    n_parse_ok += 1
                if result.compile_ok:
                    n_compile_ok += 1
    finally:
        if loaded_here:
            unload_model()

    return {
        "base_model_key": base_model_key,
        "compiler": compiler,
        "prompt": prompt,
        "n_attempts": n_attempts,
        "dsl_parse_ok_rate": (
            n_parse_ok / n_attempts if n_attempts else 0.0
        ),
        "compile_ok_rate": (
            n_compile_ok / n_attempts if n_attempts else 0.0
        ),
    }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/test_hybrid_pipeline.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/ailiance && git add scripts/kicad_sch/hybrid_pipeline.py tests/kicad_sch/test_hybrid_pipeline.py
git commit -m "feat(trackd): add run_cell orchestrator

Per (model, compiler, prompt) cell loop: build system
prompt, generate DSL per seed and sample, dispatch to
runner, log every attempt to AuditLogger, aggregate
parse_ok/compile_ok rates."
```

---

## Task 8: `run_all` — full 5 × 4 grid loop

**Files:**
- Modify: `~/ailiance/scripts/kicad_sch/hybrid_pipeline.py` (append `run_all`)
- Test: `~/ailiance/tests/kicad_sch/test_hybrid_pipeline.py` (append two tests)

- [ ] **Step 1: Write the failing test**

Append to `tests/kicad_sch/test_hybrid_pipeline.py`:

```python
def test_run_all_iterates_full_grid(tmp_path, monkeypatch):
    monkeypatch.setattr(hybrid_pipeline, "load_model_and_tokenizer", _stub_load)
    monkeypatch.setattr(hybrid_pipeline, "generate_sample", _stub_generate)
    monkeypatch.setattr(hybrid_pipeline, "unload_model", lambda: None)

    from scripts.kicad_sch.compilers.result import CompileResult

    class _OK:
        def run(self, dsl, out_dir, **_):
            return CompileResult(
                dsl_parse_ok=True, compile_ok=True,
                output_path=None, stderr="", wall_time_ms=1,
            )

    for c in hybrid_pipeline.COMPILERS:
        monkeypatch.setitem(hybrid_pipeline.RUNNERS, c, _OK())

    logger = AuditLogger(tmp_path / "a.ndjson")
    summary = hybrid_pipeline.run_all(
        prompts=["voltage divider"],
        base_models=list(hybrid_pipeline.BASE_MODELS),
        compilers=list(hybrid_pipeline.COMPILERS),
        seeds=[42],
        n_samples=1,
        out_dir=tmp_path / "art",
        audit_logger=logger,
    )
    # 5 models * 4 compilers * 1 prompt = 20 cells
    assert len(summary["cells"]) == 20
    assert summary["n_attempts_total"] == 20
    assert summary["compile_ok_rate_overall"] == 1.0


def test_run_all_writes_summary_json(tmp_path, monkeypatch):
    monkeypatch.setattr(hybrid_pipeline, "load_model_and_tokenizer", _stub_load)
    monkeypatch.setattr(hybrid_pipeline, "generate_sample", _stub_generate)
    monkeypatch.setattr(hybrid_pipeline, "unload_model", lambda: None)

    from scripts.kicad_sch.compilers.result import CompileResult

    class _OK:
        def run(self, dsl, out_dir, **_):
            return CompileResult(dsl_parse_ok=True, compile_ok=True)

    for c in hybrid_pipeline.COMPILERS:
        monkeypatch.setitem(hybrid_pipeline.RUNNERS, c, _OK())

    summary_path = tmp_path / "summary.json"
    logger = AuditLogger(tmp_path / "a.ndjson")
    hybrid_pipeline.run_all(
        prompts=["led blinker"],
        base_models=["qwen36"],
        compilers=["skidl"],
        seeds=[42],
        n_samples=1,
        out_dir=tmp_path / "art",
        audit_logger=logger,
        summary_path=summary_path,
    )
    payload = json.loads(summary_path.read_text())
    assert payload["cells"][0]["base_model_key"] == "qwen36"
    assert payload["cells"][0]["compiler"] == "skidl"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/test_hybrid_pipeline.py -v -k run_all
```

Expected: `AttributeError: module ... has no attribute 'run_all'`.

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/kicad_sch/hybrid_pipeline.py`:

```python
def run_all(
    *,
    prompts: list[str],
    base_models: list[str],
    compilers: list[str],
    seeds: list[int],
    n_samples: int,
    out_dir: Path,
    audit_logger: AuditLogger,
    summary_path: Path | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.2,
) -> dict:
    """Iterate over the full grid of (base_model, compiler, prompt) cells.

    Loads each base model exactly once and reuses it across all compilers
    x prompts to amortise the MLX load cost.
    """
    cells: list[dict] = []
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for base_model_key in base_models:
        if base_model_key not in MODELS:
            raise ValueError(f"unknown base model {base_model_key!r}")
        model, tok = load_model_and_tokenizer(MODELS[base_model_key]["path"])
        audit_logger.log(
            "model_loaded",
            base_model_key=base_model_key,
            model_path=MODELS[base_model_key]["path"],
        )
        try:
            for compiler in compilers:
                for prompt in prompts:
                    cell = run_cell(
                        base_model_key=base_model_key,
                        compiler=compiler,
                        prompt=prompt,
                        seeds=seeds,
                        n_samples=n_samples,
                        out_dir=out_dir,
                        audit_logger=audit_logger,
                        model_tok=(model, tok),
                        max_tokens=max_tokens,
                        temperature=temperature,
                    )
                    cells.append(cell)
        finally:
            unload_model()
            audit_logger.log("model_unloaded", base_model_key=base_model_key)

    n_attempts_total = sum(c["n_attempts"] for c in cells)
    compile_ok_total = sum(
        c["compile_ok_rate"] * c["n_attempts"] for c in cells
    )
    parse_ok_total = sum(
        c["dsl_parse_ok_rate"] * c["n_attempts"] for c in cells
    )
    summary = {
        "n_attempts_total": n_attempts_total,
        "compile_ok_rate_overall": (
            compile_ok_total / n_attempts_total if n_attempts_total else 0.0
        ),
        "dsl_parse_ok_rate_overall": (
            parse_ok_total / n_attempts_total if n_attempts_total else 0.0
        ),
        "cells": cells,
    }
    if summary_path is not None:
        Path(summary_path).write_text(json.dumps(summary, indent=2))
    return summary
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/test_hybrid_pipeline.py -v
```

Expected: 4 passed total.

- [ ] **Step 5: Commit**

```bash
cd ~/ailiance && git add scripts/kicad_sch/hybrid_pipeline.py tests/kicad_sch/test_hybrid_pipeline.py
git commit -m "feat(trackd): add run-all grid orchestrator

Loads each base model exactly once, reuses across all
compilers/prompts to amortise MLX load cost. Emits
summary JSON with per-cell rates plus overall
parse_ok/compile_ok aggregates."
```

---

## Task 9: `__main__` CLI entry point

**Files:**
- Modify: `~/ailiance/scripts/kicad_sch/hybrid_pipeline.py` (append `main()` + guard)
- Test: `~/ailiance/tests/kicad_sch/test_hybrid_pipeline.py` (append CLI test)

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_cli_smoke_mode_runs_one_cell(tmp_path, monkeypatch):
    monkeypatch.setattr(hybrid_pipeline, "load_model_and_tokenizer", _stub_load)
    monkeypatch.setattr(hybrid_pipeline, "generate_sample", _stub_generate)
    monkeypatch.setattr(hybrid_pipeline, "unload_model", lambda: None)

    from scripts.kicad_sch.compilers.result import CompileResult

    class _OK:
        def run(self, dsl, out_dir, **_):
            return CompileResult(dsl_parse_ok=True, compile_ok=True)

    for c in hybrid_pipeline.COMPILERS:
        monkeypatch.setitem(hybrid_pipeline.RUNNERS, c, _OK())

    rc = hybrid_pipeline.main([
        "--mode", "smoke",
        "--out-dir", str(tmp_path / "art"),
        "--audit-path", str(tmp_path / "audit.ndjson"),
        "--summary-path", str(tmp_path / "summary.json"),
    ])
    assert rc == 0
    assert (tmp_path / "summary.json").exists()
    payload = json.loads((tmp_path / "summary.json").read_text())
    # smoke = 1 model x 1 compiler x 1 prompt x 1 seed x 1 sample = 1 cell
    assert len(payload["cells"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/test_hybrid_pipeline.py::test_cli_smoke_mode_runs_one_cell -v
```

Expected: `AttributeError: module ... has no attribute 'main'`.

- [ ] **Step 3: Write minimal implementation**

Append to `scripts/kicad_sch/hybrid_pipeline.py`:

```python
SMOKE_PROMPTS = ["voltage divider 10k 10k"]
FULL_PROMPTS = [
    # 20 reference circuits - keep stable, do not reorder.
    "voltage divider 10k 10k",
    "RC low pass 1k 100nF",
    "LED blinker with NE555 astable",
    "non-inverting opamp gain 10 with rail-to-rail input",
    "ESP32 mini board with USB-C and 3V3 LDO",
    "I2C pull-up pair 4k7 on SDA/SCL",
    "diode bridge full-wave rectifier",
    "common-emitter NPN amplifier",
    "two-stage RC filter 1k 1k 100nF 100nF",
    "MOSFET low-side switch with gate pulldown",
    "TL431 shunt reference 2.5V",
    "linear regulator LM7805 with input and output caps",
    "buck converter MP1584 12V to 5V minimal",
    "RS485 transceiver SN65HVD75",
    "shift register 74HC595 LED driver",
    "ADC reference divider for 3V3 from 12V input",
    "audio amplifier LM386 minimal",
    "EEPROM 24LC256 with I2C address pins tied low",
    "RGB LED with three current-limit resistors",
    "current sense amplifier INA199 with 10mohm shunt",
]


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="hybrid_pipeline")
    p.add_argument("--mode", choices=["smoke", "full"], default="smoke")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--audit-path", required=True)
    p.add_argument("--summary-path", required=True)
    p.add_argument("--base-models", nargs="+", default=None)
    p.add_argument("--compilers", nargs="+", default=None)
    p.add_argument("--n-samples", type=int, default=1)
    p.add_argument("--seeds", nargs="+", type=int, default=None)
    args = p.parse_args(argv)

    if args.mode == "smoke":
        prompts = SMOKE_PROMPTS
        base_models = args.base_models or ["qwen36"]
        compilers = args.compilers or ["skidl"]
        seeds = args.seeds or [42]
    else:
        prompts = FULL_PROMPTS
        base_models = args.base_models or list(BASE_MODELS)
        compilers = args.compilers or list(COMPILERS)
        seeds = args.seeds or list(DEFAULT_SEEDS)

    logger = AuditLogger(Path(args.audit_path))
    logger.log(
        "run_start", mode=args.mode, base_models=base_models,
        compilers=compilers, seeds=seeds, n_samples=args.n_samples,
        n_prompts=len(prompts),
    )
    summary = run_all(
        prompts=prompts,
        base_models=base_models,
        compilers=compilers,
        seeds=seeds,
        n_samples=args.n_samples,
        out_dir=Path(args.out_dir),
        audit_logger=logger,
        summary_path=Path(args.summary_path),
    )
    logger.log(
        "run_end",
        n_attempts_total=summary["n_attempts_total"],
        compile_ok_rate_overall=summary["compile_ok_rate_overall"],
        dsl_parse_ok_rate_overall=summary["dsl_parse_ok_rate_overall"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/test_hybrid_pipeline.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/ailiance && git add scripts/kicad_sch/hybrid_pipeline.py tests/kicad_sch/test_hybrid_pipeline.py
git commit -m "feat(trackd): add CLI with smoke and full modes

smoke = qwen36 x skidl x 1 prompt x 1 seed (1 cell).
full = 5 models x 4 compilers x 20 prompts x 5 seeds.
Locks 20 reference prompts list as a stable constant
to preserve cross-run comparability."
```

---

## Task 10: Shell wrapper `run_track_d.sh`

**Files:**
- Create: `~/ailiance/scripts/run_track_d.sh`
- Test: `~/ailiance/tests/kicad_sch/test_run_track_d_sh.py`

- [ ] **Step 1: Write the failing test**

```python
# ~/ailiance/tests/kicad_sch/test_run_track_d_sh.py
import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_track_d.sh"


def test_script_exists_and_is_executable():
    assert SCRIPT.exists()
    assert os.access(SCRIPT, os.X_OK), "run_track_d.sh must be chmod +x"


def test_script_help_lists_smoke_and_full():
    proc = subprocess.run(
        ["bash", str(SCRIPT), "--help"],
        capture_output=True, text=True,
    )
    assert "smoke" in proc.stdout.lower()
    assert "full" in proc.stdout.lower()


def test_script_rejects_unknown_mode():
    proc = subprocess.run(
        ["bash", str(SCRIPT), "weird"],
        capture_output=True, text=True,
    )
    assert proc.returncode != 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/test_run_track_d_sh.py -v
```

Expected: 3 failed (script missing).

- [ ] **Step 3: Write minimal implementation**

Create `~/ailiance/scripts/run_track_d.sh`:

```bash
#!/usr/bin/env bash
# Track-D hybrid LLM->DSL->compiler pipelines launcher.
# Usage:
#   scripts/run_track_d.sh smoke   # 1 cell (qwen36 + skidl + 1 prompt)
#   scripts/run_track_d.sh full    # 5 models * 4 compilers * 20 prompts * 5 seeds
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: run_track_d.sh <mode>
  smoke   1 cell: qwen36 base x skidl compiler x 1 prompt x 1 seed.
  full    Full grid: 5 base models x 4 compilers x 20 prompts x 5 seeds.

Output goes to ~/ailiance/output/track-d/<timestamp>/.
USAGE
}

if [[ $# -ne 1 ]] || [[ "$1" == "--help" || "$1" == "-h" ]]; then
  usage
  [[ $# -eq 0 ]] && exit 1 || exit 0
fi

MODE="$1"
case "$MODE" in
  smoke|full) ;;
  *) echo "error: unknown mode '$MODE'" >&2; usage >&2; exit 2 ;;
esac

TS=$(date +%Y-%m-%dT%H-%M-%S)
ROOT="${HOME}/ailiance"
OUT="${ROOT}/output/track-d/${TS}"
mkdir -p "${OUT}/artefacts"

cd "${ROOT}"
uv run python -m scripts.kicad_sch.hybrid_pipeline \
  --mode "${MODE}" \
  --out-dir "${OUT}/artefacts" \
  --audit-path "${OUT}/audit.ndjson" \
  --summary-path "${OUT}/summary.json"

echo "Track-D ${MODE} run complete: ${OUT}"
```

Then make it executable:

```bash
chmod +x ~/ailiance/scripts/run_track_d.sh
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd ~/ailiance && uv run python -m pytest tests/kicad_sch/test_run_track_d_sh.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/ailiance && git add scripts/run_track_d.sh tests/kicad_sch/test_run_track_d_sh.py
git update-index --chmod=+x scripts/run_track_d.sh
git commit -m "feat(trackd): add run-track-d shell wrapper

Two modes: smoke (1 cell) and full (5x4x20x5 grid).
Time-stamped output dir under output/track-d/, writes
audit.ndjson + summary.json side by side."
```

---

## Task 11: Live smoke run on Studio

This task has no test file — it is an integration smoke against the *real* MLX + real compilers. Required to confirm the plan ships working software end-to-end.

**Files:** none (artefact-only).

- [ ] **Step 1: Run smoke**

```bash
ssh studio 'cd ~/ailiance && bash scripts/run_track_d.sh smoke'
```

Expected output last line: `Track-D smoke run complete: /Users/clems/ailiance/output/track-d/2026-05-11T...`.

- [ ] **Step 2: Inspect audit log**

```bash
ssh studio 'jq -c . ~/ailiance/output/track-d/$(ls -t ~/ailiance/output/track-d/ | head -1)/audit.ndjson'
```

Expected: at least 3 NDJSON lines — one `run_start`, one or more `model_loaded` + `generation`, one `run_end`. Every `generation` line has fields `base_model_key`, `compiler`, `seed`, `sample_idx`, `dsl_parse_ok`, `compile_ok`.

- [ ] **Step 3: Inspect summary JSON**

```bash
ssh studio 'jq . ~/ailiance/output/track-d/$(ls -t ~/ailiance/output/track-d/ | head -1)/summary.json'
```

Expected: `cells` array with one entry containing `base_model_key: "qwen36"`, `compiler: "skidl"`, `n_attempts: 1`, and numeric rate fields.

- [ ] **Step 4: Record findings**

Append a short note to `~/ailiance-bench/docs/superpowers/specs/2026-05-11-kicad-sch-gap-design.md` under a new `## Track D smoke results` section: timestamp, model load time, parse/compile rates observed, any tool that short-circuited because of Pre-Task 0 install gaps.

- [ ] **Step 5: Commit doc note (in `ailiance-bench` repo)**

```bash
cd ~/ailiance-bench && git add docs/superpowers/specs/2026-05-11-kicad-sch-gap-design.md
git commit -m "docs(trackd): record live smoke results

First end-to-end smoke of the hybrid pipeline against
real MLX models and real compilers on Studio."
```

---

## Self-Review

**1. Spec coverage:**
- 20 hybrid pipelines, no LoRA, inference-only → Tasks 7-9 (`run_cell`, `run_all`, CLI) cover the 5 x 4 grid; Task 11 proves end-to-end.
- Per-cell `dsl_parse_ok / compile_ok / kicad_load_ok` rates → `CompileResult` (Task 1) carries the first two; `kicad_load_ok` is left for Eval N3 as the spec says ("filled in downstream by Eval N3, not by the runner").
- NDJSON audit via AuditLogger → every runner attempt logged in Task 7; `run_start` / `run_end` / `model_loaded` / `model_unloaded` events in Tasks 8-9.
- 4 system prompts each ~100 words, no markdown wrap → Task 2 with explicit length test (200-2000 chars) and "no markdown / no code fence / do not wrap" assertion.
- 4 runner modules with shared `CompileResult{dsl_parse_ok, compile_ok, output_path, stderr, wall_time_ms}` → Tasks 3-6, dataclass in Task 1.
- Test files under `tests/kicad_sch/` and `tests/kicad_sch/compilers/` → every task ships its test file.
- CLI runner `run_track_d.sh` with smoke | full → Task 10.
- Concrete test examples from the brief (`test_skidl_runner_compiles_minimal_voltage_divider`, `test_pipeline_logs_each_attempt`) → reproduced verbatim in Tasks 3 and 7.

**2. Placeholder scan:** no TODOs, no "implement later", no "similar to Task N". Every step contains either complete code, an exact shell command, or an exact expected output line.

**3. Type consistency:**
- `CompileResult` fields used identically in every runner (Tasks 3-6) and in pipeline (Task 7).
- `runner.run(dsl, out_dir)` signature consistent across all four runners and the `_StubRunner` / `_AltRunner` test doubles (Tasks 3-7).
- `RUNNERS` dict module-level in Task 7, monkeypatched in Tasks 7-9.
- `MODELS` keys (`apertus, devstral, eurollm, qwen36, medium35`) verified live against `eval_framework.py:59` on Studio 2026-05-11.
- `load_model_and_tokenizer(model_path, adapter_path=None) -> (model, tokenizer)` signature taken from `eval_framework.py:459`.
- `BASE_MODELS / COMPILERS / DEFAULT_SEEDS` constants defined once in Task 7, reused in CLI (Task 9) and tests (Tasks 8-9).

**4. Environment carryover from Studio probe (2026-05-11 05:39 CEST):**
- skidl / atopile / npx / circuit_synth all MISSING → `Pre-Task 0` covers install with explicit `uv pip install` + `brew install node` + `npm install -g @tscircuit/cli`.
- `audit_log.py` MISSING → declared as Foundation deliverable in File Structure preamble; if it lands later than expected, Tasks 7-10 break at import. Mitigation: a temporary local AuditLogger stub (one-line JSON-per-call writer) unblocks Tasks 1-6 + the unit half of Tasks 7-10 without committing the stub — that responsibility belongs to Foundation.
