#!/usr/bin/env python3
"""
compare_base_vs_lora.py — Croise les baselines BASE vs LoRA pour produire
                          une matrice de lift (composite_lora - composite_base).

Phases couvertes :
  P1 : ~/bench-results/kicad_functional_phase1{,_lora}.json
       (datasets : kicad-dsl, kicad-pcb, spice-sim ; champ score
        `composite_score` par dataset)
  P2 : ~/bench-results/kicad_phase2{,_lora}.json
       (un seul dataset implicite kicad-sch-gen ; champ `composite_score`)
  P3 : ~/bench-results/kicad_phase3{,_lora}.json
       (kicad-sch-extract ; `composite_score`)
  P4 : ~/bench-results/kicad_phase4{,_lora}.json
       (ERC absolu ; `composite_avg`)
  P5 : ~/bench-results/kicad_phase5{,_lora}.json   (si existe — ERC delta)
       (`composite_v2_avg`)

Hypothese : les 3 adapters LoRA sont sur la meme base gemma-4-E4B
(`gemma-e4b-eu-kiki-base`), donc le baseline de comparaison pour chacun
est ce modele unique.

Output :
  ~/bench-results/compare_base_vs_lora.json
  ~/bench-results/compare_base_vs_lora.md

Mode --dry-run : n'ecrit rien, affiche ce qui serait fait + status fichiers.

Gestion gracieuse :
  - Si un fichier LoRA n'existe pas -> warning + colonnes "(en attente)".
  - Si la base n'a pas la metrique -> "(n/a)".
  - Si un dataset existe seulement cote base ou cote lora -> idem.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #

HOME = Path.home()
BENCH_DIR = Path(os.environ.get("BENCH_RESULTS_DIR", HOME / "bench-results"))
LOG_DIR = HOME / "logs"

BASE_REF_NICK = "gemma-e4b-eu-kiki-base"  # le baseline de comparaison

# Adapters LoRA et alias court pour les colonnes
LORA_NICKS = [
    ("gemma-e4b-eukiki-final", "+eu-kiki"),
    ("gemma-e4b-mascarade-final", "+mascarade"),
    ("gemma-e4b-aggro-test", "+aggro"),
]

# Phase config : (label, base_path, lora_path, datasets_extractor, score_field)
# datasets_extractor(model_block) -> dict {ds_name: composite_value}
# score_field est juste pour le rapport de meta.

def _p1_datasets(model_block: dict) -> dict[str, float | None]:
    """P1 / P1_lora : model_block est un dict {ds_name: {...,'composite_score':...}}."""
    out: dict[str, float | None] = {}
    if not isinstance(model_block, dict):
        return out
    for ds_name, ds_blk in model_block.items():
        if isinstance(ds_blk, dict):
            out[ds_name] = ds_blk.get("composite_score")
    return out


def _flat_dataset(model_block: dict, label: str, score_key: str) -> dict[str, float | None]:
    """P2/3/4/5 : un seul dataset par modele, on fabrique {label: composite}."""
    if not isinstance(model_block, dict) or "error" in model_block:
        return {label: None}
    return {label: model_block.get(score_key)}


PHASES = [
    ("P1",
     BENCH_DIR / "kicad_functional_phase1.json",
     BENCH_DIR / "kicad_functional_phase1_lora.json",
     _p1_datasets,
     "composite_score"),
    ("P2",
     BENCH_DIR / "kicad_phase2.json",
     BENCH_DIR / "kicad_phase2_lora.json",
     lambda mb: _flat_dataset(mb, "kicad-sch-gen", "composite_score"),
     "composite_score"),
    ("P3",
     BENCH_DIR / "kicad_phase3.json",
     BENCH_DIR / "kicad_phase3_lora.json",
     lambda mb: _flat_dataset(mb, "kicad-sch-extract", "composite_score"),
     "composite_score"),
    ("P4",
     BENCH_DIR / "kicad_phase4.json",
     BENCH_DIR / "kicad_phase4_lora.json",
     lambda mb: _flat_dataset(mb, "kicad-erc-abs", "composite_avg"),
     "composite_avg"),
    ("P5",
     BENCH_DIR / "kicad_phase5.json",
     BENCH_DIR / "kicad_phase5_lora.json",
     lambda mb: _flat_dataset(mb, "kicad-erc-delta", "composite_v2_avg"),
     "composite_v2_avg"),
]

OUT_JSON = BENCH_DIR / "compare_base_vs_lora.json"
OUT_MD = BENCH_DIR / "compare_base_vs_lora.md"

LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / f"compare_base_vs_lora-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
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


def _safe_load(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        log(f"  WARN: cannot read {path}: {exc!r}")
        return None


def _fmt_num(v: float | None, prec: int = 3) -> str:
    if v is None:
        return "n/a"
    return f"{v:.{prec}f}"


def _fmt_lift(v_lora: float | None, v_base: float | None) -> str:
    if v_lora is None:
        return "(en attente)"
    if v_base is None:
        return f"{v_lora:.3f} (no base)"
    delta = v_lora - v_base
    pct = (delta * 100.0)
    sign = "+" if delta >= 0 else ""
    return f"{v_lora:.3f} ({sign}{pct:.1f}pts)"


# --------------------------------------------------------------------------- #


def build_matrix() -> dict:
    """Construit la matrice complete. Format :
       {
         "P1": {
           "base_path": "...", "lora_path": "...",
           "lora_present": bool,
           "datasets": {
             "kicad-dsl": {
               "base": 0.42,
               "lora": {"+eu-kiki": 0.85, "+mascarade": 0.50, "+aggro": 0.43},
             }, ...
           }
         }, ...
       }
    """
    out: dict[str, Any] = {}
    for label, base_path, lora_path, extractor, score_field in PHASES:
        ph: dict[str, Any] = {
            "base_path": str(base_path),
            "lora_path": str(lora_path),
            "score_field": score_field,
            "base_present": base_path.exists(),
            "lora_present": lora_path.exists(),
            "datasets": {},
            "warnings": [],
        }
        d_base = _safe_load(base_path)
        d_lora = _safe_load(lora_path)

        if d_base is None:
            ph["warnings"].append(f"base file missing: {base_path}")
        if d_lora is None:
            ph["warnings"].append(f"lora file missing: {lora_path} (en attente)")

        # Compute base scores per dataset
        base_block = (d_base or {}).get("bench", {}).get(BASE_REF_NICK, {}) if d_base else {}
        base_scores = extractor(base_block) if base_block else {}
        if d_base and not base_block:
            ph["warnings"].append(
                f"base ref nick '{BASE_REF_NICK}' not in {base_path.name}"
            )

        # Compute lora scores per dataset / per adapter
        lora_per_adapter: dict[str, dict[str, float | None]] = {}
        for nick, alias in LORA_NICKS:
            blk = (d_lora or {}).get("bench", {}).get(nick, {}) if d_lora else {}
            lora_per_adapter[nick] = extractor(blk) if blk else {}

        # Union datasets
        all_ds: list[str] = []
        for s in [base_scores] + list(lora_per_adapter.values()):
            for k in s:
                if k not in all_ds:
                    all_ds.append(k)

        for ds in all_ds:
            ph["datasets"][ds] = {
                "base": base_scores.get(ds),
                "lora": {alias: lora_per_adapter[nick].get(ds)
                         for nick, alias in LORA_NICKS},
            }
        out[label] = ph
    return out


def write_outputs(matrix: dict, dry_run: bool) -> None:
    if dry_run:
        log("DRY-RUN — would write:")
        log(f"  {OUT_JSON}")
        log(f"  {OUT_MD}")
        log("DRY-RUN — preview of markdown table:")
        for line in build_markdown(matrix).splitlines()[:25]:
            log(f"  | {line}")
        return

    out = {
        "metadata": {
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "base_ref_nick": BASE_REF_NICK,
            "lora_nicks": [{"nick": n, "alias": a} for n, a in LORA_NICKS],
            "phases": list(matrix.keys()),
        },
        "matrix": matrix,
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    log(f"wrote {OUT_JSON}")
    OUT_MD.write_text(build_markdown(matrix))
    log(f"wrote {OUT_MD}")


def build_markdown(matrix: dict) -> str:
    aliases = [a for _, a in LORA_NICKS]
    lines = [
        "# Compare base vs LoRA — composite lift par phase / dataset",
        "",
        f"_Generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_",
        "",
        f"- Base ref     : `{BASE_REF_NICK}` (les 3 adapters LoRA sont sur cette meme base)",
        f"- Adapters     : {', '.join(n for n, _ in LORA_NICKS)}",
        "- Lift         : `composite_lora - composite_base` (en pts ; +X.Xpts)",
        "",
        f"| Phase | Dataset | base | {' | '.join(aliases)} |",
        f"|---|---|---:|{'---:|' * len(aliases)}",
    ]
    for label, ph in matrix.items():
        if not ph["datasets"]:
            note = "(en attente)" if not ph["lora_present"] else "(no data)"
            lines.append(f"| {label} | — | — | {' | '.join([note]*len(aliases))} |")
            continue
        for ds, scores in ph["datasets"].items():
            base_v = scores["base"]
            row = [
                f"| {label}", f" {ds}", f" {_fmt_num(base_v)}",
            ]
            for alias in aliases:
                lora_v = scores["lora"].get(alias)
                row.append(f" {_fmt_lift(lora_v, base_v)}")
            lines.append("|".join(row) + " |")
    # Warnings section
    has_warn = any(ph["warnings"] for ph in matrix.values())
    if has_warn:
        lines += ["", "## Warnings", ""]
        for label, ph in matrix.items():
            for w in ph["warnings"]:
                lines.append(f"- **{label}** : {w}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Compare BASE vs LoRA composite scores across phases")
    ap.add_argument("--dry-run", action="store_true",
                    help="Don't write outputs, just print what would be done")
    args = ap.parse_args()

    BENCH_DIR.mkdir(parents=True, exist_ok=True)

    log("=" * 70)
    log("COMPARE BASE vs LORA")
    log(f"  bench dir   : {BENCH_DIR}")
    log(f"  output JSON : {OUT_JSON}")
    log(f"  output MD   : {OUT_MD}")
    log(f"  base ref    : {BASE_REF_NICK}")
    log(f"  adapters    : {[n for n,_ in LORA_NICKS]}")
    log(f"  log         : {LOG_PATH}")
    log("=" * 70)

    # File presence check
    for label, base_path, lora_path, *_ in PHASES:
        log(f"  [{label}] base={'OK' if base_path.exists() else 'MISSING'} ({base_path.name}) "
            f"lora={'OK' if lora_path.exists() else 'MISSING (en attente)'} ({lora_path.name})")

    matrix = build_matrix()
    write_outputs(matrix, args.dry_run)

    log("COMPARE DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
