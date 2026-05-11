#!/usr/bin/env python3
"""
Bench Phase 2 — generation .kicad_sch (KiCad 6/10 S-expression).

Le modele recoit une description textuelle de circuit et doit generer un
fichier .kicad_sch parsable.

Validation (sans kicad-cli, fallback parser pure-Python) :
  1. balanced_parens (binaire)
  2. starts_with_kicad_sch + has_version + has_lib_symbols + has_uuid
  3. composants extraits (>= 1) + labels extraits (>= 1)
  4. ratio composants generes / attendus (proxy structure)

Score composite :
  parse_ok  (0.40)  = balanced_parens
  cli_proxy (0.40)  = starts_with_kicad_sch + has_version + has_lib_symbols
                      + has_uuid (4 binaires moyennes)
  structure (0.20)  = ratio_match(n_components_gen, n_components_expected)
                      + ratio_match(n_labels_gen, n_labels_expected) / 2

Sortie :
  ~/bench-results/kicad_phase2.{json,md}
  Save incremental apres chaque (modele, sample).

Usage :
  python3 ~/scripts/bench_kicad_phase2.py                  # tous samples
  python3 ~/scripts/bench_kicad_phase2.py --models gemma-e2b
  python3 ~/scripts/bench_kicad_phase2.py --dry-run
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

sys.path.insert(0, str(Path(__file__).parent))
from kicad_sch_parser import parse_summary, balanced_parens  # noqa: E402

# --------------------------------------------------------------------------- #

HOME = Path.home()
DATA_PATH = Path(os.environ.get(
    "KICAD_SCH_GEN_PATH",
    HOME / "eu-kiki-data" / "kicad-sch-gen" / "valid.jsonl",
))
BENCH_DIR = Path(os.environ.get("BENCH_RESULTS_DIR", HOME / "bench-results"))
LOG_DIR = HOME / "logs"

OUT_JSON = BENCH_DIR / "kicad_phase2.json"
OUT_MD = BENCH_DIR / "kicad_phase2.md"

# Skip granite-30b par defaut (RAM + temps de gen)
SKIP_HEAVY = os.environ.get("KICAD_SKIP_HEAVY", "1") == "1"
HEAVY_NICKS = {"granite-4.1-30b"}

MODELS: list[tuple[str, str]] = [
    ("gemma-e4b-eu-kiki-base",   "lmstudio-community/gemma-4-E4B-it-MLX-4bit"),
    ("gemma-e2b",                "lmstudio-community/gemma-4-E2B-it-MLX-4bit"),
    ("ministral-3b",             "mlx-community/Ministral-3-3B-Instruct-2512-4bit"),
    ("ministral-3-8b",           "mlx-community/Ministral-3-8B-Instruct-2512-4bit"),
    ("ministral-3-14b-instruct", "mlx-community/Ministral-3-14B-Instruct-2512-4bit"),
    ("ministral-3-14b-reasoning","mlx-community/Ministral-3-14B-Reasoning-2512-4bit"),
    ("granite-4.1-3b",           "mlx-community/granite-4.1-3b-4bit"),
    ("granite-4.1-30b",          "mlx-community/granite-4.1-30b-4bit"),
]

# .kicad_sch peuvent etre longs : 1500 tokens couvre led/vdiv/555/opamp ;
# 4096 pour esp32 ; spi_bus est trop gros (~43k chars) -> on l'exclut de la
# generation (sera marquee skipped) mais reste dans Phase 3.
DEFAULT_MAX_TOKENS = 4096
SPI_BUS_ID = "spi_bus_4devices"  # skip in Phase 2 (too long to generate)

# --------------------------------------------------------------------------- #

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / f"bench_kicad_phase2-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
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
# Dataset
# --------------------------------------------------------------------------- #


def load_samples() -> list[dict]:
    rows = []
    if not DATA_PATH.exists():
        raise FileNotFoundError(DATA_PATH)
    with DATA_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            msgs = d.get("messages", [])
            user = next((m["content"] for m in msgs if m.get("role") == "user"), None)
            asst = next((m["content"] for m in msgs if m.get("role") == "assistant"), None)
            if user is None or asst is None:
                continue
            rows.append({
                "id": d.get("_id", ""),
                "source": d.get("_source", ""),
                "prompt": user,
                "expected": asst,
            })
    return rows


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


def _strip_md_fence(text: str) -> str:
    import re
    m = re.search(r"```(?:lisp|scheme|kicad|sexp|sch|kicad_sch)?\s*\n(.*?)```", text, re.S | re.I)
    return m.group(1) if m else text


def _ratio_match(gen: int, exp: int) -> float:
    denom = max(exp, 1)
    diff = abs(gen - exp)
    return max(0.0, min(1.0, 1.0 - diff / denom))


def score_sch(generated: str, expected: str) -> dict[str, Any]:
    src = _strip_md_fence(generated)
    g = parse_summary(src)
    e = parse_summary(expected)

    parse_ok = bool(g["balanced_parens"])
    cli_proxy = (
        (1.0 if g["starts_with_kicad_sch"] else 0.0)
        + (1.0 if g["has_version"] else 0.0)
        + (1.0 if g["has_lib_symbols"] else 0.0)
        + (1.0 if g["has_uuid"] else 0.0)
    ) / 4.0
    comp_match = _ratio_match(g["n_components"], e["n_components"])
    label_match = _ratio_match(g["n_labels"], e["n_labels"])
    structure = (comp_match + label_match) / 2.0

    composite = (
        (1.0 if parse_ok else 0.0) * 0.40
        + cli_proxy * 0.40
        + structure * 0.20
    )

    return {
        "parse_ok": parse_ok,
        "starts_with_kicad_sch": g["starts_with_kicad_sch"],
        "has_version": g["has_version"],
        "has_lib_symbols": g["has_lib_symbols"],
        "has_uuid": g["has_uuid"],
        "expected_n_components": e["n_components"],
        "generated_n_components": g["n_components"],
        "comp_count_match": round(comp_match, 4),
        "expected_n_labels": e["n_labels"],
        "generated_n_labels": g["n_labels"],
        "label_count_match": round(label_match, 4),
        "cli_proxy_score": round(cli_proxy, 4),
        "structure_score": round(structure, 4),
        "composite": round(composite, 4),
    }


def aggregate(records: list[dict]) -> dict:
    n = len(records)
    if n == 0:
        return {"n_samples": 0}
    sc = [r["scores"] for r in records]
    return {
        "n_samples": n,
        "parse_ok_rate": round(sum(1 for s in sc if s["parse_ok"]) / n, 4),
        "starts_with_kicad_sch_rate": round(sum(1 for s in sc if s["starts_with_kicad_sch"]) / n, 4),
        "has_lib_symbols_rate": round(sum(1 for s in sc if s["has_lib_symbols"]) / n, 4),
        "comp_count_match_avg": round(sum(s["comp_count_match"] for s in sc) / n, 4),
        "label_count_match_avg": round(sum(s["label_count_match"] for s in sc) / n, 4),
        "cli_proxy_avg": round(sum(s["cli_proxy_score"] for s in sc) / n, 4),
        "composite_score": round(sum(s["composite"] for s in sc) / n, 4),
    }


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #


def _format_prompt(tokenizer, user_msg: str) -> str:
    try:
        return tokenizer.apply_chat_template(
            [{"role": "user", "content": user_msg}],
            tokenize=False,
            add_generation_prompt=True,
        )
    except Exception:
        return user_msg


def generate_for_model(nick: str, hf_id: str, samples: list[dict],
                       max_tokens: int) -> dict:
    log(f"  loading {nick} ({hf_id}) ...")
    t0 = time.time()
    from mlx_lm import load as mlx_load
    from mlx_lm import generate as mlx_generate
    try:
        model, tokenizer = mlx_load(hf_id)
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
        scores = score_sch(generated, sample["expected"])
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
        log(f"     [{i+1}/{len(samples)}] {sid} composite={scores['composite']} "
            f"parse_ok={scores['parse_ok']} t={dt_g:.1f}s")

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
        "# KiCad Phase 2 bench — generation .kicad_sch (KiCad 10 S-expr)",
        "",
        f"_Generated: {md['timestamp']}_",
        "",
        f"- Dataset    : `{md['data_path']}` ({md['n_samples_total']} samples, "
        f"{md['n_samples_eval']} evaluated)",
        f"- Models     : {len(md['models'])}",
        f"- Max tokens : {md['max_tokens']}",
        f"- Validation : pure-Python parser (kicad-cli not installed)",
        "",
        "| Model | n | parse_ok | cli_proxy | comp_match | label_match | composite |",
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
    lines += ["", "## Models tested", ""]
    for m in md["models"]:
        lines.append(f"- **{m['nickname']}** — `{m['hf_id']}`")
    OUT_MD.write_text("\n".join(lines) + "\n")
    log(f"Markdown saved to {OUT_MD}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> int:
    ap = argparse.ArgumentParser(description="KiCad Phase 2 — sch generation bench")
    ap.add_argument("--models", nargs="*", default=None)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--include-heavy", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    BENCH_DIR.mkdir(parents=True, exist_ok=True)

    samples = load_samples()
    n_total = len(samples)
    n_eval = sum(1 for s in samples if s["id"] != SPI_BUS_ID)

    if args.models:
        models = [(n, h) for n, h in MODELS if n in args.models]
        miss = sorted(set(args.models) - {n for n, _ in MODELS})
        if miss:
            log(f"WARN: unknown models: {miss}")
    else:
        models = list(MODELS)
        if SKIP_HEAVY and not args.include_heavy:
            before = len(models)
            models = [(n, h) for n, h in models if n not in HEAVY_NICKS]
            if len(models) < before:
                log(f"WARN: skipping heavy {sorted(HEAVY_NICKS)} "
                    f"(KICAD_SKIP_HEAVY=1; --include-heavy to force)")

    log("=" * 70)
    log("KICAD PHASE 2 BENCH — sch generation")
    log(f"  Models    : {len(models)} -> {[n for n, _ in models]}")
    log(f"  Samples   : {n_eval}/{n_total} (skipped: {n_total - n_eval})")
    log(f"  MaxTokens : {args.max_tokens}")
    log(f"  Output    : {OUT_JSON}")
    log(f"  Output    : {OUT_MD}")
    log(f"  Log       : {LOG_PATH}")
    eta_min = len(models) * n_eval * 60 / 60  # ~60s per gen rough on M1 Max
    log(f"  ETA       : ~{eta_min:.0f} min")
    log("=" * 70)

    if args.dry_run:
        log("DRY-RUN — sample shapes:")
        for s in samples:
            log(f"  {s['id']} ({s['source']}): prompt[:80]={s['prompt'][:80]!r} "
                f"expected_chars={len(s['expected'])}")
        log("DRY-RUN — running scorer on expected (sanity):")
        for s in samples:
            sc = score_sch(s["expected"], s["expected"])
            log(f"  {s['id']}: composite={sc['composite']} parse_ok={sc['parse_ok']}")
        try:
            import mlx_lm  # noqa: F401
            log("  mlx_lm import OK")
        except Exception as exc:
            log(f"  mlx_lm import FAILED: {exc!r}")
        log("DRY-RUN done.")
        return 0

    results = {
        "metadata": {
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_path": str(DATA_PATH),
            "n_samples_total": n_total,
            "n_samples_eval": n_eval,
            "max_tokens": args.max_tokens,
            "skipped_ids": [SPI_BUS_ID],
            "models": [{"nickname": n, "hf_id": h} for n, h in models],
        },
        "bench": {},
    }
    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    for nick, hf_id in models:
        log(f"\n############ MODEL: {nick} ({hf_id}) ############")
        try:
            per = generate_for_model(nick, hf_id, samples, args.max_tokens)
        except Exception as exc:
            log(f"  MODEL CRASHED: {exc!r}")
            log(traceback.format_exc())
            per = {"error": f"model_crash: {exc!r}", "n_samples": 0}
        results["bench"][nick] = per
        OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        log(f"=== done {nick} (saved {OUT_JSON.name}) ===")

    write_markdown(results)
    log("KICAD PHASE 2 BENCH COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
