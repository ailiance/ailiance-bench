#!/usr/bin/env python3
"""bench_phase7_cuda.py — CUDA port of ailiance-bench Phase 1 functional eval
for the 10 published `Ailiance-fr/qwen3-4b-mascarade-*-lora` adapters.

Reuses parsers & scorers from the original MLX bench
(`~/ailiance-bench/scripts/bench_kicad_functional.py`) via sys.modules
stubbing of the MLX import, then swaps the loader + generate functions
for transformers / PEFT on CUDA.

Outputs:
  - /tmp/phase7_results/qwen3-4b-mascarade-<lora>_phase1.json
  - /tmp/phase7_results/_phase7_summary.md
  - (with --update-cards) replaces the "## Bench results" section in
    each LoRA's HF card with the real Phase 7 functional numbers.

Datasets pulled from /home/kxkm/phase7_data/*_valid.jsonl
(staged from Studio ~/eu-kiki/data/hf-traced/<dataset>/valid.jsonl).

Usage:
  python bench_phase7_cuda.py                       # all 10 LoRA, all 4 ds
  python bench_phase7_cuda.py --loras kicad,spice   # selected
  python bench_phase7_cuda.py --datasets kicad-dsl  # selected
  python bench_phase7_cuda.py --n-samples 5         # quick smoke
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import tempfile
import time
import types
from pathlib import Path

# Stub mlx_lm BEFORE importing the bench module so its top-level
# `from mlx_lm import load, generate` doesn't ImportError.
_mlx = types.ModuleType("mlx_lm")
_mlx.load = lambda *a, **k: None       # never called
_mlx.generate = lambda *a, **k: None   # never called
sys.modules["mlx_lm"] = _mlx

BENCH_SCRIPTS = Path.home() / "ailiance-bench" / "scripts"
sys.path.insert(0, str(BENCH_SCRIPTS))

# Now safe to import the parsers / scorers (they don't actually call mlx_lm).
from bench_kicad_functional import (  # noqa: E402
    DATASETS as _DEFAULT_DATASETS,
    GEN_PARAMS,
    parse_spice,
    score_spice,
    log as _bench_log,  # noqa: F401
)

# kicad-dsl / kicad-pcb scorers exist in the bench module, locate them dynamically.
import bench_kicad_functional as _bkf  # noqa: E402


# Map dataset → scorer name in bench_kicad_functional (real names are
# `score_dsl`, `score_pcb`, `score_spice` — short, not `score_kicad_*`).
_SCORER_NAMES = {
    "kicad-dsl":     "score_dsl",
    "kicad-pcb":     "score_pcb",
    "spice-sim":     "score_spice",
    "emc-dsp-power": "score_spice",  # SPICE-shaped output expected
}
SCORERS = {ds: (getattr(_bkf, fn, None), None) for ds, fn in _SCORER_NAMES.items()}

DATA_DIR = Path("/home/kxkm/phase7_data")
RESULTS_DIR = Path("/tmp/phase7_results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

HF_ORG = "Ailiance-fr"
BASE_MODEL = "Qwen/Qwen3-4B-Instruct-2507"

LORA_DOMAINS = [
    "kicad", "spice", "stm32", "emc", "embedded",
    "platformio", "freecad", "dsp", "iot", "power",
]

# Mapping (domain → dataset) — which Phase 1 ds to run for each LoRA.
# Conservative: only run datasets we have AND that match the LoRA's specialty.
DOMAIN_TO_DATASETS = {
    "kicad":      ["kicad-dsl", "kicad-pcb"],
    "spice":      ["spice-sim", "emc-dsp-power"],
    "emc":        ["emc-dsp-power"],
    "power":      ["emc-dsp-power"],
    "dsp":        ["emc-dsp-power"],
    "stm32":      [],   # no Phase 1 ds covers this directly — eval via mascarade-stm32-dataset only
    "embedded":   [],
    "platformio": [],
    "freecad":    [],
    "iot":        [],
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("phase7")


def load_samples(dataset: str, n: int) -> list[dict]:
    """Load `valid.jsonl` for a dataset, return first n (prompt, expected) rows."""
    path = DATA_DIR / f"{dataset}_valid.jsonl"
    if not path.exists():
        log.error("dataset valid file not found: %s", path)
        return []
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            msgs = d.get("messages", [])
            user = next((m["content"] for m in msgs if m.get("role") == "user"), None)
            asst = next((m["content"] for m in msgs if m.get("role") == "assistant"), None)
            if user and asst:
                rows.append({"prompt": user, "expected": asst})
            if len(rows) >= n:
                break
    return rows


def cuda_load_lora(domain: str):
    """Load base + LoRA from HF onto CUDA."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    log.info("loading base %s + lora %s/qwen3-4b-mascarade-%s-lora",
             BASE_MODEL, HF_ORG, domain)
    tok = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, torch_dtype=torch.bfloat16,
        device_map="auto", trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(model, f"{HF_ORG}/qwen3-4b-mascarade-{domain}-lora")
    model.eval()
    return model, tok


def cuda_generate(model, tok, prompt: str, max_tokens: int) -> str:
    import torch
    text = tok.apply_chat_template(
        [{"role": "user", "content": prompt}],
        tokenize=False, add_generation_prompt=True,
    )
    inputs = tok(text, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            do_sample=False,  # greedy for reproducibility
            pad_token_id=tok.pad_token_id,
        )
    return tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)


def eval_lora_on_dataset(model, tok, domain: str, dataset: str, n_samples: int) -> dict:
    scorer_pair = SCORERS.get(dataset)
    if not scorer_pair or scorer_pair[0] is None:
        return {"dataset": dataset, "status": "no_scorer"}

    score_fn = scorer_pair[0]
    rows = load_samples(dataset, n_samples)
    if not rows:
        return {"dataset": dataset, "status": "no_samples"}

    max_tokens = GEN_PARAMS.get(dataset, {}).get("max_tokens", 1024)
    per_sample = []
    t0 = time.perf_counter()

    for i, row in enumerate(rows):
        try:
            gen = cuda_generate(model, tok, row["prompt"], max_tokens)
        except Exception as e:
            log.warning("  [%s/%s] sample %d gen FAILED: %r", domain, dataset, i, e)
            continue
        try:
            sc = score_fn(gen, row["expected"])
        except Exception as e:
            log.warning("  [%s/%s] sample %d score FAILED: %r", domain, dataset, i, e)
            continue
        composite = sc.get("composite", sc.get("score", None))
        per_sample.append({
            "i": i,
            "scores": {k: v for k, v in sc.items() if isinstance(v, (int, float, bool))},
            "composite": composite,
        })
        log.info("  [%s/%s] %d/%d composite=%s",
                 domain, dataset, i + 1, len(rows), composite)

    dt = time.perf_counter() - t0
    composites = [s["composite"] for s in per_sample if isinstance(s["composite"], (int, float))]
    return {
        "dataset": dataset,
        "status": "ok",
        "n_samples": len(per_sample),
        "avg_composite": round(sum(composites) / len(composites), 3) if composites else None,
        "duration_s": round(dt, 1),
        "samples": per_sample[:5],
    }


def update_card(domain: str, snippet: str) -> bool:
    import tempfile, re
    from huggingface_hub import HfApi, hf_hub_download

    api = HfApi()
    repo = f"{HF_ORG}/qwen3-4b-mascarade-{domain}-lora"
    try:
        path = hf_hub_download(repo_id=repo, filename="README.md", repo_type="model")
        readme = open(path).read()
    except Exception as e:
        log.error("card fetch failed %s: %r", repo, e)
        return False

    new_section = snippet.lstrip("\n")
    pattern = re.compile(r"## Bench results.*?(?=\n## |\Z)", re.S)
    if pattern.search(readme):
        new_readme = pattern.sub(new_section, readme, count=1)
    else:
        if "## Citations" in readme:
            new_readme = readme.replace("## Citations", new_section + "\n## Citations", 1)
        else:
            new_readme = readme.rstrip() + "\n\n" + new_section
    if new_readme == readme:
        return True
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as tf:
        tf.write(new_readme)
        tmp = tf.name
    try:
        api.upload_file(
            path_or_fileobj=tmp,
            path_in_repo="README.md",
            repo_id=repo,
            repo_type="model",
            commit_message=f"docs: Phase 7 CUDA bench results ({domain})",
        )
        return True
    finally:
        os.unlink(tmp)


def card_snippet(domain: str, results: list[dict]) -> str:
    if not results:
        return "\n## Bench results — ailiance-bench Phase 7 (CUDA)\n\n_No Phase 1 dataset matches this LoRA's specialty._\n"
    rows = []
    for r in results:
        ds = r["dataset"]
        s = r.get("status")
        if s == "ok":
            rows.append(f"| `{ds}` | {r['n_samples']} | **{r['avg_composite']}** | {r['duration_s']}s |")
        else:
            rows.append(f"| `{ds}` | — | _{s}_ | — |")
    table = "\n".join(rows)
    return (
        "\n## Bench results — ailiance-bench Phase 7 (CUDA, 2026-05-11)\n\n"
        "Functional eval via the parsers/scorers from "
        "[`ailiance/ailiance-bench`](https://github.com/ailiance/ailiance-bench) "
        "Phase 1 (`bench_kicad_functional`), ported to CUDA / transformers + PEFT "
        f"for the Qwen3-4B-Instruct-2507 base.\n\n"
        "| Dataset | n | Composite score | Duration |\n|---|---:|---:|---:|\n"
        + table + "\n\n"
        "_Composite score combines structural-parse-ok, component-count match, "
        "ground-node presence, etc. — see `bench_kicad_functional.score_*` for "
        "the exact formula. Greedy decoding, max_tokens per `GEN_PARAMS`._\n"
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--loras", default=",".join(LORA_DOMAINS))
    p.add_argument("--datasets", default=None,
                   help="comma-separated subset, or default (mapping per LoRA)")
    p.add_argument("--n-samples", type=int, default=10)
    p.add_argument("--update-cards", action="store_true")
    args = p.parse_args()

    requested_loras = [d.strip() for d in args.loras.split(",") if d.strip()]
    forced_datasets = (
        [d.strip() for d in args.datasets.split(",")] if args.datasets else None
    )

    all_report = {"base_model": BASE_MODEL, "n_samples": args.n_samples, "loras": []}

    for domain in requested_loras:
        datasets = forced_datasets or DOMAIN_TO_DATASETS.get(domain, [])
        if not datasets:
            log.info("=== %s : no matching Phase 1 dataset, skipping ===", domain)
            all_report["loras"].append({"domain": domain, "status": "no_matching_dataset"})
            continue

        log.info("=== %s (datasets=%s) ===", domain, datasets)
        try:
            model, tok = cuda_load_lora(domain)
        except Exception as e:
            log.error("load failed %s: %r", domain, e)
            all_report["loras"].append({"domain": domain, "status": "load_failed", "error": repr(e)})
            continue

        per_ds = []
        for ds in datasets:
            r = eval_lora_on_dataset(model, tok, domain, ds, args.n_samples)
            per_ds.append(r)

        all_report["loras"].append({
            "domain": domain,
            "status": "ok",
            "datasets": per_ds,
        })

        # write per-LoRA JSON
        out_json = RESULTS_DIR / f"qwen3-4b-mascarade-{domain}_phase7.json"
        out_json.write_text(json.dumps({"domain": domain, "datasets": per_ds}, indent=2, ensure_ascii=False))

        if args.update_cards:
            snip = card_snippet(domain, per_ds)
            ok = update_card(domain, snip)
            log.info("  card update %s -> %s", domain, ok)

        # free VRAM
        import gc, torch
        del model
        gc.collect()
        torch.cuda.empty_cache()

    summary = RESULTS_DIR / "_phase7_summary.md"
    lines = [
        "# Phase 7 CUDA bench summary",
        "",
        f"Base: `{BASE_MODEL}`",
        f"N samples per (LoRA, dataset): {args.n_samples}",
        "",
        "| LoRA | Dataset | Status | n | Composite | Duration |",
        "|---|---|---|---:|---:|---:|",
    ]
    for L in all_report["loras"]:
        d = L["domain"]
        if L.get("status") != "ok":
            lines.append(f"| {d} | — | _{L.get('status')}_ | — | — | — |")
            continue
        for ds in L.get("datasets", []):
            lines.append(
                f"| {d} | {ds['dataset']} | {ds.get('status')} | {ds.get('n_samples','—')} | "
                f"{ds.get('avg_composite','—')} | {ds.get('duration_s','—')}s |"
            )
    summary.write_text("\n".join(lines))
    log.info("summary written -> %s", summary)
    (RESULTS_DIR / "_phase7_all.json").write_text(json.dumps(all_report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
