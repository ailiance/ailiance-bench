#!/usr/bin/env python3
"""bench_phase9_baseline_forgetting.py — baseline + cross-domain forgetting matrix.

Two evals in one pass (sharing the loaded base model for efficiency):

1. BASELINE (1 pass): Qwen3-4B-Instruct-2507 base WITHOUT any LoRA,
   run on every domain's eval set (mascarade-<domain>-dataset, seed=101).
   Gives the comparison floor for `base vs +mascarade-X | Δ`.

2. CROSS-DOMAIN FORGETTING (10 LoRA × 9 other domains): for each LoRA,
   run on the OTHER 9 domains' eval sets. If the LoRA degrades base
   performance on out-of-domain → catastrophic forgetting confirmed.

Metric used: Jaccard token-overlap (same as eval_mascarade_lora.py for
cross-comparability). Functional Phase 7+8 metrics are too domain-specific
for cross-domain matrix.

Outputs:
  - /tmp/phase9_results/baseline.json
  - /tmp/phase9_results/forgetting_matrix.json
  - /tmp/phase9_results/_phase9_summary.md
  - --update-cards: appends "## Cross-domain forgetting check" section
    to each LoRA card with Δ vs base on in-domain + 4 sample other-domains.

Usage:
  python bench_phase9_baseline_forgetting.py
  python bench_phase9_baseline_forgetting.py --skip-baseline   # if already run
  python bench_phase9_baseline_forgetting.py --n-samples 5     # quicker
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import tempfile
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("phase9")

HF_ORG = "Ailiance-fr"
BASE_MODEL = "Qwen/Qwen3-4B-Instruct-2507"
RESULTS_DIR = Path("/tmp/phase9_results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DOMAINS = [
    "kicad", "spice", "stm32", "emc", "embedded",
    "platformio", "freecad", "dsp", "iot", "power",
]


def load_eval_samples(domain: str, n: int = 10) -> list[dict]:
    """Pull held-out samples from Ailiance-fr/mascarade-<domain>-dataset, seed=101."""
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(
        repo_id=f"{HF_ORG}/mascarade-{domain}-dataset",
        filename=f"{domain}_chat.jsonl",
        repo_type="dataset",
    )
    with open(path) as f:
        lines = [line for line in f if line.strip()]
    random.seed(101)  # same seed as Phase 7+8 for cross-comparable samples
    chosen = random.sample(lines, min(n, len(lines)))
    out = []
    for l in chosen:
        d = json.loads(l)
        msgs = d.get("messages") or d.get("conversations") or []
        prompt, ref = "", ""
        for m in msgs:
            role = m.get("role") or m.get("from")
            content = m.get("content") or m.get("value") or ""
            if role in ("user", "human"):
                prompt = content
            elif role in ("assistant", "gpt"):
                ref = content
        if prompt and ref:
            out.append({"prompt": prompt, "ref": ref})
    return out


def jaccard(a: str, b: str) -> float:
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def load_base():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    log.info("loading base %s", BASE_MODEL)
    tok = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL, torch_dtype=torch.bfloat16,
        device_map="auto", trust_remote_code=True,
    )
    return model, tok


def attach_adapter(model, domain: str):
    """Attach a LoRA adapter to an already-loaded base model (in-place)."""
    from peft import PeftModel
    log.info("attaching lora qwen3-4b-mascarade-%s", domain)
    return PeftModel.from_pretrained(model, f"{HF_ORG}/qwen3-4b-mascarade-{domain}-lora")


def detach_adapter(peft_model):
    """Unload the LoRA, return the bare base."""
    return peft_model.unload()  # PEFT 0.10+ method


def generate(model, tok, prompt: str, max_tokens: int = 512) -> str:
    import torch
    text = tok.apply_chat_template(
        [{"role": "user", "content": prompt}],
        tokenize=False, add_generation_prompt=True,
    )
    inputs = tok(text, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **inputs, max_new_tokens=max_tokens,
            do_sample=False, pad_token_id=tok.pad_token_id,
        )
    return tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)


def eval_on_dataset(model, tok, domain: str, n_samples: int) -> dict:
    rows = load_eval_samples(domain, n_samples)
    if not rows:
        return {"domain": domain, "status": "no_samples", "avg_jaccard": None}
    overlaps = []
    t0 = time.perf_counter()
    for r in rows:
        try:
            gen = generate(model, tok, r["prompt"])
        except Exception as e:
            log.warning("  gen err: %r", e)
            continue
        overlaps.append(jaccard(gen, r["ref"]))
    dt = time.perf_counter() - t0
    return {
        "domain": domain,
        "status": "ok",
        "n_samples": len(overlaps),
        "avg_jaccard": round(sum(overlaps) / max(len(overlaps), 1), 3),
        "duration_s": round(dt, 1),
    }


def run_baseline(model, tok, n_samples: int) -> dict:
    """Run base (no LoRA) on every domain's eval set."""
    log.info("=== BASELINE pass (base only) ===")
    res = {}
    for d in DOMAINS:
        log.info("[baseline / %s]", d)
        res[d] = eval_on_dataset(model, tok, d, n_samples)
    return res


def run_forgetting(model, tok, n_samples: int, baseline: dict) -> dict:
    """For each LoRA, run on EVERY domain. Compare in-domain (target) vs out-of-domain."""
    from peft import PeftModel

    matrix = {}
    for lora_domain in DOMAINS:
        log.info("=== FORGETTING : lora=%s ===", lora_domain)
        try:
            peft_model = attach_adapter(model, lora_domain)
            peft_model.eval()
        except Exception as e:
            log.error("  attach %s failed: %r", lora_domain, e)
            matrix[lora_domain] = {"status": "attach_failed", "error": repr(e)}
            continue

        row = {}
        for eval_domain in DOMAINS:
            log.info("  -> eval on %s", eval_domain)
            r = eval_on_dataset(peft_model, tok, eval_domain, n_samples)
            base_j = baseline.get(eval_domain, {}).get("avg_jaccard")
            r["delta_vs_base"] = round(r["avg_jaccard"] - base_j, 3) if (
                r.get("avg_jaccard") is not None and base_j is not None
            ) else None
            row[eval_domain] = r
        matrix[lora_domain] = row

        # detach for clean next iter
        try:
            base_again = peft_model.unload()
            model = base_again
        except Exception as e:
            log.warning("  detach failed (will reload base next time): %r", e)
            # reload base from scratch
            import gc, torch
            del peft_model
            gc.collect()
            torch.cuda.empty_cache()
            model, tok = load_base()
    return matrix


def card_snippet(lora_domain: str, matrix_row: dict, baseline: dict) -> str:
    if not matrix_row or matrix_row.get("status") != "ok" and "status" in matrix_row:
        return ""
    rows = []
    in_domain_delta = None
    for eval_d, r in matrix_row.items():
        if isinstance(r, dict) and r.get("avg_jaccard") is not None:
            d = r.get("delta_vs_base")
            d_str = f"{d:+.3f}" if d is not None else "—"
            tag = " ⬅ in-domain" if eval_d == lora_domain else ""
            rows.append(f"| `{eval_d}` | {r['avg_jaccard']} | {d_str}{tag} |")
            if eval_d == lora_domain:
                in_domain_delta = d
    table = "\n".join(rows)
    # Compute out-of-domain forgetting summary
    deltas_oo = [
        r["delta_vs_base"] for ed, r in matrix_row.items()
        if isinstance(r, dict) and ed != lora_domain
        and r.get("delta_vs_base") is not None
    ]
    avg_forget = round(sum(deltas_oo) / len(deltas_oo), 3) if deltas_oo else None

    warning = ""
    if avg_forget is not None and avg_forget < -0.05:
        warning = (
            "\n⚠️ **Catastrophic forgetting observed** : average Jaccard "
            f"drop of {avg_forget} on out-of-domain prompts vs base. "
            "Use this LoRA only for **in-domain** prompts; for "
            "multi-domain hardware QA prefer the router auto-selection "
            "via the `ailiance` gateway alias.\n"
        )

    return (
        "\n## Cross-domain forgetting check (Phase 9, 2026-05-11)\n\n"
        f"For each domain's eval set (seed=101, n samples held-out), "
        f"compare this LoRA's Jaccard token-overlap vs the Qwen3-4B-Instruct-2507 "
        f"**baseline (no adapter)** on the SAME prompts. Negative Δ = the LoRA "
        f"degrades base behaviour on that domain.\n\n"
        "| Eval domain | LoRA Jaccard | Δ vs base |\n|---|---:|---:|\n"
        + table + "\n\n"
        f"**In-domain Δ**: {in_domain_delta if in_domain_delta is not None else '—'}  "
        f"**Out-of-domain mean Δ**: {avg_forget if avg_forget is not None else '—'}"
        + warning + "\n"
    )


def update_card(lora_domain: str, snippet: str) -> bool:
    from huggingface_hub import HfApi, hf_hub_download

    api = HfApi()
    repo = f"{HF_ORG}/qwen3-4b-mascarade-{lora_domain}-lora"
    try:
        path = hf_hub_download(repo_id=repo, filename="README.md", repo_type="model")
        readme = open(path).read()
    except Exception as e:
        log.error("card fetch %s failed: %r", repo, e)
        return False
    if "## Cross-domain forgetting check" in readme:
        # replace existing section
        new_readme = re.sub(
            r"## Cross-domain forgetting check.*?(?=\n## |\Z)",
            snippet.lstrip("\n"),
            readme, count=1, flags=re.S,
        )
    else:
        new_readme = readme.rstrip() + "\n" + snippet
    if new_readme == readme:
        return True
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as tf:
        tf.write(new_readme)
        tmp = tf.name
    try:
        api.upload_file(
            path_or_fileobj=tmp, path_in_repo="README.md",
            repo_id=repo, repo_type="model",
            commit_message=f"docs: Phase 9 cross-domain forgetting matrix ({lora_domain})",
        )
        return True
    finally:
        os.unlink(tmp)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n-samples", type=int, default=5,
                   help="Samples per (LoRA, eval-domain) cell. 5 = 500 generations total.")
    p.add_argument("--skip-baseline", action="store_true",
                   help="Reuse cached baseline.json if exists")
    p.add_argument("--skip-forgetting", action="store_true")
    p.add_argument("--update-cards", action="store_true")
    args = p.parse_args()

    model, tok = load_base()

    # 1. Baseline
    baseline_path = RESULTS_DIR / "baseline.json"
    if args.skip_baseline and baseline_path.exists():
        log.info("loading cached baseline")
        baseline = json.loads(baseline_path.read_text())
    else:
        baseline = run_baseline(model, tok, args.n_samples)
        baseline_path.write_text(json.dumps(baseline, indent=2, ensure_ascii=False))

    if args.skip_forgetting:
        log.info("--skip-forgetting set, done after baseline")
        return

    # 2. Cross-domain forgetting matrix
    matrix = run_forgetting(model, tok, args.n_samples, baseline)
    matrix_path = RESULTS_DIR / "forgetting_matrix.json"
    matrix_path.write_text(json.dumps(matrix, indent=2, ensure_ascii=False))

    # 3. Update cards if requested
    if args.update_cards:
        for lora_d in DOMAINS:
            row = matrix.get(lora_d)
            if not row:
                continue
            snippet = card_snippet(lora_d, row, baseline)
            ok = update_card(lora_d, snippet)
            log.info("  card %s -> %s", lora_d, ok)

    # 4. Summary markdown
    lines = ["# Phase 9 — Baseline + Cross-domain Forgetting Matrix\n",
             f"Base: `{BASE_MODEL}`",
             f"Samples per cell: {args.n_samples} (seed=101 from mascarade-<dom>-dataset)\n",
             "## Baseline (Qwen3-4B no adapter)\n",
             "| Domain | Jaccard | Duration |", "|---|---:|---:|"]
    for d in DOMAINS:
        r = baseline.get(d, {})
        lines.append(f"| {d} | {r.get('avg_jaccard','—')} | {r.get('duration_s','—')}s |")

    lines += ["\n## Forgetting matrix — Δ vs baseline\n",
              "Rows = LoRA, columns = eval domain. Diagonal = in-domain (expected positive).\n"]
    header = "| LoRA \\ Eval | " + " | ".join(DOMAINS) + " |"
    sep = "|---|" + "|".join(["---:"] * len(DOMAINS)) + "|"
    lines += [header, sep]
    for lora_d in DOMAINS:
        row = matrix.get(lora_d, {})
        cells = []
        for ed in DOMAINS:
            r = row.get(ed, {}) if isinstance(row, dict) else {}
            d = r.get("delta_vs_base") if isinstance(r, dict) else None
            cells.append(f"{d:+.3f}" if isinstance(d, (int, float)) else "—")
        lines.append(f"| {lora_d} | " + " | ".join(cells) + " |")
    (RESULTS_DIR / "_phase9_summary.md").write_text("\n".join(lines))
    log.info("done. results in %s", RESULTS_DIR)


if __name__ == "__main__":
    main()
