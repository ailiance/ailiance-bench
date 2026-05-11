#!/usr/bin/env python3
"""
Bench Phase 6 reco #26 — completion PUR (no chat template) sur ministral-14b /
granite-30b.

On donne le prefix header en raw text + une instruction minimale (single
"Completion:" tag), pas de chat-template, pas de role tags. mlx_lm.generate
accepte un prompt str ; pour rester pur completion on ne passe PAS par
apply_chat_template.

Modeles testes (2 seulement) :
  - ministral-3-14b-instruct
  - granite-4.1-30b  (peut OOM ; KICAD_SKIP_HEAVY pour skip)

5 prompts (dataset valid.jsonl moins spi_bus_4devices).

Sortie : ~/bench-results/kicad_phase6_completion_pure.{json,md}
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
import uuid as uuidlib
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from bench_kicad_phase4 import (  # noqa: E402
    composite_score,
    aggregate as aggregate_p4,
    detect_kicad_version,
    run_erc,
    KICAD_CLI,
    _strip_md_fence,
)
from bench_kicad_phase2 import (  # noqa: E402
    load_samples,
    SPI_BUS_ID,
)
from bench_kicad_phase6_completion import (  # noqa: E402
    build_prefix,
    KICAD_VERSION_TS,
)

# --------------------------------------------------------------------------- #

HOME = Path.home()
BENCH_DIR = Path(os.environ.get("BENCH_RESULTS_DIR", HOME / "bench-results"))
LOG_DIR = HOME / "logs"

OUT_JSON = BENCH_DIR / "kicad_phase6_completion_pure.json"
OUT_MD = BENCH_DIR / "kicad_phase6_completion_pure.md"

DEFAULT_MAX_TOKENS = 4096
SKIP_HEAVY = os.environ.get("KICAD_SKIP_HEAVY", "1") == "1"
HEAVY_NICKS = {"granite-4.1-30b"}

MODELS: list[tuple[str, str]] = [
    ("ministral-3-14b-instruct", "mlx-community/Ministral-3-14B-Instruct-2512-4bit"),
    ("granite-4.1-30b",          "mlx-community/granite-4.1-30b-4bit"),
]

# --------------------------------------------------------------------------- #

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / f"bench_kicad_phase6_completion_pure-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
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
# Generation pure-completion (no chat template, raw prefix as prompt)
# --------------------------------------------------------------------------- #


def generate_pure(model, tokenizer, prompt: str, max_tokens: int) -> str:
    """Generation completion pure, sans apply_chat_template."""
    from mlx_lm import generate as mlx_generate
    # mlx_lm.generate accepte un str -> tokenize en interne sans BOS chat tags
    return mlx_generate(
        model, tokenizer,
        prompt=prompt,
        max_tokens=max_tokens,
        verbose=False,
    )


def generate_for_model(nick: str, hf_id: str,
                       samples: list[dict], max_tokens: int) -> dict:
    log(f"  loading {nick} ({hf_id}) — pure completion mode")
    t0 = time.time()
    from mlx_lm import load as mlx_load
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
            log(f"     [{i+1}/{len(samples)}] skipping {sid}")
            continue
        # PURE completion : prompt = raw prefix (le modele continue le texte)
        prefix = build_prefix(sid)
        t_g = time.time()
        try:
            completion = generate_pure(model, tokenizer, prefix, max_tokens)
        except Exception as exc:
            log(f"     [{i+1}/{len(samples)}] GEN ERROR ({sid}): {exc!r}")
            completion = ""
        dt_g = time.time() - t_g

        # Concatenate prefix + generated tail
        completion_clean = _strip_md_fence(completion)
        full_sch = prefix + completion_clean

        erc = run_erc(full_sch, nick, sid)
        scores = composite_score(erc)

        records.append({
            "id": sid,
            "source": sample.get("source", ""),
            "prefix_chars": len(prefix),
            "completion_chars": len(completion),
            "full_sch_chars": len(full_sch),
            "completion_preview": completion[:1500],
            "erc": {
                "parse_ok": erc["parse_ok"],
                "parse_via": erc["parse_via"],
                "errors_count": erc["errors_count"],
                "warnings_count": erc["warnings_count"],
                "violations_by_type": erc["violations_by_type"],
                "rc": erc["rc"],
                "stderr": (erc.get("stderr") or "")[:200],
            },
            "scores": scores,
            "gen_time_s": round(dt_g, 2),
        })
        log(f"     [{i+1}/{len(samples)}] {sid} via={erc['parse_via']} "
            f"errs={erc['errors_count']} warns={erc['warnings_count']} "
            f"composite={scores['composite']} t={dt_g:.1f}s")

    agg = aggregate_p4(records)
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
        "# KiCad Phase 6 reco #26 — completion PURE (no chat template)",
        "",
        f"_Generated: {md['timestamp']}_",
        "",
        f"- KiCad CLI    : `{md['kicad_cli']}` (v{md.get('kicad_version','?')})",
        f"- Models       : {len(md['models'])}",
        f"- Max tokens   : {md['max_tokens']}",
        f"- Score weights: parse_ok 0.30 + erc_no_errors 0.40 + erc_low_warnings 0.30",
        "",
        "| Model | n | parse_ok_cli | avg_err | avg_warn | composite |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for m in md["models"]:
        nick = m["nickname"]
        e = results["bench"].get(nick, {})
        if "error" in e:
            lines.append(f"| **{nick}** | 0 | — | — | — | err: {e['error'][:40]} |")
            continue
        n = e.get("n_samples", 0)
        if n == 0:
            lines.append(f"| **{nick}** | 0 | — | — | — | skipped |")
            continue
        avg_e = e.get("avg_errors")
        avg_w = e.get("avg_warnings")
        lines.append(
            f"| **{nick}** | {n} | "
            f"{e.get('parse_ok_kicad_rate', 0):.2f} | "
            f"{(avg_e if avg_e is not None else 0):.2f} | "
            f"{(avg_w if avg_w is not None else 0):.2f} | "
            f"{e.get('composite_avg', 0):.3f} |"
        )
    lines += ["", "## Models tested", ""]
    for m in md["models"]:
        lines.append(f"- **{m['nickname']}** — `{m['hf_id']}` (PURE completion)")
    OUT_MD.write_text("\n".join(lines) + "\n")
    log(f"Markdown saved to {OUT_MD}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> int:
    ap = argparse.ArgumentParser(description="KiCad Phase 6 — completion PURE")
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
    log("KICAD PHASE 6 reco #26 — completion PURE bench")
    log(f"  Models    : {len(models)} -> {[n for n, _ in models]}")
    log(f"  Samples   : {n_eval}/{n_total} (skipped: {SPI_BUS_ID})")
    log(f"  MaxTokens : {args.max_tokens}")
    log(f"  KICAD_CLI : {KICAD_CLI}")
    log(f"  Output    : {OUT_JSON}")
    log(f"  Output    : {OUT_MD}")
    log(f"  Log       : {LOG_PATH}")
    log("=" * 70)

    if args.dry_run:
        log("DRY-RUN — listing models / samples / prefix shape")
        for nick, hf in models:
            log(f"  {nick}: hf={hf}")
        log(f"DRY-RUN — {n_eval} samples to eval :")
        for s in samples:
            mark = "SKIP" if s["id"] == SPI_BUS_ID else "EVAL"
            log(f"  [{mark}] {s['id']}")
        sample_for_demo = next((s for s in samples if s["id"] != SPI_BUS_ID), None)
        if sample_for_demo:
            pfx = build_prefix(sample_for_demo["id"])
            log(f"DRY-RUN — pure prompt = raw prefix, size = {len(pfx)} chars")
            log(f"DRY-RUN — first prefix lines:\n{pfx}")
        try:
            import mlx_lm  # noqa: F401
            log("  mlx_lm import OK (PURE mode bypasses chat template)")
        except Exception as exc:
            log(f"  mlx_lm import FAILED: {exc!r}")
        log("DRY-RUN done.")
        return 0

    results = {
        "metadata": {
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "kicad_cli": KICAD_CLI,
            "kicad_version": detect_kicad_version(),
            "max_tokens": args.max_tokens,
            "n_samples_total": n_total,
            "n_samples_eval": n_eval,
            "skipped_ids": [SPI_BUS_ID],
            "score_weights": {"parse_ok": 0.30, "erc_no_errors": 0.40,
                              "erc_low_warnings": 0.30},
            "kicad_version_in_prefix": KICAD_VERSION_TS,
            "mode": "pure_completion_no_chat_template",
            "models": [{"nickname": n, "hf_id": h} for n, h in models],
        },
        "bench": {},
    }
    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    for nick, hf in models:
        log(f"\n############ MODEL: {nick} ############")
        try:
            per = generate_for_model(nick, hf, samples, args.max_tokens)
        except Exception as exc:
            log(f"  MODEL CRASHED: {exc!r}")
            log(traceback.format_exc())
            per = {"error": f"model_crash: {exc!r}", "n_samples": 0}
        results["bench"][nick] = per
        OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        log(f"=== done {nick} (saved {OUT_JSON.name}) ===")

    write_markdown(results)
    log("KICAD PHASE 6 reco #26 BENCH COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
