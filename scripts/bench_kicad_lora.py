#!/usr/bin/env python3
"""
Bench fonctionnel KiCad + SPICE — variante LoRA / adapters (Phase 1 LoRA).

Reutilise integralement les parsers / scoring / generation pipeline de
``bench_kicad_functional.py`` (DRY) — on importe les fonctions et on
applique :

  - une nouvelle liste ``MODELS_LORA``  : tuples (base_hf_id, adapter_path, nick)
  - un loader patche : ``mlx_lm.load(base_id, adapter_path=adapter_path)``
    (l'API MLX-LM le supporte nativement et applique les couches LoRA en place)

Sortie distincte :
  ~/bench-results/kicad_functional_phase1_lora.json
  ~/bench-results/kicad_functional_phase1_lora.md

Usage :
  python3 ~/scripts/bench_kicad_lora.py                       # tous adapters x 3 datasets x 20 samples
  python3 ~/scripts/bench_kicad_lora.py --models gemma-e4b-eukiki
  python3 ~/scripts/bench_kicad_lora.py --datasets kicad-pcb
  python3 ~/scripts/bench_kicad_lora.py --n-samples 1 --models gemma-e4b-eukiki --datasets kicad-pcb   # sanity 1 sample
  python3 ~/scripts/bench_kicad_lora.py --dry-run

Env :
  EUKIKI_DATA_DIR   : default ~/eu-kiki-data/hf-traced
  BENCH_RESULTS_DIR : default ~/bench-results
  KICAD_MAX_TOKENS  : override max tokens (per-dataset autrement)
"""

from __future__ import annotations

import argparse
import datetime as dt
import gc
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any

# --- Reuse parsers / scoring / loaders / aggregation from base bench ---
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from bench_kicad_functional import (  # noqa: E402
    DATA_DIR,
    BENCH_DIR,
    DATASETS,
    GEN_PARAMS,
    SCORERS,
    aggregate,
    load_samples,
    log,
    _format_prompt,
)

DEFAULT_N_SAMPLES = 20

# Sortie distincte : on NE TOUCHE PAS aux fichiers de la Phase 1 base.
OUT_JSON = BENCH_DIR / "kicad_functional_phase1_lora.json"
OUT_MD = BENCH_DIR / "kicad_functional_phase1_lora.md"

# --------------------------------------------------------------------------- #
# Liste des combinaisons base + adapter a bencher.
#
# Critere de selection :
#   - base doit etre present dans la liste ``MODELS`` de bench_kicad_functional.py
#     (sinon on benche un base inconnu et la comparaison base vs lora est cassee)
#   - adapter local trouve dans ~/lora-adapters/<name>/(final|phase4_full)/
#
# Inventory au 2026-05-11 : 3 adapters locaux ciblent
# lmstudio-community/gemma-4-E4B-it-MLX-4bit (alias 'gemma-e4b-eu-kiki-base'
# dans le bench base).
# --------------------------------------------------------------------------- #

GEMMA_E4B_BASE = "lmstudio-community/gemma-4-E4B-it-MLX-4bit"
HOME = Path.home()

MODELS_LORA: list[tuple[str, str, str]] = [
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
# Per-model generation : meme logique que bench_kicad_functional.generate_for_model
# mais avec adapter_path.
# --------------------------------------------------------------------------- #


def generate_for_lora_combo(
    nick: str,
    base_hf_id: str,
    adapter_path: str,
    datasets: list[str],
    n_samples: int,
    max_tokens_override: int | None,
) -> dict[str, dict[str, Any]]:
    """Charge base + adapter UNE FOIS, genere n_samples par dataset, score."""
    log(f"  loading base {base_hf_id} + adapter {adapter_path} ...")
    t0 = time.time()
    from mlx_lm import load as mlx_load
    from mlx_lm import generate as mlx_generate

    if not Path(adapter_path).exists():
        msg = f"adapter_path missing: {adapter_path}"
        log(f"  LOAD SKIP for {nick}: {msg}")
        return {ds: {"error": msg, "n_samples": 0} for ds in datasets}

    try:
        model, tokenizer = mlx_load(base_hf_id, adapter_path=adapter_path)
    except Exception as exc:
        log(f"  LOAD FAILED for {nick}: {exc!r}")
        return {ds: {"error": f"load_failed: {exc!r}", "n_samples": 0} for ds in datasets}
    log(f"  loaded in {time.time()-t0:.1f}s")

    out: dict[str, dict[str, Any]] = {}
    for ds in datasets:
        log(f"  -> generating {n_samples} samples on {ds}")
        max_tokens = max_tokens_override or GEN_PARAMS[ds]["max_tokens"]
        try:
            samples = load_samples(ds, n_samples)
        except FileNotFoundError as exc:
            log(f"  dataset missing: {exc}")
            out[ds] = {"error": f"dataset_missing: {exc}", "n_samples": 0}
            continue

        records: list[dict[str, Any]] = []
        for i, sample in enumerate(samples):
            prompt_text = _format_prompt(tokenizer, sample["prompt"])
            t_gen = time.time()
            try:
                generated = mlx_generate(
                    model,
                    tokenizer,
                    prompt=prompt_text,
                    max_tokens=max_tokens,
                    verbose=False,
                )
            except Exception as exc:
                log(f"     [{i+1}/{n_samples}] GEN ERROR: {exc!r}")
                generated = ""
            dt_gen = time.time() - t_gen

            scores = SCORERS[ds](generated, sample["expected"])
            records.append({
                "prompt": sample["prompt"][:300],
                "expected": sample["expected"][:600],
                "generated": generated[:2000],
                "scores": scores,
                "gen_time_s": round(dt_gen, 2),
            })
            if (i + 1) % 5 == 0 or i == n_samples - 1:
                log(f"     [{i+1}/{n_samples}] composite={scores.get('composite')} "
                    f"parse_ok={scores.get('parse_ok')} t={dt_gen:.1f}s")
        agg = aggregate(records, ds)
        agg["samples"] = records
        out[ds] = agg
        log(f"  {ds} done: composite={agg.get('composite_score')} "
            f"parse_ok_rate={agg.get('parse_ok_rate')}")

    # Free memory before next combo
    del model
    del tokenizer
    gc.collect()
    try:
        import mlx.core as mx  # type: ignore
        mx.metal.clear_cache()
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #


def write_markdown(results: dict) -> None:
    lines: list[str] = []
    lines.append("# KiCad + SPICE functional bench — Phase 1 LORA (adapters)")
    lines.append("")
    md = results["metadata"]
    lines.append(f"_Generated: {md['timestamp']}_")
    lines.append("")
    lines.append(f"- Datasets : {md['datasets']}")
    lines.append(f"- Samples / dataset : **{md['n_samples']}**")
    lines.append(f"- Combos base+adapter : {len(md['models'])}")
    lines.append("")
    lines.append("## Combos tested")
    lines.append("")
    for m in md["models"]:
        lines.append(f"- **{m['nickname']}** — base `{m['base_hf_id']}` + adapter `{m['adapter_path']}`")
    lines.append("")
    for ds in md["datasets"]:
        lines.append(f"## Dataset: `{ds}`")
        lines.append("")
        lines.append("| Combo | n | parse_ok | composite | extras |")
        lines.append("|---|---:|---:|---:|---|")
        for m in md["models"]:
            nick = m["nickname"]
            entry = results["bench"].get(nick, {}).get(ds, {})
            if "error" in entry:
                lines.append(f"| **{nick}** | 0 | — | — | {entry['error']} |")
                continue
            n = entry.get("n_samples", 0)
            if n == 0:
                lines.append(f"| **{nick}** | 0 | — | — | skipped |")
                continue
            extras_keys = [k for k in entry if k.endswith("_rate") and k != "parse_ok_rate"]
            extras = ", ".join(f"{k}={entry[k]}" for k in extras_keys)
            lines.append(
                f"| **{nick}** | {n} | {entry.get('parse_ok_rate', 0):.2f} | "
                f"{entry.get('composite_score', 0):.3f} | {extras} |"
            )
        lines.append("")
    OUT_MD.write_text("\n".join(lines))
    log(f"Markdown saved to {OUT_MD}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> int:
    ap = argparse.ArgumentParser(description="KiCad functional bench Phase 1 — LORA")
    ap.add_argument("--models", nargs="*", default=None,
                    help="Subset de nicknames LoRA (voir MODELS_LORA)")
    ap.add_argument("--datasets", nargs="*", default=None,
                    help=f"Subset parmi {DATASETS}")
    ap.add_argument("--n-samples", type=int, default=DEFAULT_N_SAMPLES,
                    help=f"Samples par dataset (default {DEFAULT_N_SAMPLES})")
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="Override max_tokens (default per-dataset)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Liste combos + datasets + verifie adapters/imports sans charger ni generer")
    args = ap.parse_args()

    BENCH_DIR.mkdir(parents=True, exist_ok=True)

    # Resolve datasets
    if args.datasets:
        datasets = [d for d in args.datasets if d in DATASETS]
        missing = sorted(set(args.datasets) - set(DATASETS))
        if missing:
            log(f"WARN: datasets ignores (inconnus): {missing}")
    else:
        datasets = list(DATASETS)

    # Resolve models
    if args.models:
        combos = [(n, b, a) for n, b, a in MODELS_LORA if n in args.models]
        missing = sorted(set(args.models) - {n for n, _, _ in MODELS_LORA})
        if missing:
            log(f"WARN: combos ignores (inconnus): {missing}")
    else:
        combos = list(MODELS_LORA)

    log("=" * 70)
    log("KICAD + SPICE FUNCTIONAL BENCH — PHASE 1 LORA")
    log(f"  Combos   : {len(combos)} -> {[n for n, _, _ in combos]}")
    log(f"  Datasets : {datasets}")
    log(f"  Samples  : {args.n_samples} per dataset")
    log(f"  Output   : {OUT_JSON}")
    log(f"  Output   : {OUT_MD}")
    eta_min = len(combos) * len(datasets) * args.n_samples * 30 / 60
    log(f"  ETA      : ~{eta_min:.0f} min (~30s/gen rough, adapter overhead negligeable)")
    log("=" * 70)

    if args.dry_run:
        log("DRY-RUN — combo / adapter checks:")
        for nick, base, adapter in combos:
            ap_path = Path(adapter)
            cfg = ap_path / "adapter_config.json"
            sft = ap_path / "adapters.safetensors"
            ap_ok = ap_path.exists()
            cfg_ok = cfg.exists()
            sft_ok = sft.exists()
            log(f"  {nick}:")
            log(f"    base       = {base}")
            log(f"    adapter    = {adapter}  exists={ap_ok}")
            log(f"    config     = {cfg.name}  exists={cfg_ok}")
            log(f"    safetensors= {sft.name}  exists={sft_ok}")
        log("DRY-RUN — datasets sample shape:")
        for ds in datasets:
            try:
                rows = load_samples(ds, 1)
                log(f"  {ds}: prompt[:80]={rows[0]['prompt'][:80]!r}")
                log(f"  {ds}: expected_chars={len(rows[0]['expected'])}")
            except Exception as exc:
                log(f"  {ds}: ERROR {exc!r}")
        log("DRY-RUN: imports test...")
        try:
            import mlx_lm  # noqa: F401
            from mlx_lm import load as _load, generate as _gen  # noqa: F401
            import inspect
            sig = inspect.signature(_load)
            has_adapter = "adapter_path" in sig.parameters
            log(f"  mlx_lm imports OK ; load supports adapter_path = {has_adapter}")
            if not has_adapter:
                log("  WARN: cette version de mlx_lm ne supporte pas adapter_path !")
        except Exception as exc:
            log(f"  mlx_lm import FAILED: {exc!r}")
            return 2
        log("DRY-RUN done.")
        return 0

    results: dict[str, Any] = {
        "metadata": {
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_dir": str(DATA_DIR),
            "n_samples": args.n_samples,
            "max_tokens_override": args.max_tokens,
            "gen_params": GEN_PARAMS,
            "models": [
                {"nickname": n, "base_hf_id": b, "adapter_path": a}
                for n, b, a in combos
            ],
            "datasets": datasets,
        },
        "bench": {},
    }
    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    for nick, base, adapter in combos:
        log(f"\n############ COMBO: {nick} (base={base}) ############")
        log(f"############ adapter: {adapter}")
        try:
            per_ds = generate_for_lora_combo(
                nick, base, adapter, datasets, args.n_samples, args.max_tokens
            )
        except Exception as exc:
            log(f"  COMBO CRASHED: {exc!r}")
            log(traceback.format_exc())
            per_ds = {ds: {"error": f"combo_crash: {exc!r}", "n_samples": 0}
                      for ds in datasets}

        results["bench"][nick] = per_ds
        # incremental save
        OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        log(f"=== done {nick} (saved {OUT_JSON.name}) ===")

    write_markdown(results)
    log("KICAD FUNCTIONAL BENCH PHASE 1 LORA COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
