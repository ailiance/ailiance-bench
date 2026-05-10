#!/usr/bin/env python3
"""
Bench baseline « 31 domaines × modèles 4-bit » — perplexité uniquement.

Cible la macM1 32 Go : on n'utilise QUE des modèles MLX 4-bit déjà téléchargés
dans ~/.cache/huggingface/hub/, jamais les BF16 (Qwen3.6-35B / Mistral-Medium
128B) qui requièrent GrosMac.

Pour chaque modèle, on calcule la perplexité sur le `valid.jsonl` de chacun
des 31 domaines présents dans EUKIKI_DATA_DIR (par défaut
~/eu-kiki-data/hf-traced).

Sortie :
  ~/bench-results/31_domains_baseline.json    (machine-readable, overwrite)
  ~/bench-results/31_domains_baseline.md      (tableau modèles × domaines)

Lancement :
  python3 ~/scripts/bench_31_domains_base.py                     # tout
  python3 ~/scripts/bench_31_domains_base.py --models gemma3-4b  # un seul
  python3 ~/scripts/bench_31_domains_base.py --domains cpp rust  # subset

Variables d'env :
  EUKIKI_DATA_DIR    : dossier hf-traced/<domain>/valid.jsonl
                       (def: ~/eu-kiki-data/hf-traced)
  BENCH_RESULTS_DIR  : où écrire baseline.{json,md}
                       (def: ~/bench-results)
  MLX_VENV_BIN       : bin du venv où vit mlx_lm.perplexity
                       (def: ~/mlx-stack/.venv/bin)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths & constants
# --------------------------------------------------------------------------- #

HOME = Path.home()
DATA_DIR = Path(os.environ.get("EUKIKI_DATA_DIR", HOME / "eu-kiki-data" / "hf-traced"))
BENCH_DIR = Path(os.environ.get("BENCH_RESULTS_DIR", HOME / "bench-results"))
PYBIN = Path(os.environ.get("MLX_VENV_BIN", HOME / "mlx-stack" / ".venv" / "bin"))
MLX_PERPLEXITY = str(PYBIN / "mlx_lm.perplexity")

OUT_JSON = BENCH_DIR / "31_domains_baseline.json"
OUT_MD = BENCH_DIR / "31_domains_baseline.md"

# Modèles 4-bit "EU AI Act compatibles" (signataires GPAI Code of Practice août 2025)
# ET sortis < 6 mois (post 2025-11-10). Filtrage 2026-05-10.
# Sortants (non signataires ou trop vieux) : llama-3.2-3b, qwen-coder-3b, qwen3.5-9b,
#   jackrong-9b-opus, helium-1-2b, gemma3-4b.
# Entrants : ministral-3-14b instruct/reasoning, granite-4.1-30b, gemma-e2b.
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

# Bench params (alignés sur bench_new_models.py pour comparabilité)
PPL_NUM_SAMPLES = 25      # nombre d'exemples (cohérent avec bench_eu_kiki_v2.py)
PPL_SEQ_LEN = 1024
PPL_BATCH_SIZE = 1
PPL_TIMEOUT = 600         # 10 min par (modèle, domaine) — petits modèles 4-bit

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #


def log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def run(cmd: list[str], timeout: int) -> tuple[int, str, str]:
    log("RUN: " + " ".join(shlex.quote(p) for p in cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        log(f"TIMEOUT after {timeout}s")
        return 124, out, err


# --------------------------------------------------------------------------- #
# Domain discovery
# --------------------------------------------------------------------------- #


def discover_domains() -> list[str]:
    """Liste les domaines avec un valid.jsonl utilisable."""
    if not DATA_DIR.exists():
        log(f"FATAL: DATA_DIR introuvable: {DATA_DIR}")
        return []
    domains = sorted(
        p.name for p in DATA_DIR.iterdir()
        if p.is_dir() and (p / "valid.jsonl").exists()
    )
    return domains


# --------------------------------------------------------------------------- #
# Perplexity (en pointant directement sur le dossier-domaine)
# --------------------------------------------------------------------------- #

PPL_RX = re.compile(r"Perplexity:\s*([0-9.]+)\s*(?:±\s*([0-9.]+))?")


def bench_one(model_id: str, domain: str) -> dict:
    domain_dir = DATA_DIR / domain
    cmd = [
        MLX_PERPLEXITY,
        "--model", model_id,
        "--data-path", str(domain_dir),
        "--num-samples", str(PPL_NUM_SAMPLES),
        "--sequence-length", str(PPL_SEQ_LEN),
        "--batch-size", str(PPL_BATCH_SIZE),
        "--seed", "0",
    ]
    rc, stdout, stderr = run(cmd, PPL_TIMEOUT)

    if rc == 124:
        return {"ppl": None, "stderr_ppl": None, "status": f"TIMEOUT_{PPL_TIMEOUT}s"}

    text = stdout + "\n" + stderr
    m = PPL_RX.search(text)
    if not m:
        log(f"  no ppl line — rc={rc}; stderr tail:")
        log(stderr[-400:])
        return {"ppl": None, "stderr_ppl": None, "status": f"NO_PPL_rc{rc}"}

    ppl = float(m.group(1))
    err = float(m.group(2)) if m.group(2) else None
    return {"ppl": ppl, "stderr_ppl": err, "status": "ok"}


# --------------------------------------------------------------------------- #
# Output rendering
# --------------------------------------------------------------------------- #


def write_markdown(results: dict, domains: list[str], models: list[tuple[str, str]]) -> None:
    """Tableau markdown : lignes = modèles, colonnes = domaines."""
    lines: list[str] = []
    lines.append(f"# 31-domains baseline (perplexity, lower=better)")
    lines.append("")
    lines.append(f"_Generated: {results['metadata']['timestamp']}_")
    lines.append("")
    lines.append(f"- Samples / domain: **{PPL_NUM_SAMPLES}**, seq-len: **{PPL_SEQ_LEN}**")
    lines.append(f"- Data: `{DATA_DIR}`")
    lines.append(f"- Models: {len(models)} (4-bit MLX only — fits in 32 GB RAM)")
    lines.append("")

    header = ["Model"] + domains
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] + ["---:"] * len(domains)) + "|")

    for nick, _ in models:
        row = [f"**{nick}**"]
        for dom in domains:
            entry = results["bench"].get(nick, {}).get(dom, {})
            ppl = entry.get("ppl")
            if ppl is None:
                row.append(entry.get("status", "—") if entry else "—")
            else:
                row.append(f"{ppl:.2f}")
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")
    lines.append("## Models tested")
    lines.append("")
    for nick, hf_id in models:
        lines.append(f"- **{nick}** — `{hf_id}`")
    lines.append("")

    OUT_MD.write_text("\n".join(lines))
    log(f"Markdown saved to {OUT_MD}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> int:
    ap = argparse.ArgumentParser(description="Baseline perplexity bench: 31 domains × 4-bit models")
    ap.add_argument("--models", nargs="*", default=None,
                    help="Subset de nicknames (ex: gemma3-4b qwen3.5-9b)")
    ap.add_argument("--domains", nargs="*", default=None,
                    help="Subset de domaines")
    ap.add_argument("--dry-run", action="store_true",
                    help="Affiche ce qui serait benché sans rien lancer")
    args = ap.parse_args()

    BENCH_DIR.mkdir(parents=True, exist_ok=True)

    if not Path(MLX_PERPLEXITY).exists():
        log(f"FATAL: mlx_lm.perplexity introuvable: {MLX_PERPLEXITY}")
        log("Set MLX_VENV_BIN or check your venv install.")
        return 2

    all_domains = discover_domains()
    if not all_domains:
        log("FATAL: aucun domaine avec valid.jsonl trouvé.")
        return 2

    if args.domains:
        domains = [d for d in args.domains if d in all_domains]
        missing = sorted(set(args.domains) - set(all_domains))
        if missing:
            log(f"WARN: domaines ignorés (absents): {missing}")
    else:
        domains = all_domains

    if args.models:
        models = [(n, h) for n, h in MODELS if n in args.models]
        missing = sorted(set(args.models) - {n for n, _ in MODELS})
        if missing:
            log(f"WARN: modèles ignorés (inconnus): {missing}")
    else:
        models = MODELS

    log("=" * 70)
    log("31-DOMAINS BASELINE BENCH")
    log(f"  Models  : {len(models)} → {[n for n, _ in models]}")
    log(f"  Domains : {len(domains)} → {domains}")
    log(f"  Output  : {OUT_JSON}")
    log(f"  Output  : {OUT_MD}")
    eta_min = len(models) * len(domains) * 1.5  # ~1.5 min/cellule (4-bit, 25 samples)
    log(f"  ETA     : ~{eta_min:.0f} min (rough, scales with model size)")
    log("=" * 70)

    if args.dry_run:
        log("DRY-RUN — exiting without launching bench.")
        return 0

    results = {
        "metadata": {
            "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_dir": str(DATA_DIR),
            "num_samples": PPL_NUM_SAMPLES,
            "sequence_length": PPL_SEQ_LEN,
            "batch_size": PPL_BATCH_SIZE,
            "models": [{"nickname": n, "hf_id": h} for n, h in models],
            "domains": domains,
        },
        "bench": {},
    }

    for nick, hf_id in models:
        log(f"\n############ MODEL: {nick} ({hf_id}) ############")
        results["bench"].setdefault(nick, {})
        for dom in domains:
            log(f"  -> {nick} / {dom}")
            entry = bench_one(hf_id, dom)
            results["bench"][nick][dom] = entry
            ppl_s = f"{entry['ppl']:.2f}" if entry.get("ppl") is not None else entry.get("status", "?")
            log(f"     ppl={ppl_s}")

            # Save incrémental après chaque cellule (résilience aux crashes)
            OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))

        log(f"=== done {nick} ===")

    write_markdown(results, domains, models)
    log("BASELINE BENCH COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
