#!/usr/bin/env python3
"""
Bench Phase 2 LORA — generation .kicad_sch sur 3 adapters LoRA.

Reuse SCORING + DATASET de bench_kicad_phase2.py (DRY) ; pattern
load(base, adapter_path=...) emprunte a bench_kicad_lora.py (Phase 1 LoRA).

Combos benches (LORA_COMBOS) : voir definition ci-dessous, mirror exact
de bench_kicad_lora.py. On ignore granite-4.1-30b (pas dans LORA_COMBOS).

Sortie distincte (NE TOUCHE PAS aux fichiers base) :
  ~/bench-results/kicad_phase2_lora.json
  ~/bench-results/kicad_phase2_lora.md

Usage :
  python3 ~/scripts/bench_kicad_lora_phase2.py
  python3 ~/scripts/bench_kicad_lora_phase2.py --models gemma-e4b-eukiki-final
  python3 ~/scripts/bench_kicad_lora_phase2.py --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import gc
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any

# --- Reuse scoring / dataset / utilities from base Phase 2 ---
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from bench_kicad_phase2 import (  # noqa: E402
    BENCH_DIR,
    DEFAULT_MAX_TOKENS,
    SPI_BUS_ID,
    aggregate,
    load_samples,
    score_sch,
    _format_prompt,
)

# Sortie distincte (separe du base pour comparaison facile)
OUT_JSON = BENCH_DIR / "kicad_phase2_lora.json"
OUT_MD = BENCH_DIR / "kicad_phase2_lora.md"

# Logger local (on ne reuse pas celui du base : LOG_PATH = nouveau fichier)
import os  # noqa: E402

LOG_DIR = Path.home() / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / f"bench_kicad_lora_phase2-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
_log_fh = None


def log(msg: str) -> None:
    global _log_fh
    if _log_fh is None:
        _log_fh = LOG_PATH.open("a", buffering=1)
    line = f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if _log_fh:
        _log_fh.write(line + "\n")


# --------------------------------------------------------------------------- #
# Combos LoRA — mirror EXACT de bench_kicad_lora.py
# --------------------------------------------------------------------------- #

GEMMA_E4B_BASE = "lmstudio-community/gemma-4-E4B-it-MLX-4bit"
HOME = Path.home()

LORA_COMBOS: list[tuple[str, str, str]] = [
    # (nickname, base_hf_id, adapter_path)
    (
        "gemma-e4b-eukiki-final",
        GEMMA_E4B_BASE,
        str(HOME / "lora-adapters" / "gemma4-e4b-eukiki" / "final"),
    ),
    (
        "gemma-e4b-mascarade-final",
        GEMMA_E4B_BASE,
        str(HOME / "lora-adapters" / "gemma4-e4b-mascarade" / "final"),
    ),
    (
        "gemma-e4b-aggro-test",
        GEMMA_E4B_BASE,
        str(HOME / "lora-adapters" / "aggro-test"),
    ),
    (
        "gemma-e4b-kicad9plus-final",
        GEMMA_E4B_BASE,
        str(HOME / "lora-adapters" / "gemma4-e4b-kicad9plus" / "final"),
    ),
]


# --------------------------------------------------------------------------- #
# Generation per combo (load base + adapter once)
# --------------------------------------------------------------------------- #


def generate_for_lora_combo(nick: str, base_hf_id: str, adapter_path: str,
                            samples: list[dict], max_tokens: int) -> dict:
    log(f"  loading base {base_hf_id} + adapter {adapter_path} ...")
    t0 = time.time()
    from mlx_lm import load as mlx_load
    from mlx_lm import generate as mlx_generate

    if not Path(adapter_path).exists():
        msg = f"adapter_path missing: {adapter_path}"
        log(f"  LOAD SKIP for {nick}: {msg}")
        return {"error": msg, "n_samples": 0}

    try:
        model, tokenizer = mlx_load(base_hf_id, adapter_path=adapter_path)
    except Exception as exc:
        log(f"  LOAD FAILED for {nick}: {exc!r}")
        return {"error": f"load_failed: {exc!r}", "n_samples": 0}
    log(f"  loaded in {time.time()-t0:.1f}s")

    records = []
    for i, sample in enumerate(samples):
        sid = sample["id"]
        if sid == SPI_BUS_ID:
            log(f"     [{i+1}/{len(samples)}] skipping {sid} (sch too long for generation)")
            continue
        prompt_text = _format_prompt(tokenizer, sample["prompt"])
        t_g = time.time()
        try:
            generated = mlx_generate(
                model, tokenizer,
                prompt=prompt_text,
                max_tokens=max_tokens,
                verbose=False,
            )
        except Exception as exc:
            log(f"     [{i+1}/{len(samples)}] GEN ERROR ({sid}): {exc!r}")
            generated = ""
        dt_g = time.time() - t_g
        try:
            scores = score_sch(generated, sample["expected"])
        except Exception as exc:
            log(f"     [{i+1}/{len(samples)}] SCORE ERROR ({sid}): {exc!r} — fallback zero")
            scores = {"parse_ok": False, "composite": 0.0,
                      "starts_with_kicad_sch": False, "has_version": False,
                      "has_lib_symbols": False, "has_uuid": False,
                      "comp_count_match": 0.0, "label_count_match": 0.0,
                      "cli_proxy_score": 0.0, "structure_score": 0.0,
                      "expected_n_components": 0, "generated_n_components": 0,
                      "expected_n_labels": 0, "generated_n_labels": 0,
                      "score_error": repr(exc)}
        records.append({
            "id": sid,
            "source": sample["source"],
            "prompt": sample["prompt"][:300],
            "expected_chars": len(sample["expected"]),
            "generated_chars": len(generated),
            "generated": generated[:3000],
            "scores": scores,
            "gen_time_s": round(dt_g, 2),
        })
        log(f"     [{i+1}/{len(samples)}] {sid} composite={scores.get('composite')} "
            f"parse_ok={scores.get('parse_ok')} t={dt_g:.1f}s")

    agg = aggregate(records)
    agg["samples"] = records

    del model
    del tokenizer
    gc.collect()
    try:
        import mlx.core as mx  # type: ignore
        mx.metal.clear_cache()
    except Exception:
        pass
    return agg


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #


def write_markdown(results: dict) -> None:
    md = results["metadata"]
    lines = [
        "# KiCad Phase 2 LORA bench — generation .kicad_sch (adapters)",
        "",
        f"_Generated: {md['timestamp']}_",
        "",
        f"- Dataset    : `{md['data_path']}` ({md['n_samples_total']} samples, "
        f"{md['n_samples_eval']} evaluated)",
        f"- Combos     : {len(md['models'])}",
        f"- Max tokens : {md['max_tokens']}",
        f"- Validation : pure-Python parser (kicad-cli not used in P2)",
        "",
        "| Combo | n | parse_ok | cli_proxy | comp_match | label_match | composite |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for m in md["models"]:
        nick = m["nickname"]
        e = results["bench"].get(nick, {})
        if "error" in e:
            lines.append(f"| **{nick}** | 0 | — | — | — | — | err: {e['error'][:30]} |")
            continue
        n = e.get("n_samples", 0)
        if n == 0:
            lines.append(f"| **{nick}** | 0 | — | — | — | — | skipped |")
            continue
        lines.append(
            f"| **{nick}** | {n} | "
            f"{e.get('parse_ok_rate', 0):.2f} | "
            f"{e.get('cli_proxy_avg', 0):.2f} | "
            f"{e.get('comp_count_match_avg', 0):.2f} | "
            f"{e.get('label_count_match_avg', 0):.2f} | "
            f"{e.get('composite_score', 0):.3f} |"
        )
    lines += ["", "## Combos tested", ""]
    for m in md["models"]:
        lines.append(f"- **{m['nickname']}** — base `{m['base_hf_id']}` + adapter `{m['adapter_path']}`")
    OUT_MD.write_text("\n".join(lines) + "\n")
    log(f"Markdown saved to {OUT_MD}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> int:
    ap = argparse.ArgumentParser(description="KiCad Phase 2 LORA — sch generation bench")
    ap.add_argument("--models", nargs="*", default=None,
                    help="Subset de nicknames LoRA (voir LORA_COMBOS)")
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--dry-run", action="store_true",
                    help="Liste combos + samples + verifie adapters/imports sans charger")
    args = ap.parse_args()

    BENCH_DIR.mkdir(parents=True, exist_ok=True)

    samples = load_samples()
    n_total = len(samples)
    n_eval = sum(1 for s in samples if s["id"] != SPI_BUS_ID)

    if args.models:
        combos = [(n, b, a) for n, b, a in LORA_COMBOS if n in args.models]
        miss = sorted(set(args.models) - {n for n, _, _ in LORA_COMBOS})
        if miss:
            log(f"WARN: unknown LoRA combos: {miss}")
    else:
        combos = list(LORA_COMBOS)

    log("=" * 70)
    log("KICAD PHASE 2 LORA BENCH — sch generation (adapters)")
    log(f"  Combos    : {len(combos)} -> {[n for n, _, _ in combos]}")
    log(f"  Samples   : {n_eval}/{n_total} (skipped: {n_total - n_eval})")
    log(f"  MaxTokens : {args.max_tokens}")
    log(f"  Output    : {OUT_JSON}")
    log(f"  Output    : {OUT_MD}")
    log(f"  Log       : {LOG_PATH}")
    eta_min = len(combos) * n_eval * 60 / 60
    log(f"  ETA       : ~{eta_min:.0f} min (~60s/gen rough on M1 Max, adapter overhead negligeable)")
    log("=" * 70)

    if args.dry_run:
        log("DRY-RUN — combo / adapter checks:")
        for nick, base, adapter in combos:
            ap_path = Path(adapter)
            cfg = ap_path / "adapter_config.json"
            sft = ap_path / "adapters.safetensors"
            log(f"  {nick}:")
            log(f"    base       = {base}")
            log(f"    adapter    = {adapter}  exists={ap_path.exists()}")
            log(f"    config     = {cfg.name}  exists={cfg.exists()}")
            log(f"    safetensors= {sft.name}  exists={sft.exists()}")
        log(f"DRY-RUN — {n_eval} samples to evaluate (skipped: {SPI_BUS_ID}):")
        for s in samples:
            mark = "SKIP" if s["id"] == SPI_BUS_ID else "EVAL"
            log(f"  [{mark}] {s['id']} ({s['source']}): prompt[:80]={s['prompt'][:80]!r} "
                f"expected_chars={len(s['expected'])}")
        log("DRY-RUN — sanity scoring on expected:")
        for s in samples:
            if s["id"] == SPI_BUS_ID:
                continue
            try:
                sc = score_sch(s["expected"], s["expected"])
                log(f"  {s['id']}: composite={sc['composite']} parse_ok={sc['parse_ok']}")
            except Exception as exc:
                log(f"  {s['id']}: SCORE ERROR {exc!r}")
        try:
            import mlx_lm  # noqa: F401
            from mlx_lm import load as _load
            import inspect
            sig = inspect.signature(_load)
            has_adapter = "adapter_path" in sig.parameters
            log(f"  mlx_lm OK ; load supports adapter_path = {has_adapter}")
            if not has_adapter:
                log("  WARN: cette version de mlx_lm ne supporte pas adapter_path !")
                return 2
        except Exception as exc:
            log(f"  mlx_lm import FAILED: {exc!r}")
            return 2
        log("DRY-RUN done.")
        return 0

    results = {
        "metadata": {
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_path": str(Path(os.environ.get(
                "KICAD_SCH_GEN_PATH",
                HOME / "ailiance-data" / "kicad-sch-gen" / "valid.jsonl",
            ))),
            "n_samples_total": n_total,
            "n_samples_eval": n_eval,
            "max_tokens": args.max_tokens,
            "skipped_ids": [SPI_BUS_ID],
            "models": [
                {"nickname": n, "base_hf_id": b, "adapter_path": a}
                for n, b, a in combos
            ],
        },
        "bench": {},
    }
    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    for nick, base, adapter in combos:
        log(f"\n############ COMBO: {nick} (base={base}) ############")
        log(f"############ adapter: {adapter}")
        try:
            per = generate_for_lora_combo(nick, base, adapter, samples, args.max_tokens)
        except Exception as exc:
            log(f"  COMBO CRASHED: {exc!r}")
            log(traceback.format_exc())
            per = {"error": f"combo_crash: {exc!r}", "n_samples": 0}
        results["bench"][nick] = per
        OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        log(f"=== done {nick} (saved {OUT_JSON.name}) ===")

    write_markdown(results)
    log("KICAD PHASE 2 LORA BENCH COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
