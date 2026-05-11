#!/usr/bin/env python3
"""
Bench Phase 6 reco #24 — task completion avec prefix header canonique.

Strategie : on injecte un PREFIX_TEMPLATE (kicad_sch + version + uuid + paper +
title_block + lib_symbols ouvert) dans le prompt user. Le modele doit completer
avec lib_symbols entries + symbols + wires + labels + parens fermantes.

Concatenation avant scoring : prefix + generated -> scoring complet.

Bench tous les 10 modeles (7 base + 3 LoRA, modulo SKIP_HEAVY pour granite-30b).
5 prompts (dataset valid.jsonl moins spi_bus_4devices).

Sortie :
  ~/bench-results/kicad_phase6_completion.{json,md}

Usage :
  python3 ~/scripts/bench_kicad_phase6_completion.py
  python3 ~/scripts/bench_kicad_phase6_completion.py --dry-run
  python3 ~/scripts/bench_kicad_phase6_completion.py --models gemma-e4b-eu-kiki-base
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

# Reuse loader + scorer Phase 4 (ERC kicad-cli + fallback)
from bench_kicad_phase4 import (  # noqa: E402
    composite_score,
    aggregate as aggregate_p4,
    detect_kicad_version,
    run_erc,
    KICAD_CLI,
    ERC_TIMEOUT_S,
    _strip_md_fence,
)
# Reuse dataset loader
from bench_kicad_phase2 import (  # noqa: E402
    load_samples,
    SPI_BUS_ID,
)

# --------------------------------------------------------------------------- #

HOME = Path.home()
BENCH_DIR = Path(os.environ.get("BENCH_RESULTS_DIR", HOME / "bench-results"))
LOG_DIR = HOME / "logs"

OUT_JSON = BENCH_DIR / "kicad_phase6_completion.json"
OUT_MD = BENCH_DIR / "kicad_phase6_completion.md"

DEFAULT_MAX_TOKENS = 4096
SKIP_HEAVY = os.environ.get("KICAD_SKIP_HEAVY", "1") == "1"
HEAVY_NICKS = {"granite-4.1-30b"}

GEMMA_E4B_BASE = "lmstudio-community/gemma-4-E4B-it-MLX-4bit"

# (nick, hf_id, adapter_path_or_None)
MODELS: list[tuple[str, str, str | None]] = [
    # 7 base
    ("gemma-e4b-eu-kiki-base",   "lmstudio-community/gemma-4-E4B-it-MLX-4bit", None),
    ("gemma-e2b",                "lmstudio-community/gemma-4-E2B-it-MLX-4bit", None),
    ("ministral-3b",             "mlx-community/Ministral-3-3B-Instruct-2512-4bit", None),
    ("ministral-3-8b",           "mlx-community/Ministral-3-8B-Instruct-2512-4bit", None),
    ("ministral-3-14b-instruct", "mlx-community/Ministral-3-14B-Instruct-2512-4bit", None),
    ("ministral-3-14b-reasoning","mlx-community/Ministral-3-14B-Reasoning-2512-4bit", None),
    ("granite-4.1-3b",           "mlx-community/granite-4.1-3b-4bit", None),
    ("granite-4.1-30b",          "mlx-community/granite-4.1-30b-4bit", None),
    # 3 LoRA gemma-e4b
    ("gemma-e4b-eukiki-final",   GEMMA_E4B_BASE,
        str(HOME / "lora-adapters" / "gemma4-e4b-eukiki" / "final")),
    ("gemma-e4b-mascarade-final", GEMMA_E4B_BASE,
        str(HOME / "lora-adapters" / "gemma4-e4b-mascarade" / "final")),
    ("gemma-e4b-aggro-test",     GEMMA_E4B_BASE,
        str(HOME / "lora-adapters" / "aggro-test")),
    ("gemma-e4b-kicad9plus-final", GEMMA_E4B_BASE,
        str(HOME / "lora-adapters" / "gemma4-e4b-kicad9plus" / "final")),
]

# Reference KICAD_VERSION matches local kicad-cli (10.0.2 -> KiCad 10
# bumped to 20260306 for KiCad 10 mainline, fallback to refs ts).
# On reuse "20250114" pour rester compatible avec kicad-cli installe (KiCad 10
# accepte aussi version 9 schemas) ; verif via head -2 du ref.
KICAD_VERSION_TS = "20250114"

PREFIX_TEMPLATE = """(kicad_sch
\t(version {ver})
\t(generator "kicad-bench")
\t(generator_version "1.0")
\t(uuid "{uuid}")
\t(paper "A4")
\t(title_block
\t\t(title "{title}")
\t\t(date "2026-05-11")
\t)
\t(lib_symbols
"""

USER_INSTRUCTION = """You are completing a KiCad 10 schematic file. The header is written. \
Continue by adding lib_symbols entries, symbol instances, wires, labels, and the \
closing parens. Output only completion code (no markdown, no explanation).

Existing prefix:
{prefix}

Continue:"""

# --------------------------------------------------------------------------- #

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / f"bench_kicad_phase6_completion-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
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
# Prompt builder
# --------------------------------------------------------------------------- #


def build_prefix(sample_id: str) -> str:
    # uuid deterministe par sample_id pour reproductibilite
    u = uuidlib.uuid5(uuidlib.NAMESPACE_DNS, f"phase6-{sample_id}")
    title = sample_id.replace("_", " ").title()
    return PREFIX_TEMPLATE.format(ver=KICAD_VERSION_TS, uuid=str(u), title=title)


def build_user_msg(prefix: str) -> str:
    return USER_INSTRUCTION.format(prefix=prefix)


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #


def _format_chat_prompt(tokenizer, user_msg: str) -> str:
    try:
        return tokenizer.apply_chat_template(
            [{"role": "user", "content": user_msg}],
            tokenize=False,
            add_generation_prompt=True,
        )
    except Exception:
        return user_msg


def generate_for_model(nick: str, hf_id: str, adapter_path: str | None,
                       samples: list[dict], max_tokens: int) -> dict:
    log(f"  loading {nick} hf_id={hf_id} adapter={adapter_path or '(none)'}")
    t0 = time.time()
    from mlx_lm import load as mlx_load
    from mlx_lm import generate as mlx_generate

    if adapter_path is not None and not Path(adapter_path).exists():
        msg = f"adapter_path missing: {adapter_path}"
        log(f"  LOAD SKIP for {nick}: {msg}")
        return {"error": msg, "n_samples": 0}

    try:
        if adapter_path:
            model, tokenizer = mlx_load(hf_id, adapter_path=adapter_path)
        else:
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
        prefix = build_prefix(sid)
        user_msg = build_user_msg(prefix)
        prompt_text = _format_chat_prompt(tokenizer, user_msg)
        t_g = time.time()
        try:
            completion = mlx_generate(
                model, tokenizer,
                prompt=prompt_text,
                max_tokens=max_tokens,
                verbose=False,
            )
        except Exception as exc:
            log(f"     [{i+1}/{len(samples)}] GEN ERROR ({sid}): {exc!r}")
            completion = ""
        dt_g = time.time() - t_g

        # Concatenate prefix + generated (after stripping markdown fence si
        # le modele a quand meme ajoute des ```)
        completion_clean = _strip_md_fence(completion)
        full_sch = prefix + completion_clean

        # Score via Phase 4 ERC + fallback
        erc = run_erc(full_sch, nick, sid)
        scores = composite_score(erc)

        records.append({
            "id": sid,
            "source": sample.get("source", ""),
            "prompt_user": user_msg[:300],
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
        "# KiCad Phase 6 reco #24 — task completion (header prefix)",
        "",
        f"_Generated: {md['timestamp']}_",
        "",
        f"- KiCad CLI    : `{md['kicad_cli']}` (v{md.get('kicad_version','?')})",
        f"- Models       : {len(md['models'])}",
        f"- Samples eval : {md.get('n_samples_eval','?')} (skipped: {SPI_BUS_ID})",
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
        line = f"- **{m['nickname']}** — `{m['hf_id']}`"
        if m.get("adapter_path"):
            line += f" + adapter `{m['adapter_path']}`"
        lines.append(line)
    OUT_MD.write_text("\n".join(lines) + "\n")
    log(f"Markdown saved to {OUT_MD}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> int:
    ap = argparse.ArgumentParser(description="KiCad Phase 6 — task completion (header prefix)")
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
        models = [(n, h, a) for n, h, a in MODELS if n in args.models]
        miss = sorted(set(args.models) - {n for n, _, _ in MODELS})
        if miss:
            log(f"WARN: unknown models: {miss}")
    else:
        models = list(MODELS)
        if SKIP_HEAVY and not args.include_heavy:
            before = len(models)
            models = [(n, h, a) for n, h, a in models if n not in HEAVY_NICKS]
            if len(models) < before:
                log(f"WARN: skipping heavy {sorted(HEAVY_NICKS)} "
                    f"(KICAD_SKIP_HEAVY=1; --include-heavy to force)")

    log("=" * 70)
    log("KICAD PHASE 6 reco #24 — task completion bench")
    log(f"  Models    : {len(models)} -> {[n for n, _, _ in models]}")
    log(f"  Samples   : {n_eval}/{n_total} (skipped: {SPI_BUS_ID})")
    log(f"  MaxTokens : {args.max_tokens}")
    log(f"  KICAD_CLI : {KICAD_CLI}")
    log(f"  Output    : {OUT_JSON}")
    log(f"  Output    : {OUT_MD}")
    log(f"  Log       : {LOG_PATH}")
    log("=" * 70)

    if args.dry_run:
        log("DRY-RUN — listing models / prompts / prefix shape")
        for nick, hf, adapter in models:
            ap_exists = (Path(adapter).exists() if adapter else "n/a")
            log(f"  {nick}: hf={hf}  adapter={adapter}  exists={ap_exists}")
        log(f"DRY-RUN — {n_eval} samples to eval :")
        for s in samples:
            mark = "SKIP" if s["id"] == SPI_BUS_ID else "EVAL"
            log(f"  [{mark}] {s['id']}")
        sample_for_demo = next((s for s in samples if s["id"] != SPI_BUS_ID), None)
        if sample_for_demo:
            pfx = build_prefix(sample_for_demo["id"])
            usr = build_user_msg(pfx)
            log(f"DRY-RUN — prefix size for '{sample_for_demo['id']}' = {len(pfx)} chars")
            log(f"DRY-RUN — first prefix lines:\n{pfx}")
            log(f"DRY-RUN — user msg size = {len(usr)} chars")
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
            "kicad_cli": KICAD_CLI,
            "kicad_version": detect_kicad_version(),
            "max_tokens": args.max_tokens,
            "n_samples_total": n_total,
            "n_samples_eval": n_eval,
            "skipped_ids": [SPI_BUS_ID],
            "score_weights": {"parse_ok": 0.30, "erc_no_errors": 0.40,
                              "erc_low_warnings": 0.30},
            "kicad_version_in_prefix": KICAD_VERSION_TS,
            "models": [
                {"nickname": n, "hf_id": h, "adapter_path": a}
                for n, h, a in models
            ],
        },
        "bench": {},
    }
    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    for nick, hf, adapter in models:
        log(f"\n############ MODEL: {nick} ############")
        try:
            per = generate_for_model(nick, hf, adapter, samples, args.max_tokens)
        except Exception as exc:
            log(f"  MODEL CRASHED: {exc!r}")
            log(traceback.format_exc())
            per = {"error": f"model_crash: {exc!r}", "n_samples": 0}
        results["bench"][nick] = per
        OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        log(f"=== done {nick} (saved {OUT_JSON.name}) ===")

    write_markdown(results)
    log("KICAD PHASE 6 reco #24 BENCH COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
