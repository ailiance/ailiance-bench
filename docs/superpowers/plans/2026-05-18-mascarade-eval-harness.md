# Mascarade Eval Harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a trustworthy eval harness (`mascarade-eval/` in `ailiance-bench`) that produces a defensible per-LoRA verdict for the 10 deployed mascarade LoRAs.

**Architecture:** A pipeline — mine fresh held-out data from upstream, filter training-set leakage, run base vs base+LoRA over the held-out, score with a hybrid metric (functional scorers + LLM-judge + perplexity), aggregate into a per-LoRA verdict report. New Python module, follows the repo's Phase-N script conventions.

**Tech Stack:** Python 3.12, `datasets` 4.8, `huggingface-hub` 1.13, `mlx-lm` 0.31.3, stdlib `urllib`/`hashlib`, `pytest`. Spec: `docs/superpowers/specs/2026-05-18-mascarade-eval-harness-design.md`.

---

## File Structure

All under `mascarade-eval/` in the `ailiance-bench` repo root.

| File | Responsibility |
|------|----------------|
| `mascarade_eval/__init__.py` | Package marker, shared constants (`DOMAINS`, paths). |
| `mascarade_eval/leakage_check.py` | Pure functions: normalize text, exact-hash + shingled-Jaccard near-dup detection against a training corpus. |
| `mascarade_eval/mine_upstream.py` | Build `heldout/<domain>.raw.jsonl` from a time-cut upstream slice. |
| `mascarade_eval/runner.py` | Generate answers for `base` and `base+LoRA` configs over a held-out file via HTTP. |
| `mascarade_eval/scorers.py` | Hybrid scoring: wraps `bench_kicad_functional` scorers, perplexity, dispatch by domain. |
| `mascarade_eval/judge.py` | LLM-judge (home Mistral-Medium) + external spot-check sampling. |
| `mascarade_eval/aggregate.py` | Combine scores → per-LoRA verdict; render `mascarade-eval-report.md`. |
| `mascarade_eval/run_eval.py` | CLI entrypoint orchestrating the full pipeline. |
| `tests/test_leakage_check.py` | Unit tests for the leakage guard. |
| `tests/test_scorers.py` | Unit tests for scoring dispatch. |
| `tests/test_aggregate.py` | Unit tests for the verdict logic. |

The 10 domains (shared constant): `kicad spice stm32 emc embedded platformio freecad dsp iot power`.

---

## Task 1: Research spike — pin down upstream held-out sources

**Files:** Create `mascarade-eval/docs/heldout-sources.md` (findings doc).

- [ ] **Step 1: Investigate, per domain, a usable upstream held-out source**

`N/A - research`. For each of the 10 domains, determine a concrete source of (prompt, reference-answer) pairs that is **outside the training corpus**, preferring a time-cut:
- Inspect `Ailiance-fr/mascarade-<domain>-dataset` `_provenance` fields (the recon found a `_provenance` key on dataset rows) — they record where each training row came from.
- Identify the upstream (which Stack Exchange site per domain, KiCad doc source) and the latest timestamp present in training; a slice newer than that is unseen by construction.
- Decide the access method: Stack Exchange API (`api.stackexchange.com`, filter by tag + `fromdate`), an SE data dump, or KiCad repo docs.

- [ ] **Step 2: Write `heldout-sources.md`**

Document, per domain: source URL/API, the tag/filter, the time-cut date, expected yield (≥25 items/domain target), and the exact field mapping to `{prompt, reference}`. This doc is the contract `mine_upstream.py` implements.

- [ ] **Step 3: Commit**

```bash
git add mascarade-eval/docs/heldout-sources.md
git commit -m "docs(eval): pin down upstream held-out sources"
```

---

## Task 2: Module scaffold + shared constants

**Files:**
- Create: `mascarade-eval/mascarade_eval/__init__.py`
- Create: `mascarade-eval/pyproject.toml` (or extend the repo's if it has one — Task checks first)

- [ ] **Step 1: Create the package with shared constants**

```python
# mascarade-eval/mascarade_eval/__init__.py
"""Trustworthy eval harness for the 10 mascarade hardware LoRAs."""
from pathlib import Path

DOMAINS: tuple[str, ...] = (
    "kicad", "spice", "stm32", "emc", "embedded",
    "platformio", "freecad", "dsp", "iot", "power",
)
BASE_MODEL = "Qwen/Qwen3-4B-Instruct-2507"
HF_ORG = "Ailiance-fr"

_ROOT = Path(__file__).resolve().parent.parent
HELDOUT_DIR = _ROOT / "heldout"
RESULTS_DIR = _ROOT / "results"
MIN_HELDOUT = 20  # below this, a domain verdict is flagged low-confidence
```

- [ ] **Step 2: Verify import works**

Run: `cd mascarade-eval && python -c "from mascarade_eval import DOMAINS; print(len(DOMAINS))"`
Expected: `10`

- [ ] **Step 3: Commit**

```bash
git add mascarade-eval/mascarade_eval/__init__.py mascarade-eval/pyproject.toml
git commit -m "feat(eval): scaffold mascarade-eval package"
```

---

## Task 3: Leakage check

**Files:**
- Create: `mascarade-eval/mascarade_eval/leakage_check.py`
- Test: `mascarade-eval/tests/test_leakage_check.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_leakage_check.py
from mascarade_eval.leakage_check import normalize, is_leak, filter_leaks

def test_normalize_collapses_whitespace_and_case():
    assert normalize("  Hello   WORLD\n") == "hello world"

def test_exact_duplicate_is_a_leak():
    train = ["how do I route a differential pair"]
    assert is_leak("How do I route a differential pair?", train) is True

def test_near_duplicate_is_a_leak():
    train = ["what value decoupling capacitor for an stm32 vdd pin"]
    cand = "What value of decoupling capacitor should I use for an STM32 VDD pin?"
    assert is_leak(cand, train, jaccard_threshold=0.6) is True

def test_distinct_prompt_is_not_a_leak():
    train = ["how to configure spi on stm32"]
    assert is_leak("explain aliasing in dsp", train) is False

def test_filter_leaks_drops_leaked_items_and_reports():
    items = [{"prompt": "configure spi on stm32"}, {"prompt": "explain fft windowing"}]
    train = ["how to configure spi on stm32"]
    clean, dropped = filter_leaks(items, train)
    assert len(clean) == 1 and clean[0]["prompt"] == "explain fft windowing"
    assert len(dropped) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mascarade-eval && python -m pytest tests/test_leakage_check.py -v`
Expected: FAIL — `ModuleNotFoundError: mascarade_eval.leakage_check`

- [ ] **Step 3: Implement `leakage_check.py`**

```python
# mascarade_eval/leakage_check.py
"""Detect held-out items that overlap the LoRA training corpus.

Two passes: exact (normalized sha256) and near-duplicate (shingled
Jaccard). Dependency-free — stdlib only.
"""
from __future__ import annotations
import hashlib
import re

_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, collapse whitespace, strip — for hashing/shingling."""
    return _WS.sub(" ", text.lower()).strip()


def _shingles(text: str, k: int = 4) -> set[str]:
    """k-word shingles of normalized text."""
    words = normalize(text).split()
    if len(words) < k:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def is_leak(candidate: str, train_corpus: list[str],
            jaccard_threshold: float = 0.6) -> bool:
    """True if `candidate` exactly or near-duplicates any training item."""
    cand_norm = normalize(candidate)
    cand_hash = hashlib.sha256(cand_norm.encode()).hexdigest()
    cand_shingles = _shingles(candidate)
    for train_item in train_corpus:
        if hashlib.sha256(normalize(train_item).encode()).hexdigest() == cand_hash:
            return True
        if _jaccard(cand_shingles, _shingles(train_item)) >= jaccard_threshold:
            return True
    return False


def filter_leaks(items: list[dict], train_corpus: list[str],
                 jaccard_threshold: float = 0.6) -> tuple[list[dict], list[dict]]:
    """Split `items` (each with a 'prompt' key) into (clean, dropped)."""
    clean, dropped = [], []
    for item in items:
        if is_leak(item["prompt"], train_corpus, jaccard_threshold):
            dropped.append(item)
        else:
            clean.append(item)
    return clean, dropped
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mascarade-eval && python -m pytest tests/test_leakage_check.py -v`
Expected: PASS — 5 passed

- [ ] **Step 5: Commit**

```bash
git add mascarade-eval/mascarade_eval/leakage_check.py mascarade-eval/tests/test_leakage_check.py
git commit -m "feat(eval): leakage check against training corpus"
```

---

## Task 4: Training-corpus loader

**Files:**
- Create: `mascarade-eval/mascarade_eval/train_corpus.py`
- Test: `mascarade-eval/tests/test_train_corpus.py`

Provides the `train_corpus` list that Task 3 consumes — the set of training prompts per domain, loaded from the HF dataset.

- [ ] **Step 1: Write the failing test** (uses a local fixture file, no network)

```python
# tests/test_train_corpus.py
import json
from mascarade_eval.train_corpus import extract_prompts

def test_extract_prompts_handles_messages_format(tmp_path):
    f = tmp_path / "d.jsonl"
    f.write_text(json.dumps({"messages": [
        {"role": "user", "content": "Q1"}, {"role": "assistant", "content": "A1"}]}) + "\n")
    assert extract_prompts(str(f)) == ["Q1"]

def test_extract_prompts_handles_conversations_format(tmp_path):
    f = tmp_path / "d.jsonl"
    f.write_text(json.dumps({"conversations": [
        {"from": "human", "value": "Q2"}, {"from": "gpt", "value": "A2"}]}) + "\n")
    assert extract_prompts(str(f)) == ["Q2"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mascarade-eval && python -m pytest tests/test_train_corpus.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `train_corpus.py`** (parser resilient to both formats — per recon, `bench_phase9_baseline_forgetting.py:56-83`)

```python
# mascarade_eval/train_corpus.py
"""Load the user prompts of a mascarade training dataset.

Datasets exist in two formats (recon 2026-05-18): ShareGPT
(`conversations`/`from`/`value`) and OpenAI (`messages`/`role`/`content`).
"""
from __future__ import annotations
import json
from huggingface_hub import hf_hub_download
from . import HF_ORG


def extract_prompts(jsonl_path: str) -> list[str]:
    """Return every user/human prompt in a chat JSONL file."""
    prompts: list[str] = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            msgs = d.get("messages") or d.get("conversations") or []
            for m in msgs:
                role = m.get("role") or m.get("from")
                if role in ("user", "human"):
                    prompts.append(m.get("content") or m.get("value") or "")
    return prompts


def load_train_prompts(domain: str) -> list[str]:
    """Download the domain training dataset from HF and extract its prompts."""
    path = hf_hub_download(
        repo_id=f"{HF_ORG}/mascarade-{domain}-dataset",
        filename=f"{domain}_chat.jsonl",
        repo_type="dataset",
    )
    return extract_prompts(path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mascarade-eval && python -m pytest tests/test_train_corpus.py -v`
Expected: PASS — 2 passed

- [ ] **Step 5: Commit**

```bash
git add mascarade-eval/mascarade_eval/train_corpus.py mascarade-eval/tests/test_train_corpus.py
git commit -m "feat(eval): training-corpus prompt loader"
```

---

## Task 5: `mine_upstream.py` — held-out builder

**Files:**
- Create: `mascarade-eval/mascarade_eval/mine_upstream.py`
- Test: `mascarade-eval/tests/test_mine_upstream.py`

Implements the per-domain source contract from Task 1's `heldout-sources.md`.

- [ ] **Step 1: Write the failing test** (parsing/shaping logic, network mocked)

```python
# tests/test_mine_upstream.py
from mascarade_eval.mine_upstream import shape_item

def test_shape_item_builds_prompt_reference_pair():
    raw = {"title": "How to route DDR3", "body_markdown": "details...",
           "accepted_answer_body": "route it like this"}
    item = shape_item(raw, domain="kicad")
    assert item["domain"] == "kicad"
    assert "How to route DDR3" in item["prompt"]
    assert item["reference"] == "route it like this"
    assert item["source"]  # provenance recorded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mascarade-eval && python -m pytest tests/test_mine_upstream.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `mine_upstream.py`**

Implement against the source contract in `mascarade-eval/docs/heldout-sources.md` (Task 1). Required public surface:
- `shape_item(raw: dict, domain: str) -> dict` — map one raw upstream record to `{"domain", "prompt", "reference", "source"}`. (Shape shown in the test above; the exact `raw` keys come from Task 1's contract.)
- `mine(domain: str, n: int, cutoff_date: str) -> list[dict]` — fetch up to `n` records newer than `cutoff_date` for `domain`, return shaped items.
- `main()` — CLI: `--domains`, `--n` (default 40), writes `heldout/<domain>.raw.jsonl`.

Full code for `shape_item` and the file scaffold is fixed here; `mine()`'s fetch body is filled per the Task 1 contract:

```python
# mascarade_eval/mine_upstream.py
"""Mine a fresh held-out slice per domain from upstream (time-cut)."""
from __future__ import annotations
import argparse
import json
from . import DOMAINS, HELDOUT_DIR


def shape_item(raw: dict, domain: str) -> dict:
    """Map one raw upstream record to a held-out item."""
    title = raw.get("title", "").strip()
    body = raw.get("body_markdown", "").strip()
    prompt = f"{title}\n\n{body}".strip() if body else title
    return {
        "domain": domain,
        "prompt": prompt,
        "reference": raw.get("accepted_answer_body", "").strip(),
        "source": raw.get("link") or raw.get("source") or "upstream",
    }


def mine(domain: str, n: int, cutoff_date: str) -> list[dict]:
    """Fetch <= n records for `domain` newer than `cutoff_date`.

    Implements the per-domain source/filter from
    mascarade-eval/docs/heldout-sources.md (Task 1).
    """
    raise NotImplementedError("fill from heldout-sources.md contract")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", nargs="*", default=list(DOMAINS))
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--cutoff-date", required=True,
                    help="ISO date; only items newer are mined")
    args = ap.parse_args()
    HELDOUT_DIR.mkdir(parents=True, exist_ok=True)
    for domain in args.domains:
        items = mine(domain, args.n, args.cutoff_date)
        out = HELDOUT_DIR / f"{domain}.raw.jsonl"
        out.write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in items))
        print(f"{domain}: {len(items)} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

> **NOTE for the implementer:** `mine()` is the one body that depends on Task 1's findings — implement its fetch loop against the documented source (Stack Exchange API `fromdate` filter, or dump parse). `shape_item` may need its `raw` keys adjusted to match. This is expected — Task 1 is its spec.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mascarade-eval && python -m pytest tests/test_mine_upstream.py -v`
Expected: PASS — 1 passed

- [ ] **Step 5: Build the held-out, then leakage-filter it**

Run `mine_upstream.py` for all domains, then a one-off that loads each `heldout/<domain>.raw.jsonl`, calls `train_corpus.load_train_prompts(domain)` + `leakage_check.filter_leaks`, writes `heldout/<domain>.clean.jsonl`, and logs dropped counts. A domain with `< MIN_HELDOUT` clean items is flagged for top-up.

- [ ] **Step 6: Commit**

```bash
git add mascarade-eval/mascarade_eval/mine_upstream.py mascarade-eval/tests/test_mine_upstream.py
git commit -m "feat(eval): upstream held-out miner"
```

---

## Task 6: Runner

**Files:**
- Create: `mascarade-eval/mascarade_eval/runner.py`
- Test: `mascarade-eval/tests/test_runner.py`

Generates answers for two configs over a clean held-out file. Uses the HTTP chat-completions pattern from the recon (`bench_gateway.py:46-73`).

- [ ] **Step 1: Write the failing test** (HTTP mocked)

```python
# tests/test_runner.py
from unittest.mock import patch, MagicMock
import json, io
from mascarade_eval.runner import chat_completion

def test_chat_completion_extracts_content():
    fake = io.BytesIO(json.dumps(
        {"choices": [{"message": {"content": "the answer"}}]}).encode())
    fake.__enter__ = lambda s: s
    fake.__exit__ = lambda *a: None
    with patch("urllib.request.urlopen", return_value=fake):
        out = chat_completion("http://x/v1/chat/completions", "m", "prompt")
    assert out == "the answer"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mascarade-eval && python -m pytest tests/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `runner.py`**

```python
# mascarade_eval/runner.py
"""Generate answers for base and base+LoRA over a held-out file."""
from __future__ import annotations
import json
import time
import urllib.request

# base+LoRA: Studio :9340 mascarade server (via the gateway tunnel
# localhost:9340). base: a plain Qwen3-4B endpoint — see CONFIGS.
CONFIGS = {
    "lora": "http://localhost:9340/v1/chat/completions",
    "base": "http://localhost:9341/v1/chat/completions",  # see Step 5 note
}


def chat_completion(url: str, model: str, prompt: str,
                    max_tokens: int = 1024, timeout: int = 90) -> str:
    """One OpenAI-compatible chat call; returns the assistant content."""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    return data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""


def run_config(heldout_items: list[dict], config: str, model: str) -> list[dict]:
    """Generate an answer per held-out item for one config."""
    url = CONFIGS[config]
    out = []
    for item in heldout_items:
        t0 = time.perf_counter()
        try:
            answer = chat_completion(url, model, item["prompt"])
            err = None
        except Exception as e:  # noqa: BLE001
            answer, err = "", repr(e)
        out.append({**item, "config": config, "answer": answer,
                    "error": err, "gen_s": round(time.perf_counter() - t0, 2)})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mascarade-eval && python -m pytest tests/test_runner.py -v`
Expected: PASS — 1 passed

- [ ] **Step 5: Commit**

> **NOTE:** the `base` config needs a plain Qwen3-4B endpoint. Decide at execution: either start a temporary `mlx_lm.server` for `Qwen3-4B-Instruct-2507` on Studio :9341, or load the base model locally in the runner. Record the choice in the runner docstring.

```bash
git add mascarade-eval/mascarade_eval/runner.py mascarade-eval/tests/test_runner.py
git commit -m "feat(eval): base vs base+LoRA runner"
```

---

## Task 7: Scorers (functional + perplexity dispatch)

**Files:**
- Create: `mascarade-eval/mascarade_eval/scorers.py`
- Test: `mascarade-eval/tests/test_scorers.py`

Wraps the existing functional scorers and adds the domain→scorer dispatch.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scorers.py
from mascarade_eval.scorers import functional_score, DOMAIN_SCORER

def test_spice_functional_score_on_valid_netlist():
    netlist = "R1 1 0 1k\nV1 1 0 5\nC1 1 0 1u\n.end"
    s = functional_score("spice", netlist, netlist)
    assert 0.0 <= s["composite"] <= 1.0 and s["parse_ok"] is True

def test_domain_without_functional_scorer_returns_none():
    assert DOMAIN_SCORER.get("iot") is None  # judged by LLM only
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mascarade-eval && python -m pytest tests/test_scorers.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `scorers.py`** (reuses `bench_kicad_functional` per recon — `score_dsl/pcb/spice`, lines 230-528)

```python
# mascarade_eval/scorers.py
"""Hybrid scoring: functional scorers where output is structured."""
from __future__ import annotations
import sys
from pathlib import Path

# Reuse the repo's functional scorers.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from bench_kicad_functional import score_dsl, score_pcb, score_spice  # noqa: E402

# Domain -> functional scorer. None = no structural scorer; LLM-judge only.
DOMAIN_SCORER = {
    "kicad": score_dsl,      # also score_pcb for pcb-shaped tasks
    "spice": score_spice,
    "emc": score_spice,      # SPICE-shaped (emc-dsp-power family)
    "dsp": score_spice,
    "power": score_spice,
    "stm32": None,
    "embedded": None,
    "platformio": None,      # extend later: a .ini parser
    "freecad": None,
    "iot": None,
}


def functional_score(domain: str, generated: str, expected: str) -> dict | None:
    """Functional composite for `domain`, or None if no structural scorer."""
    scorer = DOMAIN_SCORER.get(domain)
    if scorer is None:
        return None
    return scorer(generated, expected)


def perplexity_score(reference: str, logprob_fn) -> float | None:
    """Secondary signal: perplexity of the reference answer under a model.

    `logprob_fn(text) -> list[float]` returns per-token logprobs. The
    chat-completions HTTP API does not expose logprobs, so this is
    best-effort: pass None (or a fn that raises) and it returns None —
    perplexity is a SECONDARY cross-check per the spec, never load-bearing.
    """
    if logprob_fn is None:
        return None
    try:
        lps = logprob_fn(reference)
    except Exception:  # noqa: BLE001
        return None
    if not lps:
        return None
    import math
    return math.exp(-sum(lps) / len(lps))
```

- [ ] **Step 4: Add the perplexity test**

```python
# append to tests/test_scorers.py
from mascarade_eval.scorers import perplexity_score

def test_perplexity_is_none_when_no_logprob_provider():
    assert perplexity_score("some reference answer", logprob_fn=None) is None

def test_perplexity_computes_from_logprobs():
    ppl = perplexity_score("ref", logprob_fn=lambda t: [-1.0, -1.0])
    assert abs(ppl - 2.718281828) < 1e-3
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd mascarade-eval && python -m pytest tests/test_scorers.py -v`
Expected: PASS — 4 passed

- [ ] **Step 6: Commit**

```bash
git add mascarade-eval/mascarade_eval/scorers.py mascarade-eval/tests/test_scorers.py
git commit -m "feat(eval): functional and perplexity scorers"
```

> **NOTE:** perplexity needs a logprobs-capable path. If a run wants it,
> wire `logprob_fn` to a local model load (the volet-3 bench approach) or
> an `echo`+`logprobs` endpoint. Absent that, the harness runs on
> functional + judge alone — which the spec explicitly permits.

---

## Task 8: LLM-judge

**Files:**
- Create: `mascarade-eval/mascarade_eval/judge.py`
- Create: `mascarade-eval/mascarade_eval/rubrics/<domain>.txt` (10 rubric files)
- Test: `mascarade-eval/tests/test_judge.py`

Home judge = Mistral-Medium-128B (gateway alias `ailiance-mistral-medium`). External spot-check on a ~12% sample.

- [ ] **Step 1: Write the failing test** (judge HTTP mocked)

```python
# tests/test_judge.py
from unittest.mock import patch
from mascarade_eval.judge import parse_judge_score, sample_for_spotcheck

def test_parse_judge_score_extracts_integer():
    assert parse_judge_score("Reasoning: solid.\nSCORE: 7") == 7

def test_parse_judge_score_clamps_and_defaults():
    assert parse_judge_score("no score here") is None

def test_sample_for_spotcheck_picks_fraction():
    items = [{"i": k} for k in range(100)]
    s = sample_for_spotcheck(items, fraction=0.12, seed=0)
    assert len(s) == 12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mascarade-eval && python -m pytest tests/test_judge.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `judge.py`**

```python
# mascarade_eval/judge.py
"""LLM-judge: home Mistral-Medium scores answers on a per-domain rubric;
a sampled subset is cross-checked by an external judge for calibration.
"""
from __future__ import annotations
import random
import re
from pathlib import Path
from .runner import chat_completion

GATEWAY = "http://localhost:9300/v1/chat/completions"
HOME_JUDGE = "ailiance-mistral-medium"
_RUBRIC_DIR = Path(__file__).resolve().parent / "rubrics"
_SCORE_RE = re.compile(r"SCORE:\s*(\d+)", re.IGNORECASE)


def parse_judge_score(judge_output: str) -> int | None:
    """Extract the integer 0-10 score from a judge response, or None."""
    m = _SCORE_RE.search(judge_output)
    if not m:
        return None
    return max(0, min(10, int(m.group(1))))


def _judge_prompt(domain: str, prompt: str, answer: str) -> str:
    rubric = (_RUBRIC_DIR / f"{domain}.txt").read_text()
    return (f"{rubric}\n\n=== QUESTION ===\n{prompt}\n\n"
            f"=== ANSWER TO GRADE ===\n{answer}\n\n"
            "Reply with one line of reasoning then `SCORE: <0-10>`.")


def judge_one(domain: str, prompt: str, answer: str,
              model: str = HOME_JUDGE, url: str = GATEWAY) -> int | None:
    """Score one answer with the LLM-judge."""
    out = chat_completion(url, model, _judge_prompt(domain, prompt, answer),
                          max_tokens=256)
    return parse_judge_score(out)


def sample_for_spotcheck(items: list[dict], fraction: float = 0.12,
                         seed: int = 0) -> list[dict]:
    """Deterministic subsample for external-judge cross-check."""
    rng = random.Random(seed)
    k = max(1, round(len(items) * fraction))
    return rng.sample(items, min(k, len(items)))
```

- [ ] **Step 4: Write the 10 rubric files**

Each `rubrics/<domain>.txt`: a domain-specific grading rubric (what a correct hardware answer must contain — factual accuracy, completeness, no hallucinated parts/APIs). Write all 10 with real domain criteria — no placeholders.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd mascarade-eval && python -m pytest tests/test_judge.py -v`
Expected: PASS — 3 passed

- [ ] **Step 6: Commit**

```bash
git add mascarade-eval/mascarade_eval/judge.py mascarade-eval/mascarade_eval/rubrics/ mascarade-eval/tests/test_judge.py
git commit -m "feat(eval): LLM-judge with per-domain rubrics"
```

---

## Task 9: Verdict aggregator + report

**Files:**
- Create: `mascarade-eval/mascarade_eval/aggregate.py`
- Test: `mascarade-eval/tests/test_aggregate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_aggregate.py
from mascarade_eval.aggregate import verdict

def test_verdict_learned_when_lora_clearly_beats_base():
    assert verdict(base_score=0.40, lora_score=0.72, n=30) == "a appris"

def test_verdict_no_lora_needed_when_base_already_high():
    assert verdict(base_score=0.93, lora_score=0.94, n=30) == "domaine sans besoin de LoRA"

def test_verdict_weak_when_lora_barely_beats_mediocre_base():
    assert verdict(base_score=0.45, lora_score=0.49, n=30) == "faible"

def test_verdict_low_confidence_when_too_few_items():
    assert verdict(base_score=0.40, lora_score=0.72, n=12) == "basse confiance"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mascarade-eval && python -m pytest tests/test_aggregate.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `aggregate.py`**

```python
# mascarade_eval/aggregate.py
"""Combine per-item scores into a per-LoRA verdict + markdown report."""
from __future__ import annotations
from . import MIN_HELDOUT

_LEARNED_MARGIN = 0.15   # lora - base >= this => learned
_BASE_HIGH = 0.85        # base already this good => no LoRA needed


def verdict(base_score: float, lora_score: float, n: int) -> str:
    """Four-way verdict from mean base/LoRA scores on the held-out."""
    if n < MIN_HELDOUT:
        return "basse confiance"
    if base_score >= _BASE_HIGH and lora_score - base_score < _LEARNED_MARGIN:
        return "domaine sans besoin de LoRA"
    if lora_score - base_score >= _LEARNED_MARGIN:
        return "a appris"
    return "faible"


def render_report(rows: list[dict]) -> str:
    """rows: [{domain, n, base_score, lora_score, verdict, routed_to}]."""
    lines = ["# Mascarade Eval — verdict par LoRA", "",
             "| Domaine | n | base | +LoRA | Verdict | Aiguillage |",
             "|---|--:|--:|--:|---|---|"]
    for r in rows:
        lines.append(
            f"| {r['domain']} | {r['n']} | {r['base_score']:.3f} | "
            f"{r['lora_score']:.3f} | {r['verdict']} | {r['routed_to']} |")
    return "\n".join(lines) + "\n"
```

The `routed_to` field: `faible` → B (data) then C (training); `a appris` → none; `domaine sans besoin de LoRA` → drop the LoRA from routing; `basse confiance` → re-mine more held-out.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd mascarade-eval && python -m pytest tests/test_aggregate.py -v`
Expected: PASS — 4 passed

- [ ] **Step 5: Commit**

```bash
git add mascarade-eval/mascarade_eval/aggregate.py mascarade-eval/tests/test_aggregate.py
git commit -m "feat(eval): verdict aggregator and report"
```

---

## Task 10: CLI orchestrator + end-to-end smoke

**Files:**
- Create: `mascarade-eval/mascarade_eval/run_eval.py`
- Test: `mascarade-eval/tests/test_run_eval_smoke.py`

- [ ] **Step 1: Implement `run_eval.py`**

```python
# mascarade_eval/run_eval.py
"""CLI: run the full mascarade eval pipeline, write the verdict report."""
from __future__ import annotations
import argparse
import json
from statistics import mean
from . import DOMAINS, RESULTS_DIR, HELDOUT_DIR
from .runner import run_config
from .scorers import functional_score
from .judge import judge_one
from .aggregate import verdict, render_report

_ROUTE = {
    "faible": "B (data) -> C (training)",
    "a appris": "-",
    "domaine sans besoin de LoRA": "retirer la LoRA du routing",
    "basse confiance": "re-miner du held-out",
}


def _score_one(domain: str, item: dict) -> float:
    """Composite [0,1] for one answered held-out item: functional if
    available, else the LLM-judge (0-10 normalised to 0-1)."""
    fn = functional_score(domain, item["answer"], item.get("reference", ""))
    if fn is not None:
        return float(fn["composite"])
    score = judge_one(domain, item["prompt"], item["answer"])
    return (score / 10.0) if score is not None else 0.0


def eval_domain(domain: str) -> dict:
    """Run + score one domain; returns an aggregate row."""
    heldout = [json.loads(l) for l in
               (HELDOUT_DIR / f"{domain}.clean.jsonl").read_text().splitlines() if l]
    n = len(heldout)
    base = run_config(heldout, "base", "Qwen3-4B-Instruct-2507")
    lora = run_config(heldout, "lora", f"ailiance-{domain}")
    base_s = mean(_score_one(domain, it) for it in base) if base else 0.0
    lora_s = mean(_score_one(domain, it) for it in lora) if lora else 0.0
    v = verdict(base_s, lora_s, n)
    return {"domain": domain, "n": n, "base_score": base_s,
            "lora_score": lora_s, "verdict": v, "routed_to": _ROUTE[v]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", nargs="*", default=list(DOMAINS))
    args = ap.parse_args()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for domain in args.domains:
        try:
            rows.append(eval_domain(domain))
        except Exception as e:  # noqa: BLE001 — per-domain isolation
            print(f"{domain}: FAILED {e!r}")
            rows.append({"domain": domain, "n": 0, "base_score": 0.0,
                         "lora_score": 0.0, "verdict": "basse confiance",
                         "routed_to": _ROUTE["basse confiance"]})
    (RESULTS_DIR / "mascarade-eval.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False))
    (RESULTS_DIR / "mascarade-eval-report.md").write_text(render_report(rows))
    print(f"report -> {RESULTS_DIR / 'mascarade-eval-report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Follows the Phase-N pattern (recon: `bench_phase7_cuda.py`). Per-domain
`try/except` isolation — one domain failing never aborts the run.

- [ ] **Step 2: Write the smoke test** — run `run_eval.py` on one domain with a 3-item fixture held-out file and mocked HTTP, assert `results/mascarade-eval-report.md` is produced with one verdict row.

- [ ] **Step 3: Run the smoke test**

Run: `cd mascarade-eval && python -m pytest tests/test_run_eval_smoke.py -v`
Expected: PASS

- [ ] **Step 4: Full test sweep**

Run: `cd mascarade-eval && python -m pytest tests/ -v`
Expected: PASS — all tests green.

- [ ] **Step 5: Commit**

```bash
git add mascarade-eval/mascarade_eval/run_eval.py mascarade-eval/tests/test_run_eval_smoke.py
git commit -m "feat(eval): CLI orchestrator and e2e smoke"
```

---

## Verification (end-to-end, after implementation)

1. `cd mascarade-eval && python -m pytest tests/ -v` — all unit + smoke tests green.
2. `python -m mascarade_eval.mine_upstream --cutoff-date <date> --domains power` then leakage-filter — `heldout/power.clean.jsonl` exists, dropped count logged.
3. `python -m mascarade_eval.run_eval --domains power` — `results/mascarade-eval-report.md` produced with a `power` verdict.
4. Full run, 10 domains — report has 10 rows; any domain with `< MIN_HELDOUT` clean items shows `basse confiance` (no silent verdict).

## Decisions

- **Leakage check is dependency-free** (stdlib hashing + shingled Jaccard) rather than `datasketch`/MinHash — the corpora are small enough that O(n·m) Jaccard is fine, and it avoids a new dependency.
- **Functional scorers reused, not rewritten** — `scorers.py` imports `bench_kicad_functional` via `sys.path` (the recon's established cross-script pattern).
- **`mine_upstream.mine()` is the one deferred body** — gated by Task 1's research, by design; everything else has complete code here.

## Risks

- **R1 — thin held-out yield per domain.** Some domains may not have ≥20 fresh upstream items. Mitigation: `MIN_HELDOUT` floor → `basse confiance` verdict, explicit, never silent.
- **R2 — judge variance.** The ~12% external spot-check quantifies home-judge bias; if disagreement is high, the verdict notes low judge-confidence.
- **R3 — Task 1 finds no clean time-cut source for a domain.** Then that domain falls back to hand-curated held-out (small, flagged) — captured in `heldout-sources.md`.

## Out of scope

Sub-projects B (dataset quality) and C (training recipe) — gated by this harness's report.
