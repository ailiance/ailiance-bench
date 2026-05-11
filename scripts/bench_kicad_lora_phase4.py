#!/usr/bin/env python3
"""
Bench Phase 4 LORA — ERC reel via kicad-cli sur les .kicad_sch generes en
Phase 2 LORA (lit ~/bench-results/kicad_phase2_lora.json).

Reuse INTEGRALEMENT la logique ERC + scoring de bench_kicad_phase4.py (DRY).
Seule difference : input par defaut = phase2_lora.json, sortie = phase4_lora.{json,md}.

Si kicad_phase2_lora.json n'existe pas (Phase 2 LORA pas encore finie ou
crashed), on skip avec WARN au lieu de crasher (orchestrateur compat).

Usage :
  python3 ~/scripts/bench_kicad_lora_phase4.py
  python3 ~/scripts/bench_kicad_lora_phase4.py --models gemma-e4b-eukiki-final
  python3 ~/scripts/bench_kicad_lora_phase4.py --dry-run
  python3 ~/scripts/bench_kicad_lora_phase4.py --phase2 /path/to/kicad_phase2_lora.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

# --- Reuse ERC runner / scoring / aggregation from base Phase 4 ---
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Import depuis bench_kicad_phase4 (DRY)
import bench_kicad_phase4 as p4base  # noqa: E402
from bench_kicad_phase4 import (  # noqa: E402
    BENCH_DIR,
    KICAD_CLI,
    ERR_CAP,
    WARN_CAP,
    composite_score,
    detect_kicad_version,
    load_phase2,
    run_for_model,
    run_erc,
)

# Sortie distincte (LORA)
PHASE2_LORA_JSON = BENCH_DIR / "kicad_phase2_lora.json"
OUT_JSON = BENCH_DIR / "kicad_phase4_lora.json"
OUT_MD = BENCH_DIR / "kicad_phase4_lora.md"

# Logger local
LOG_DIR = Path.home() / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / f"bench_kicad_lora_phase4-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
_log_fh = None


def log(msg: str) -> None:
    global _log_fh
    if _log_fh is None:
        _log_fh = LOG_PATH.open("a", buffering=1)
    line = f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    if _log_fh:
        _log_fh.write(line + "\n")


# Patch: re-route base module logger -> our log file too, so run_for_model logs land here.
p4base.log = log


# --------------------------------------------------------------------------- #
# Markdown — meme format que base mais combos (base+adapter) en titre
# --------------------------------------------------------------------------- #


def write_markdown(results: dict) -> None:
    md = results["metadata"]
    lines = [
        "# KiCad Phase 4 LORA bench — ERC reel via kicad-cli (adapters)",
        "",
        f"_Generated: {md['timestamp']}_",
        "",
        f"- KiCad CLI    : `{md['kicad_cli']}` (v{md.get('kicad_version','?')})",
        f"- Phase 2 src  : `{md['phase2_path']}`",
        f"- Combos       : {len(md['models'])}",
        f"- Timeout ERC  : {md['erc_timeout_s']}s",
        f"- Score weights: parse_ok 0.30 + erc_no_errors 0.40 + erc_low_warnings 0.30",
        "",
        "| Combo | n | parse_ok_cli | avg_err | avg_warn | composite |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for nick in md["models"]:
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
    OUT_MD.write_text("\n".join(lines) + "\n")
    log(f"Markdown saved to {OUT_MD}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> int:
    ap = argparse.ArgumentParser(description="KiCad Phase 4 LORA — ERC bench (adapters)")
    ap.add_argument("--phase2", type=Path, default=PHASE2_LORA_JSON,
                    help=f"Path to kicad_phase2_lora.json (default: {PHASE2_LORA_JSON})")
    ap.add_argument("--models", nargs="*", default=None,
                    help="Subset of LoRA combo nicknames to score")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--timeout", type=int, default=None)
    args = ap.parse_args()

    if args.timeout is not None:
        # mute base module's ERC timeout via attribute (functions read it at call time)
        p4base.ERC_TIMEOUT_S = args.timeout

    BENCH_DIR.mkdir(parents=True, exist_ok=True)

    log("=" * 70)
    log("KICAD PHASE 4 LORA BENCH — ERC reel via kicad-cli (adapters)")
    log(f"  KICAD_CLI : {KICAD_CLI} (v{detect_kicad_version()})")
    log(f"  Phase 2   : {args.phase2}")
    log(f"  Output    : {OUT_JSON}")
    log(f"  Output    : {OUT_MD}")
    log(f"  Log       : {LOG_PATH}")
    log(f"  Timeout   : {p4base.ERC_TIMEOUT_S}s/sample")
    log("=" * 70)

    # --- dry-run : tolere phase2_lora.json absent ---
    if args.dry_run:
        log("DRY-RUN — checking environment...")
        if not Path(KICAD_CLI).exists():
            log(f"  WARN: kicad-cli not found at {KICAD_CLI}")
        else:
            log(f"  OK : kicad-cli at {KICAD_CLI} (v{detect_kicad_version()})")
        ref = Path.home() / "eu-kiki-data" / "kicad-sch-refs" / "spi_bus_4devices.kicad_sch"
        if ref.exists():
            log(f"  testing ERC on reference {ref.name} ...")
            try:
                txt = ref.read_text()
                erc = run_erc(txt, "dryrun_lora", "spi_bus_4devices")
                sc = composite_score(erc)
                log(f"  result: via={erc['parse_via']} errs={erc['errors_count']} "
                    f"warns={erc['warnings_count']} composite={sc['composite']}")
            except Exception as exc:
                log(f"  ref ERC test FAILED: {exc!r}")
        if not args.phase2.exists():
            log(f"  WARN: phase2 LORA source absent yet: {args.phase2}")
            log("  -> Phase 4 LORA ready ; will run once Phase 2 LORA produces this file.")
            log("  -> (graceful skip — non-fatal)")
            log("DRY-RUN done.")
            return 0
        try:
            ph2 = load_phase2(args.phase2)
            for nick, blk in ph2.get("bench", {}).items():
                n = blk.get("n_samples", 0)
                log(f"  phase2_lora combo {nick}: n_samples={n}")
        except Exception as exc:
            log(f"  WARN: cannot read phase2_lora: {exc!r}")
        log("DRY-RUN done.")
        return 0

    # --- run reel ---
    if not args.phase2.exists():
        log(f"WARN: phase2 LORA source not found: {args.phase2}")
        log("WARN: skipping Phase 4 LORA (Phase 2 LORA likely failed or not run)")
        # On ecrit un placeholder pour debug ulterieur
        results = {
            "metadata": {
                "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "kicad_cli": KICAD_CLI,
                "kicad_version": detect_kicad_version(),
                "phase2_path": str(args.phase2),
                "erc_timeout_s": p4base.ERC_TIMEOUT_S,
                "models": [],
                "skip_reason": "phase2_lora.json missing",
            },
            "bench": {},
        }
        OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        return 0

    try:
        ph2 = load_phase2(args.phase2)
    except Exception as exc:
        log(f"FATAL: cannot load phase2 LORA: {exc!r}")
        return 2

    bench_in = ph2.get("bench", {}) or {}
    if not bench_in:
        log("WARN: phase2_lora.bench is empty — nothing to evaluate (graceful)")
        results = {
            "metadata": {
                "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "kicad_cli": KICAD_CLI,
                "kicad_version": detect_kicad_version(),
                "phase2_path": str(args.phase2),
                "erc_timeout_s": p4base.ERC_TIMEOUT_S,
                "models": [],
                "skip_reason": "phase2_lora.bench empty",
            },
            "bench": {},
        }
        OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        return 0

    if args.models:
        wanted = set(args.models)
        models_order = [n for n in bench_in if n in wanted]
        miss = sorted(wanted - set(bench_in))
        if miss:
            log(f"WARN: unknown LoRA combos in phase2_lora: {miss}")
    else:
        models_order = list(bench_in.keys())

    results = {
        "metadata": {
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "kicad_cli": KICAD_CLI,
            "kicad_version": detect_kicad_version(),
            "phase2_path": str(args.phase2),
            "phase2_metadata": ph2.get("metadata", {}),
            "erc_timeout_s": p4base.ERC_TIMEOUT_S,
            "score_weights": {
                "parse_ok": 0.30,
                "erc_no_errors": 0.40,
                "erc_low_warnings": 0.30,
                "err_cap": ERR_CAP,
                "warn_cap": WARN_CAP,
            },
            "models": models_order,
        },
        "bench": {},
    }
    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    for nick in models_order:
        log(f"\n############ COMBO: {nick} ############")
        blk = bench_in.get(nick, {}) or {}
        if "error" in blk:
            log(f"  Phase 2 LORA had error for {nick}: {blk['error']!r} — skipping ERC")
            results["bench"][nick] = {"error": blk["error"], "n_samples": 0}
            OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))
            continue
        try:
            per = run_for_model(nick, blk)
        except Exception as exc:
            log(f"  COMBO ERC CRASHED: {exc!r}")
            log(traceback.format_exc())
            per = {"error": f"erc_crash: {exc!r}", "n_samples": 0}
        results["bench"][nick] = per
        OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        log(f"=== done {nick} (saved {OUT_JSON.name}) ===")

    write_markdown(results)
    log("KICAD PHASE 4 LORA BENCH COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
