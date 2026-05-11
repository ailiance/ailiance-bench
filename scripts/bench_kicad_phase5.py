#!/usr/bin/env python3
"""
Bench Phase 5 — ERC delta vs reference (re-scoring de Phase 4).

Probleme adresse :
  Phase 4 utilise une saturation absolue
        composite_v1 = 0.30*parse_ok + 0.40*max(0, 1-errs/10) + 0.30*max(0, 1-warns/20)
  donc la reference spi_bus_4devices (75 errs, 54 warns) -> composite 0.30,
  alors qu'elle EST la verite terrain. Idem ref led_blinker (3e/4w) -> 0.82.

Solution :
  Pour chaque sample (model, prompt), on retrouve la reference du meme prompt
  (champ `id` du sample, lookup dans le dataset Phase 2 source : kicad-sch-gen
  valid.jsonl), on lance kicad-cli ERC dessus pour obtenir errs_ref/warns_ref
  (cache une fois par id), puis on score sur le DELTA :

        errs_delta  = max(0, errs_gen - errs_ref)
        warns_delta = max(0, warns_gen - warns_ref)
        no_extra_errs = max(0, 1 - errs_delta / 5)     # plafond plus tolerant
        no_extra_warns = max(0, 1 - warns_delta / 10)
        composite_v2 = 0.30*parse_ok + 0.40*no_extra_errs + 0.30*no_extra_warns

  Ainsi un modele qui reproduit la ref a l'identique a composite_v2 = 1.0
  (pas 0.30/0.82).

Inputs :
  ~/bench-results/kicad_phase4.json            (base, requis)
  ~/bench-results/kicad_phase4_lora.json       (lora, optionnel)
  ~/bench-results/kicad_phase2.json            (pour recuperer le `generated`
                                                full-text quand le sample n'a
                                                pas le sch dans phase4 — phase4
                                                ne stocke pas le contenu, mais
                                                phase2 a `generated` tronque
                                                a 3000 chars)

Refs :
  ~/eu-kiki-data/kicad-sch-gen/valid.jsonl  (id -> assistant content)

Outputs :
  ~/bench-results/kicad_phase5.json           (base re-score)
  ~/bench-results/kicad_phase5.md
  ~/bench-results/kicad_phase5_lora.json      (si lora present)
  ~/bench-results/kicad_phase5_lora.md

Reuse :
  bench_kicad_phase4.run_erc(), _strip_md_fence, _safe_token  (DRY)

Usage :
  python3 ~/scripts/bench_kicad_phase5.py --dry-run
  python3 ~/scripts/bench_kicad_phase5.py
  python3 ~/scripts/bench_kicad_phase5.py --no-lora    # base seulement
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Reuse Phase 4 ERC primitives (DRY)
from bench_kicad_phase4 import (  # noqa: E402
    KICAD_CLI,
    detect_kicad_version,
    run_erc,
    _strip_md_fence,
)

# --------------------------------------------------------------------------- #

HOME = Path.home()
BENCH_DIR = Path(os.environ.get("BENCH_RESULTS_DIR", HOME / "bench-results"))
LOG_DIR = HOME / "logs"

PHASE4_BASE_JSON = BENCH_DIR / "kicad_phase4.json"
PHASE4_LORA_JSON = BENCH_DIR / "kicad_phase4_lora.json"
PHASE2_BASE_JSON = BENCH_DIR / "kicad_phase2.json"
PHASE2_LORA_JSON = BENCH_DIR / "kicad_phase2_lora.json"

OUT_JSON_BASE = BENCH_DIR / "kicad_phase5.json"
OUT_MD_BASE = BENCH_DIR / "kicad_phase5.md"
OUT_JSON_LORA = BENCH_DIR / "kicad_phase5_lora.json"
OUT_MD_LORA = BENCH_DIR / "kicad_phase5_lora.md"

GEN_DATASET = HOME / "eu-kiki-data" / "kicad-sch-gen" / "valid.jsonl"

# Plafonds delta (plus tolerants que Phase 4 absolue)
ERR_DELTA_CAP = 5
WARN_DELTA_CAP = 10

# --------------------------------------------------------------------------- #

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / f"bench_kicad_phase5-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
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
# Reference loading + ERC cache
# --------------------------------------------------------------------------- #


def load_expected_map(path: Path = GEN_DATASET) -> dict[str, str]:
    """Lit le dataset Phase 2 source et construit id -> contenu assistant (sch)."""
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = d.get("_id") or d.get("id")
            if not sid:
                continue
            for msg in d.get("messages", []) or []:
                if msg.get("role") == "assistant":
                    out[sid] = msg.get("content", "")
                    break
    return out


_REF_ERC_CACHE: dict[str, dict[str, Any]] = {}


def erc_for_ref(sid: str, sch_text: str) -> dict[str, Any]:
    """ERC sur la reference du sample id, mise en cache."""
    if sid in _REF_ERC_CACHE:
        return _REF_ERC_CACHE[sid]
    log(f"  ERC (ref) {sid} ...")
    erc = run_erc(sch_text, "ref", sid)
    _REF_ERC_CACHE[sid] = erc
    log(f"    -> via={erc['parse_via']} errs={erc['errors_count']} warns={erc['warnings_count']}")
    return erc


# --------------------------------------------------------------------------- #
# Phase 2 generated text loader (Phase 4 ne stocke pas le sch, on lit phase2)
# --------------------------------------------------------------------------- #


def load_generated_map(phase2_path: Path) -> dict[tuple[str, str], str]:
    """Map (model_nick, sample_id) -> texte genere stocke dans phase2.json."""
    out: dict[tuple[str, str], str] = {}
    if not phase2_path.exists():
        log(f"  WARN: phase2 source absent: {phase2_path}")
        return out
    try:
        with phase2_path.open("r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception as exc:
        log(f"  WARN: cannot load phase2 {phase2_path}: {exc!r}")
        return out
    for nick, blk in (d.get("bench", {}) or {}).items():
        for s in blk.get("samples", []) or []:
            sid = s.get("id")
            gen = s.get("generated", "")
            if sid:
                out[(nick, sid)] = gen
    return out


# --------------------------------------------------------------------------- #
# Composite v2 (delta vs reference)
# --------------------------------------------------------------------------- #


def composite_v2(parse_ok: float,
                 errs_gen: int | None, warns_gen: int | None,
                 errs_ref: int | None, warns_ref: int | None,
                 via_gen: str, via_ref: str) -> dict[str, Any]:
    """Score delta. Si pas d'ERC kicad-cli sur le gen ou la ref, on tombe back
       sur le composite v1 partiel (parse_ok seulement, no_err/no_w = 0)."""
    have_gen = (via_gen == "kicad-cli" and errs_gen is not None and warns_gen is not None)
    have_ref = (via_ref == "kicad-cli" and errs_ref is not None and warns_ref is not None)

    if have_gen and have_ref:
        errs_delta = max(0, errs_gen - errs_ref)
        warns_delta = max(0, warns_gen - warns_ref)
        no_extra_errs = max(0.0, 1.0 - errs_delta / float(ERR_DELTA_CAP))
        no_extra_warns = max(0.0, 1.0 - warns_delta / float(WARN_DELTA_CAP))
    elif have_gen and not have_ref:
        # Pas de ref ERC : fallback v1 absolu (cap 10/20) pour ne pas bloquer
        errs_delta = errs_gen
        warns_delta = warns_gen
        no_extra_errs = max(0.0, 1.0 - errs_gen / 10.0)
        no_extra_warns = max(0.0, 1.0 - warns_gen / 20.0)
    else:
        errs_delta = None
        warns_delta = None
        no_extra_errs = 0.0
        no_extra_warns = 0.0

    composite = 0.30 * parse_ok + 0.40 * no_extra_errs + 0.30 * no_extra_warns
    return {
        "errs_delta": errs_delta,
        "warns_delta": warns_delta,
        "no_extra_errors": round(no_extra_errs, 4),
        "no_extra_warnings": round(no_extra_warns, 4),
        "composite_v2": round(composite, 4),
    }


# --------------------------------------------------------------------------- #
# Re-score Phase 4 file
# --------------------------------------------------------------------------- #


def rescore_phase4(p4_path: Path, p2_path: Path, expected_map: dict[str, str],
                   out_json: Path, out_md: Path, label: str) -> dict | None:
    """Re-score un fichier kicad_phase4*.json en composite_v2 (delta).
       Renvoie le dict resultat ou None si fichier absent."""
    if not p4_path.exists():
        log(f"[{label}] phase4 file absent : {p4_path} — skip")
        return None
    try:
        with p4_path.open() as f:
            p4 = json.load(f)
    except Exception as exc:
        log(f"[{label}] cannot read {p4_path}: {exc!r}")
        return None

    gen_map = load_generated_map(p2_path)
    log(f"[{label}] loaded {len(gen_map)} (model, sample) generated texts from {p2_path.name}")

    # Pre-compute ERC ref pour tous les ids necessaires
    needed_ids: set[str] = set()
    for nick, blk in (p4.get("bench", {}) or {}).items():
        for s in blk.get("samples", []) or []:
            if s.get("id"):
                needed_ids.add(s["id"])
    log(f"[{label}] {len(needed_ids)} unique reference ids: {sorted(needed_ids)}")

    ref_erc_summary: dict[str, dict[str, Any]] = {}
    for sid in sorted(needed_ids):
        ref_text = expected_map.get(sid)
        if ref_text is None:
            log(f"  WARN: no reference text in dataset for id={sid!r} — composite_v2 will fallback to absolute")
            ref_erc_summary[sid] = {"parse_via": "missing", "errors_count": None, "warnings_count": None}
            continue
        erc = erc_for_ref(sid, ref_text)
        ref_erc_summary[sid] = {
            "parse_via": erc["parse_via"],
            "errors_count": erc["errors_count"],
            "warnings_count": erc["warnings_count"],
        }

    # Re-score chaque sample
    out_bench: dict[str, dict] = {}
    for nick, blk in (p4.get("bench", {}) or {}).items():
        if "error" in blk:
            out_bench[nick] = {"error": blk["error"], "n_samples": 0}
            continue
        samples = blk.get("samples", []) or []
        new_samples: list[dict] = []
        composites: list[float] = []
        delta_errs: list[int] = []
        delta_warns: list[int] = []
        for s in samples:
            sid = s.get("id", "")
            erc_blk = s.get("erc", {}) or {}
            scores_blk = s.get("scores", {}) or {}
            parse_ok = float(scores_blk.get("parse_ok_score", erc_blk.get("parse_ok", 0.0) or 0.0))
            ref_info = ref_erc_summary.get(sid, {})
            v2 = composite_v2(
                parse_ok=parse_ok,
                errs_gen=erc_blk.get("errors_count"),
                warns_gen=erc_blk.get("warnings_count"),
                errs_ref=ref_info.get("errors_count"),
                warns_ref=ref_info.get("warnings_count"),
                via_gen=erc_blk.get("parse_via", ""),
                via_ref=ref_info.get("parse_via", "missing"),
            )
            new_samples.append({
                "id": sid,
                "source": s.get("source", ""),
                "prompt": s.get("prompt", "")[:200],
                "erc_gen": {
                    "parse_via": erc_blk.get("parse_via"),
                    "errors_count": erc_blk.get("errors_count"),
                    "warnings_count": erc_blk.get("warnings_count"),
                },
                "erc_ref": ref_info,
                "scores_v1": {
                    "parse_ok": scores_blk.get("parse_ok_score"),
                    "erc_no_errors": scores_blk.get("erc_no_errors"),
                    "erc_low_warnings": scores_blk.get("erc_low_warnings"),
                    "composite": scores_blk.get("composite"),
                },
                "scores_v2": v2,
            })
            composites.append(v2["composite_v2"])
            if v2["errs_delta"] is not None:
                delta_errs.append(v2["errs_delta"])
            if v2["warns_delta"] is not None:
                delta_warns.append(v2["warns_delta"])
        n = len(new_samples)
        agg = {
            "n_samples": n,
            "composite_v2_avg": round(sum(composites) / n, 4) if n else 0.0,
            "composite_v1_avg": blk.get("composite_avg"),
            "avg_errs_delta": round(sum(delta_errs) / len(delta_errs), 2) if delta_errs else None,
            "avg_warns_delta": round(sum(delta_warns) / len(delta_warns), 2) if delta_warns else None,
            "samples": new_samples,
        }
        out_bench[nick] = agg

    out = {
        "metadata": {
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "label": label,
            "kicad_cli": KICAD_CLI,
            "kicad_version": detect_kicad_version(),
            "phase4_path": str(p4_path),
            "phase2_path": str(p2_path),
            "expected_dataset": str(GEN_DATASET),
            "score_weights": {
                "parse_ok": 0.30,
                "no_extra_errors": 0.40,
                "no_extra_warnings": 0.30,
                "err_delta_cap": ERR_DELTA_CAP,
                "warn_delta_cap": WARN_DELTA_CAP,
            },
            "models": list(out_bench.keys()),
            "ref_erc_summary": ref_erc_summary,
        },
        "bench": out_bench,
    }
    out_json.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    log(f"[{label}] wrote {out_json}")

    # Markdown
    lines = [
        f"# KiCad Phase 5 — ERC delta vs reference ({label})",
        "",
        f"_Generated: {out['metadata']['timestamp']}_",
        "",
        f"- Source phase4   : `{p4_path}`",
        f"- Refs            : `{GEN_DATASET}`",
        f"- KiCad CLI       : `{KICAD_CLI}` ({out['metadata']['kicad_version']})",
        f"- Score weights   : 0.30 parse_ok + 0.40 no_extra_errs + 0.30 no_extra_warns "
        f"(caps {ERR_DELTA_CAP}/{WARN_DELTA_CAP})",
        "",
        "## Reference ERC (per id)",
        "",
        "| id | via | errs_ref | warns_ref |",
        "|---|---|---:|---:|",
    ]
    for sid in sorted(ref_erc_summary):
        info = ref_erc_summary[sid]
        lines.append(
            f"| {sid} | {info.get('parse_via','?')} | "
            f"{info.get('errors_count')} | {info.get('warnings_count')} |"
        )

    lines += [
        "",
        "## Re-score per model",
        "",
        "| Model | n | composite_v1 | composite_v2 | avg errs_delta | avg warns_delta |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for nick, agg in out_bench.items():
        if "error" in agg:
            lines.append(f"| **{nick}** | 0 | — | — | — | err: {agg['error'][:30]} |")
            continue
        n = agg.get("n_samples", 0)
        v1 = agg.get("composite_v1_avg")
        v2 = agg.get("composite_v2_avg", 0.0)
        ad_e = agg.get("avg_errs_delta")
        ad_w = agg.get("avg_warns_delta")
        lines.append(
            f"| **{nick}** | {n} | "
            f"{(v1 if v1 is not None else 0):.3f} | "
            f"{v2:.3f} | "
            f"{(ad_e if ad_e is not None else 0):.2f} | "
            f"{(ad_w if ad_w is not None else 0):.2f} |"
        )
    out_md.write_text("\n".join(lines) + "\n")
    log(f"[{label}] wrote {out_md}")
    return out


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> int:
    ap = argparse.ArgumentParser(description="KiCad Phase 5 — ERC delta vs ref")
    ap.add_argument("--phase4-base", type=Path, default=PHASE4_BASE_JSON)
    ap.add_argument("--phase4-lora", type=Path, default=PHASE4_LORA_JSON)
    ap.add_argument("--phase2-base", type=Path, default=PHASE2_BASE_JSON)
    ap.add_argument("--phase2-lora", type=Path, default=PHASE2_LORA_JSON)
    ap.add_argument("--no-lora", action="store_true",
                    help="Skip LoRA file even if present")
    ap.add_argument("--dry-run", action="store_true",
                    help="List samples + ref ids; do not run ERC unless missing kicad-cli")
    args = ap.parse_args()

    BENCH_DIR.mkdir(parents=True, exist_ok=True)

    log("=" * 70)
    log("KICAD PHASE 5 BENCH — ERC delta vs reference")
    log(f"  phase4 base : {args.phase4_base}")
    log(f"  phase4 lora : {args.phase4_lora}  (skip={args.no_lora})")
    log(f"  refs        : {GEN_DATASET}")
    log(f"  output base : {OUT_JSON_BASE}")
    log(f"  output lora : {OUT_JSON_LORA}")
    log(f"  log         : {LOG_PATH}")
    log("=" * 70)

    expected_map = load_expected_map(GEN_DATASET)
    if not expected_map:
        log(f"FATAL: cannot load expected refs from {GEN_DATASET}")
        return 2
    log(f"loaded {len(expected_map)} reference texts: {sorted(expected_map.keys())}")

    if args.dry_run:
        log("DRY-RUN — listing samples to re-score (no ERC, no write)")
        for label, p4_path in [("base", args.phase4_base), ("lora", args.phase4_lora)]:
            if label == "lora" and args.no_lora:
                continue
            if not p4_path.exists():
                log(f"  [{label}] phase4 file absent: {p4_path} — would skip")
                continue
            try:
                with p4_path.open() as f:
                    p4 = json.load(f)
            except Exception as exc:
                log(f"  [{label}] cannot read: {exc!r}")
                continue
            n_total = 0
            ids: set[str] = set()
            for nick, blk in (p4.get("bench", {}) or {}).items():
                ss = blk.get("samples", []) or []
                n_total += len(ss)
                for s in ss:
                    if s.get("id"):
                        ids.add(s["id"])
                log(f"  [{label}] {nick}: {len(ss)} samples to re-score")
            missing_refs = [i for i in ids if i not in expected_map]
            log(f"  [{label}] total samples = {n_total}, unique ref ids = {len(ids)}, "
                f"missing in dataset = {missing_refs or 'none'}")
        # Quick ERC on one ref to validate kicad-cli setup
        first_id = next(iter(expected_map))
        log(f"  testing kicad-cli ERC on ref {first_id} ...")
        erc = run_erc(expected_map[first_id], "dryrun", first_id)
        log(f"    -> via={erc['parse_via']} errs={erc['errors_count']} "
            f"warns={erc['warnings_count']} rc={erc['rc']}")
        log("DRY-RUN done.")
        return 0

    # --- run reel ---
    rc = 0
    try:
        rescore_phase4(args.phase4_base, args.phase2_base, expected_map,
                       OUT_JSON_BASE, OUT_MD_BASE, "base")
    except Exception as exc:
        log(f"BASE rescore CRASHED: {exc!r}")
        log(traceback.format_exc())
        rc = 1

    if not args.no_lora:
        try:
            rescore_phase4(args.phase4_lora, args.phase2_lora, expected_map,
                           OUT_JSON_LORA, OUT_MD_LORA, "lora")
        except Exception as exc:
            log(f"LORA rescore CRASHED: {exc!r}")
            log(traceback.format_exc())
            rc = 1

    log("KICAD PHASE 5 BENCH COMPLETE")
    return rc


if __name__ == "__main__":
    sys.exit(main())
