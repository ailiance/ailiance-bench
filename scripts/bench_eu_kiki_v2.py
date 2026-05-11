#!/usr/bin/env python3
"""EU-KIKI v2 comprehensive benchmark — all domains, base vs LoRA.

Metrics per domain:
  1. Perplexity on valid.jsonl (25 samples)
  2. Generation quality: keyword hit rate, response length, degenerate %
  3. Domain specificity score

Comparisons:
  - Base vs LoRA for Qwen3.6-35B-A3B
  - Base vs LoRA for Medium 3.5 128B
  - Qwen36-LoRA vs Medium35-LoRA on shared domains

Usage:
    python scripts/bench_eu_kiki_v2.py                    # full bench
    python scripts/bench_eu_kiki_v2.py --qwen-only        # Qwen36 only
    python scripts/bench_eu_kiki_v2.py --medium-only      # Medium35 only
    python scripts/bench_eu_kiki_v2.py --ppl-only         # perplexity only (fast)
    python scripts/bench_eu_kiki_v2.py --domains cpp rust  # specific domains

Portability:
    The script reads paths from env vars (with sensible HOME-relative fallbacks)
    so it works on any machine. Override via:

      KIKI_TUNNER_DIR        — KIKI-Mac_tunner repo root  (default ~/KIKI-Mac_tunner)
      EUKIKI_DATA_DIR        — hf-traced datasets dir     (default ~/ailiance/data/hf-traced)
      EUKIKI_CURRICULUM_DIR  — LoRA curriculum dir        (default $KIKI_TUNNER_DIR/output/ailiance-v2-curriculum)
      BENCH_RESULTS_DIR      — JSON/MD output dir         (default ~/ailiance-bench/bench-results)
      QWEN_BF16_MODEL        — Qwen36 BF16 model path     (default $KIKI_TUNNER_DIR/models/Qwen3.6-35B-A3B-MLX-BF16)
      MEDIUM_BF16_MODEL      — Medium35 BF16 model path   (default $KIKI_TUNNER_DIR/models/Mistral-Medium-3.5-128B-BF16)

    Example (macM1 with electron home):
      EUKIKI_DATA_DIR=~/ailiance-data/hf-traced python scripts/bench_eu_kiki_v2.py --ppl-only
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
import sys
from pathlib import Path
from typing import Optional

import mlx.core as mx
import mlx.nn as nn
from mlx_lm import load, generate

# ─── Paths (env-overridable, see docstring) ───────────────────────────────────

HOME = Path.home()
TUNNER = Path(os.environ.get("KIKI_TUNNER_DIR", HOME / "KIKI-Mac_tunner"))
DATA_DIR = Path(os.environ.get("EUKIKI_DATA_DIR", HOME / "ailiance" / "data" / "hf-traced"))
CURRICULUM_DIR = Path(os.environ.get(
    "EUKIKI_CURRICULUM_DIR", TUNNER / "output" / "ailiance-v2-curriculum"))
RESULTS_DIR = Path(os.environ.get(
    "BENCH_RESULTS_DIR", HOME / "ailiance-bench" / "bench-results"))

QWEN_MODEL = os.environ.get(
    "QWEN_BF16_MODEL", str(TUNNER / "models" / "Qwen3.6-35B-A3B-MLX-BF16"))
MEDIUM_MODEL = os.environ.get(
    "MEDIUM_BF16_MODEL", str(TUNNER / "models" / "Mistral-Medium-3.5-128B-BF16"))

# ─── Domain keywords (for generation quality scoring) ─────────────────────────

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "chat-fr": ["français", "expliqu", "bonjour", "merci", "comment", "pourquoi"],
    "cpp": ["std::", "#include", "template", "nullptr", "class ", "virtual"],
    "docker-devops": ["Dockerfile", "container", "docker", "deploy", "CI", "pipeline"],
    "embedded": ["GPIO", "UART", "I2C", "SPI", "interrupt", "register", "firmware"],
    "emc-dsp-power": ["EMI", "filter", "converter", "inductor", "FFT", "bandwidth"],
    "freecad": ["FreeCAD", "sketch", "Part", "parametric", "extrude", "macro"],
    "html-css": ["CSS", "grid", "flexbox", "responsive", "media", "layout"],
    "iot": ["MQTT", "sensor", "gateway", "protocol", "WiFi", "edge"],
    "kicad-dsl": ["symbol", "footprint", "pin", "schematic", "KiCad", "net"],
    "kicad-pcb": ["PCB", "trace", "via", "copper", "layer", "DRC"],
    "llm-ops": ["deploy", "inference", "model", "serve", "quantiz", "batch"],
    "llm-orch": ["agent", "chain", "prompt", "orchestrat", "tool", "LLM"],
    "lua-upy": ["function", "require", "micropython", "lua", "table", "coroutine"],
    "math-gsm8k": ["calculate", "total", "answer", "step", "equation", "result"],
    "math-reasoning": ["prove", "theorem", "equation", "therefore", "implies"],
    "ml-training": ["epoch", "loss", "gradient", "batch", "train", "optimizer"],
    "multilingual-eu": ["traduction", "langue", "translation", "européen"],
    "music-audio": ["frequency", "audio", "signal", "waveform", "sample", "MIDI"],
    "platformio": ["platformio", "board", "upload", "serial", "monitor", "lib"],
    "python": ["def ", "import ", "return", "class ", "self.", "python"],
    "rust": ["fn ", "let ", "impl ", "struct ", "Result<", "Option<"],
    "rust-embedded": ["no_std", "cortex", "hal", "embedded", "pac", "interrupt"],
    "security-fenrir": ["vulnerability", "exploit", "secure", "audit", "CVE"],
    "shell": ["#!/bin", "grep", "awk", "pipe", "stdout", "bash"],
    "spice-sim": ["netlist", ".tran", "subckt", "ngspice", "simulation", "SPICE"],
    "sql": ["SELECT", "FROM", "WHERE", "JOIN", "INDEX", "GROUP BY"],
    "traduction-tech": ["traduction", "technique", "terme", "glossaire", "source"],
    "typescript": ["interface", "const ", "type ", "async", "Promise", "generic"],
    "web-backend": ["API", "endpoint", "middleware", "route", "REST", "server"],
    "web-frontend": ["React", "component", "render", "state", "hook", "CSS"],
    "yaml-json": ["yaml", "json", "schema", "config", "deploy", "workflow"],
    # Domains without training data (skipped automatically)
    "electronics": ["MOSFET", "transistor", "amplifier", "impedance"],
    "stm32": ["STM32", "HAL", "DMA", "ADC", "timer", "peripheral"],
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def load_valid_data(domain: str, max_samples: int = 25) -> list[dict]:
    valid_file = DATA_DIR / domain / "valid.jsonl"
    if not valid_file.exists():
        return []
    samples = []
    with open(valid_file) as f:
        for line in f:
            if len(samples) >= max_samples:
                break
            try:
                obj = json.loads(line)
                msgs = obj.get("messages", [])
                if len(msgs) >= 2:
                    samples.append({
                        "prompt": msgs[0]["content"],
                        "reference": msgs[1]["content"],
                    })
            except json.JSONDecodeError:
                continue
    return samples


def compute_ppl(model, tokenizer, texts: list[str], max_samples: int = 25) -> float:
    """Perplexity on validation texts. No clamping — report raw values."""
    mx.random.seed(42)
    losses = []
    for text in texts[:max_samples]:
        tokens = mx.array(tokenizer.encode(text))
        if len(tokens) < 2:
            continue
        # Truncate to avoid OOM on very long sequences
        tokens = tokens[:4096]
        logits = model(tokens[None, :-1])
        targets = tokens[1:]
        loss = mx.mean(
            nn.losses.cross_entropy(logits.squeeze(0), targets)
        ).item()
        losses.append(loss)
        mx.eval(mx.zeros(1))
    if not losses:
        return 999.0
    avg_loss = sum(losses) / len(losses)
    # No clamp: report actual perplexity (cap at 1e6 to avoid inf display)
    return min(math.exp(avg_loss), 1_000_000.0)


def compute_keyword_rate(text: str, domain: str) -> float:
    """Keyword presence rate — penalizes repetitive regurgitation.

    A keyword only counts once. Additionally, if >60% of the response
    is a single repeated token/phrase, score is halved (anti-regurgitation).
    """
    keywords = DOMAIN_KEYWORDS.get(domain, [])
    if not keywords:
        return 0.0
    text_lower = text.lower()
    # Each keyword counted at most once
    hits = sum(1 for kw in keywords if kw.lower() in text_lower)
    rate = hits / len(keywords)

    # Anti-regurgitation: penalize if response is mostly repeated content
    words = text.split()
    if len(words) > 10:
        unique_ratio = len(set(words)) / len(words)
        if unique_ratio < 0.3:  # >70% repeated words
            rate *= 0.25
        elif unique_ratio < 0.5:  # >50% repeated words
            rate *= 0.5

    return rate


def generate_safe(model, tokenizer, prompt: str, max_tokens: int = 256) -> str:
    """Generate with proper chat template and thinking disabled."""
    try:
        mx.random.seed(42)
        messages = [{"role": "user", "content": prompt}]
        # Apply chat template with thinking disabled (Qwen3.x trap)
        try:
            formatted = tokenizer.apply_chat_template(
                messages, add_generation_prompt=True,
                enable_thinking=False, tokenize=False,
            )
        except TypeError:
            # Tokenizer doesn't support enable_thinking kwarg
            formatted = tokenizer.apply_chat_template(
                messages, add_generation_prompt=True, tokenize=False,
            )
        return generate(model, tokenizer, prompt=formatted,
                        max_tokens=max_tokens, verbose=False)
    except Exception as e:
        return f"[ERROR] {e}"


def bench_domain(
    model, tokenizer, domain: str, samples: list[dict],
    model_name: str, ppl_only: bool = False,
) -> dict:
    t0 = time.time()

    # 1. Perplexity
    references = [s["reference"] for s in samples]
    ppl = compute_ppl(model, tokenizer, references)

    result = {
        "domain": domain,
        "model": model_name,
        "val_ppl": round(ppl, 3),
        "n_valid_samples": len(samples),
    }

    # 2-4. Generation metrics (skip if ppl_only)
    if not ppl_only:
        keyword_rates = []
        resp_lens = []
        degenerate = 0
        gen_samples = samples[:5]

        for s in gen_samples:
            resp = generate_safe(model, tokenizer, s["prompt"])
            kr = compute_keyword_rate(resp, domain)
            keyword_rates.append(kr)
            resp_lens.append(len(resp))

            # Enhanced degenerate detection
            is_degen = False
            words = resp.split()
            if len(resp) < 10:
                is_degen = True  # too short
            elif len(set(words)) < 3:
                is_degen = True  # almost no vocabulary
            elif len(words) > 20 and len(set(words)) / len(words) < 0.2:
                is_degen = True  # repetition loop (>80% repeated)
            elif kr == 0.0 and len(resp) > 50:
                is_degen = True  # off-topic (long but zero domain keywords)

            if is_degen:
                degenerate += 1

        result.update({
            "avg_keyword_rate": round(
                sum(keyword_rates) / max(1, len(keyword_rates)), 3),
            "avg_resp_len": round(
                sum(resp_lens) / max(1, len(resp_lens)), 1),
            "degenerate_pct": round(
                degenerate / max(1, len(gen_samples)) * 100, 1),
        })

    elapsed = time.time() - t0
    result["elapsed_s"] = round(elapsed, 1)

    # Print inline
    kw = result.get("avg_keyword_rate", "—")
    rl = result.get("avg_resp_len", "—")
    dg = result.get("degenerate_pct", "—")
    kw_s = f"kw={kw:.2f}" if isinstance(kw, float) else "kw=—"
    rl_s = f"len={rl:>6.0f}" if isinstance(rl, float) else "len=—"
    dg_s = f"degen={dg:>4.0f}%" if isinstance(dg, float) else "degen=—"
    print(f"  {domain:<20} ppl={ppl:>8.2f}  {kw_s}  {rl_s}  {dg_s}  ({elapsed:.0f}s)")

    return result


def find_completed_domains(prefix: str) -> list[str]:
    domains = []
    for d in sorted(CURRICULUM_DIR.glob(f"{prefix}-*")):
        if (d / "phase3_done").exists():
            domain = d.name.replace(f"{prefix}-", "")
            domains.append(domain)
    return domains


def find_partial_domains(prefix: str) -> list[str]:
    """Domains with at least phase1_done but not phase3_done."""
    domains = []
    for d in sorted(CURRICULUM_DIR.glob(f"{prefix}-*")):
        if (d / "phase1_done").exists() and not (d / "phase3_done").exists():
            domain = d.name.replace(f"{prefix}-", "")
            domains.append(domain)
    return domains


def print_table(title: str, base: list[dict], lora: list[dict]) -> dict:
    """Print comparison table and return stats."""
    if not base or not lora:
        return {}

    print(f"\n  {title}:")
    wins = {"lora": 0, "base": 0, "tie": 0}
    deltas = []

    for b in base:
        a = next((r for r in lora if r["domain"] == b["domain"]), None)
        if not a:
            continue
        delta = a["val_ppl"] - b["val_ppl"]
        deltas.append(delta)
        w = "lora" if delta < -0.5 else "base" if delta > 0.5 else "tie"
        wins[w] += 1
        marker = "✓" if w == "lora" else "✗" if w == "base" else "="

        kw_b = b.get("avg_keyword_rate", None)
        kw_a = a.get("avg_keyword_rate", None)
        kw_delta = ""
        if kw_b is not None and kw_a is not None:
            kw_delta = f"  kw: {kw_b:.2f}→{kw_a:.2f}"

        print(f"    {b['domain']:<20} base={b['val_ppl']:>8.2f}  "
              f"lora={a['val_ppl']:>8.2f}  Δ={delta:>+7.2f}{kw_delta}  {marker}")

    matched_base = [b for b in base if any(a["domain"] == b["domain"] for a in lora)]
    matched_lora = [a for a in lora if any(b["domain"] == a["domain"] for b in base)]

    if matched_base and matched_lora:
        avg_base = sum(r["val_ppl"] for r in matched_base) / len(matched_base)
        avg_lora = sum(r["val_ppl"] for r in matched_lora) / len(matched_lora)
        pct = (avg_base - avg_lora) / avg_base * 100
        print(f"    {'─' * 60}")
        print(f"    Avg PPL: base={avg_base:.2f}  lora={avg_lora:.2f}  "
              f"improvement={pct:+.1f}%")
        print(f"    Wins: lora={wins['lora']}  base={wins['base']}  tie={wins['tie']}")

    return wins


def generate_markdown_table(results: dict, out_path: Path) -> None:
    """Generate a markdown results table."""
    lines = [
        f"# EU-KIKI v2 Benchmark — {results['metadata']['timestamp']}",
        "",
        "## Perplexity (lower = better)",
        "",
    ]

    # Qwen36 table
    if results["qwen36_base"] or results["qwen36_lora"]:
        lines.append("### Qwen3.6-35B-A3B")
        lines.append("")
        lines.append("| Domain | Base PPL | LoRA PPL | Δ | kw_rate | Status |")
        lines.append("|---|---:|---:|---:|---:|---|")

        for b in results.get("qwen36_base", []):
            a = next((r for r in results.get("qwen36_lora", [])
                       if r["domain"] == b["domain"]), None)
            if a:
                delta = a["val_ppl"] - b["val_ppl"]
                kw = a.get("avg_keyword_rate", "—")
                kw_s = f"{kw:.2f}" if isinstance(kw, float) else "—"
                marker = "✓" if delta < -0.5 else "✗" if delta > 0.5 else "="
                lines.append(
                    f"| {b['domain']} | {b['val_ppl']:.2f} | {a['val_ppl']:.2f} "
                    f"| {delta:+.2f} | {kw_s} | {marker} |")
        lines.append("")

    # Qwen36 partial (P1 only)
    if results.get("qwen36_partial_lora"):
        lines.append("### Qwen3.6 Partial (P1 only, Metal buffer crash)")
        lines.append("")
        lines.append("| Domain | Base PPL | LoRA-P1 PPL | Δ | kw_rate |")
        lines.append("|---|---:|---:|---:|---:|")
        for b in results.get("qwen36_base", []):
            a = next((r for r in results.get("qwen36_partial_lora", [])
                       if r["domain"] == b["domain"]), None)
            if a:
                delta = a["val_ppl"] - b["val_ppl"]
                kw = a.get("avg_keyword_rate", "—")
                kw_s = f"{kw:.2f}" if isinstance(kw, float) else "—"
                lines.append(
                    f"| {b['domain']} | {b['val_ppl']:.2f} | {a['val_ppl']:.2f} "
                    f"| {delta:+.2f} | {kw_s} |")
        lines.append("")

    # Medium35 table
    if results["medium35_base"] or results["medium35_lora"]:
        lines.append("### Mistral Medium 3.5 128B")
        lines.append("")
        lines.append("| Domain | Base PPL | LoRA PPL | Δ | kw_rate | Status |")
        lines.append("|---|---:|---:|---:|---:|---|")

        for b in results.get("medium35_base", []):
            a = next((r for r in results.get("medium35_lora", [])
                       if r["domain"] == b["domain"]), None)
            if a:
                delta = a["val_ppl"] - b["val_ppl"]
                kw = a.get("avg_keyword_rate", "—")
                kw_s = f"{kw:.2f}" if isinstance(kw, float) else "—"
                marker = "✓" if delta < -0.5 else "✗" if delta > 0.5 else "="
                lines.append(
                    f"| {b['domain']} | {b['val_ppl']:.2f} | {a['val_ppl']:.2f} "
                    f"| {delta:+.2f} | {kw_s} | {marker} |")
        lines.append("")

    # Cross-model
    shared = results.get("cross_model", [])
    if shared:
        lines.append("### Cross-model (Qwen36 vs Medium35 LoRA)")
        lines.append("")
        lines.append("| Domain | Qwen36 PPL | Medium35 PPL | Winner |")
        lines.append("|---|---:|---:|---|")
        for entry in shared:
            lines.append(
                f"| {entry['domain']} | {entry['qwen_ppl']:.2f} "
                f"| {entry['medium_ppl']:.2f} | {entry['winner']} |")
        lines.append("")

    out_path.write_text("\n".join(lines))
    log(f"Markdown table saved to {out_path}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="EU-KIKI v2 benchmark")
    ap.add_argument("--domains", nargs="*", default=None,
                    help="Specific domains to bench")
    ap.add_argument("--qwen-only", action="store_true",
                    help="Only bench Qwen3.6")
    ap.add_argument("--medium-only", action="store_true",
                    help="Only bench Medium 3.5")
    ap.add_argument("--ppl-only", action="store_true",
                    help="Perplexity only (skip generation, 3x faster)")
    ap.add_argument("--include-partial", action="store_true",
                    help="Also bench partial adapters (P1 only)")
    ap.add_argument("--max-samples", type=int, default=25,
                    help="Max validation samples per domain")
    args = ap.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Discover completed adapters
    qwen_complete = find_completed_domains("qwen36")
    qwen_partial = find_partial_domains("qwen36")
    medium_complete = find_completed_domains("medium35")
    shared = sorted(set(qwen_complete) & set(medium_complete))

    # All domains with valid data (for base eval)
    all_domains = sorted(set(
        d.name for d in DATA_DIR.iterdir()
        if d.is_dir() and (d / "valid.jsonl").exists()
    ))

    if args.domains:
        all_domains = [d for d in args.domains if d in all_domains]
        qwen_complete = [d for d in qwen_complete if d in args.domains]
        qwen_partial = [d for d in qwen_partial if d in args.domains]
        medium_complete = [d for d in medium_complete if d in args.domains]
        shared = sorted(set(qwen_complete) & set(medium_complete))

    log("=" * 70)
    log("EU-KIKI v2 COMPREHENSIVE BENCHMARK")
    log(f"  All domains with data:   {len(all_domains)}")
    log(f"  Qwen36 complete (P3):    {len(qwen_complete)} {qwen_complete}")
    log(f"  Qwen36 partial (P1):     {len(qwen_partial)} {qwen_partial}")
    log(f"  Medium35 complete (P3):  {len(medium_complete)} {medium_complete}")
    log(f"  Shared (cross-model):    {len(shared)} {shared}")
    log(f"  PPL only: {args.ppl_only}")
    log("=" * 70)

    results = {
        "qwen36_base": [],
        "qwen36_lora": [],
        "qwen36_partial_lora": [],
        "medium35_base": [],
        "medium35_lora": [],
        "cross_model": [],
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "qwen_model": QWEN_MODEL,
            "medium_model": MEDIUM_MODEL,
            "ppl_only": args.ppl_only,
            "max_samples": args.max_samples,
        },
    }

    # ── QWEN36 ────────────────────────────────────────────────────────────────
    if not args.medium_only:
        # Base model on ALL domains
        log(f"\n{'='*70}")
        log("QWEN3.6-35B-A3B — BASE (no adapter)")
        log(f"{'='*70}")

        model, tok = load(QWEN_MODEL)
        for domain in all_domains:
            samples = load_valid_data(domain, args.max_samples)
            if not samples:
                print(f"  {domain:<20} SKIP (no valid data)")
                continue
            r = bench_domain(model, tok, domain, samples,
                             "qwen36-base", args.ppl_only)
            results["qwen36_base"].append(r)
        del model, tok
        mx.metal.clear_cache()

        # LoRA on completed domains
        if qwen_complete:
            log(f"\n{'='*70}")
            log("QWEN3.6-35B-A3B — LoRA (complete, P3)")
            log(f"{'='*70}")

            for domain in qwen_complete:
                adapter_path = str(CURRICULUM_DIR / f"qwen36-{domain}")
                samples = load_valid_data(domain, args.max_samples)
                if not samples:
                    continue
                model, tok = load(QWEN_MODEL, adapter_path=adapter_path)
                r = bench_domain(model, tok, domain, samples,
                                 "qwen36-lora-p3", args.ppl_only)
                results["qwen36_lora"].append(r)
                del model, tok
                mx.metal.clear_cache()

        # Partial LoRA (P1 only) if requested
        if args.include_partial and qwen_partial:
            log(f"\n{'='*70}")
            log("QWEN3.6-35B-A3B — LoRA (partial, P1 only)")
            log(f"{'='*70}")

            for domain in qwen_partial:
                adapter_path = str(CURRICULUM_DIR / f"qwen36-{domain}")
                samples = load_valid_data(domain, args.max_samples)
                if not samples:
                    continue
                model, tok = load(QWEN_MODEL, adapter_path=adapter_path)
                r = bench_domain(model, tok, domain, samples,
                                 "qwen36-lora-p1", args.ppl_only)
                results["qwen36_partial_lora"].append(r)
                del model, tok
                mx.metal.clear_cache()

    # ── MEDIUM35 ──────────────────────────────────────────────────────────────
    if not args.qwen_only:
        log(f"\n{'='*70}")
        log("MEDIUM-3.5-128B — BASE (no adapter) — ALL domains")
        log(f"{'='*70}")

        model, tok = load(MEDIUM_MODEL)
        for domain in all_domains:
            samples = load_valid_data(domain, args.max_samples)
            if not samples:
                print(f"  {domain:<20} SKIP (no valid data)")
                continue
            r = bench_domain(model, tok, domain, samples,
                             "medium35-base", args.ppl_only)
            results["medium35_base"].append(r)
        del model, tok
        mx.metal.clear_cache()

        log(f"\n{'='*70}")
        log("MEDIUM-3.5-128B — LoRA (complete, P3)")
        log(f"{'='*70}")

        for domain in medium_complete:
            adapter_path = str(CURRICULUM_DIR / f"medium35-{domain}")
            samples = load_valid_data(domain, args.max_samples)
            if not samples:
                continue
            model, tok = load(MEDIUM_MODEL, adapter_path=adapter_path)
            r = bench_domain(model, tok, domain, samples,
                             "medium35-lora-p3", args.ppl_only)
            results["medium35_lora"].append(r)
            del model, tok
            mx.metal.clear_cache()

    # ── CROSS-MODEL COMPARISON ────────────────────────────────────────────────
    # Compare Qwen36 LoRA vs Medium35 LoRA on shared completed domains
    if shared and results["qwen36_lora"] and results["medium35_lora"]:
        for domain in shared:
            q = next((r for r in results["qwen36_lora"]
                       if r["domain"] == domain), None)
            m = next((r for r in results["medium35_lora"]
                       if r["domain"] == domain), None)
            if q and m:
                results["cross_model"].append({
                    "domain": domain,
                    "qwen_ppl": q["val_ppl"],
                    "medium_ppl": m["val_ppl"],
                    "winner": "Qwen36-LoRA" if q["val_ppl"] < m["val_ppl"] else "Medium35-LoRA",
                })

    # Also compare Qwen36 LoRA vs Medium35 BASE on all domains
    if results["qwen36_lora"] and results["medium35_base"]:
        results["cross_model_lora_vs_base"] = []
        for q in results["qwen36_lora"]:
            m = next((r for r in results["medium35_base"]
                       if r["domain"] == q["domain"]), None)
            if m:
                results["cross_model_lora_vs_base"].append({
                    "domain": q["domain"],
                    "qwen_lora_ppl": q["val_ppl"],
                    "medium_base_ppl": m["val_ppl"],
                    "winner": "Qwen36-LoRA" if q["val_ppl"] < m["val_ppl"] else "Medium35-Base",
                })

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    log(f"\n{'='*70}")
    log("SUMMARY")
    log(f"{'='*70}")

    print_table("QWEN36 Base vs LoRA (complete)",
                results["qwen36_base"], results["qwen36_lora"])

    if results["qwen36_partial_lora"]:
        print_table("QWEN36 Base vs LoRA (partial P1)",
                    results["qwen36_base"], results["qwen36_partial_lora"])

    print_table("MEDIUM35 Base vs LoRA",
                results["medium35_base"], results["medium35_lora"])

    if results["cross_model"]:
        print(f"\n  CROSS-MODEL (Qwen36-LoRA vs Medium35-LoRA):")
        for entry in results["cross_model"]:
            print(f"    {entry['domain']:<20} Qwen={entry['qwen_ppl']:>8.2f}  "
                  f"Medium={entry['medium_ppl']:>8.2f}  → {entry['winner']}")

    # ── SAVE ──────────────────────────────────────────────────────────────────
    ts = time.strftime("%Y%m%d-%H%M")
    json_path = RESULTS_DIR / f"ailiance-v2-bench-{ts}.json"
    md_path = RESULTS_DIR / f"ailiance-v2-bench-{ts}.md"

    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    log(f"JSON results saved to {json_path}")

    generate_markdown_table(results, md_path)

    log("BENCH COMPLETE")


if __name__ == "__main__":
    main()
