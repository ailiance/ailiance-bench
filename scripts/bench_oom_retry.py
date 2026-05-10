#!/usr/bin/env python3
# ============================================================================
# bench_oom_retry.py
# ----------------------------------------------------------------------------
# POURQUOI :
#   Le bench `~/scripts/bench_new_models.py` (et son prédécesseur sur la table
#   `~/bench-results/all_models.txt`) a laissé plusieurs (modèle, tâche) en
#   échec :
#     - ministral-3-8b/gsm8k_cot         → OOM rc=-6 ([METAL] Insufficient Memory)
#     - qwen3.5-9b/{gsm8k_cot, arc_easy, mmlu_pro_computer_science}
#                                        → TIMEOUT 600s (modèle 9B trop lent
#                                          avec le KV cache fp16)
#     - helium-1-2b/{gsm8k_cot, arc_easy, mmlu_pro_computer_science}
#                                        → NO_RESULT (kyutai/helium-1-2b est
#                                          un modèle bf16 brut, KV cache fp16
#                                          + 8-shot prompt = OOM ou crash
#                                          silencieux sur Mac M1 Pro 32 Go)
#
#   Sur un Mac M1 Pro 32 Go RAM, l'unified memory limite l'empreinte du KV
#   cache à quelques Go avant que Metal renvoie « Insufficient Memory ». La
#   solution standard côté mlx-lm est d'utiliser un `QuantizedKVCache`
#   (kv_bits=8, group_size=64), qui divise par ~2 la taille du cache et
#   débloque les contextes longs (8-shot gsm8k_cot fait facilement 4-6 k
#   tokens de prompt avec le COT).
#
# STRATÉGIE :
#   `mlx_lm.evaluate` (mlx-lm 0.31.3) ne supporte PAS de flag `--kv-bits`
#   natif (vérifié via `mlx_lm.evaluate --help` : seuls --num-shots,
#   --max-tokens, --limit, --temp, --top-p, --top-k, --seed, --batch-size,
#   --apply-chat-template, --chat-template-args, --trust-remote-code,
#   --confirm-run-unsafe-code sont exposés). De plus,
#   `mlx_lm.models.cache.make_prompt_cache(model, max_kv_size=None)` ne prend
#   pas non plus de paramètre `kv_bits` dans 0.31.3.
#
#   Solution : on lance `mlx_lm.evaluate` via un wrapper Python (`-c "..."`)
#   qui monkey-patch `mlx_lm.models.cache.make_prompt_cache` pour retourner
#   des `QuantizedKVCache(group_size=64, bits=8)` à la place des `KVCache`
#   fp16 par défaut. Le protocole `update_and_fetch` est respecté donc les
#   modèles llama-like (Ministral, Qwen3.5, Helium) consomment ce cache de
#   manière transparente.
#
#   En complément, pour gsm8k_cot on passe de 8-shot → 4-shot et on cap
#   --max-tokens à 1024 (suffisant pour le COT court) afin de sécuriser la
#   marge mémoire. Cela rend les chiffres NON strictement comparables aux
#   runs 8-shot précédents — c'est un tradeoff à signaler dans le rapport.
#
# CONFIG MAC M1 PRO 32 Go :
#   venv      = /Users/electron/mlx-stack/.venv
#   mlx       = 0.31.2
#   mlx-lm    = 0.31.3
#   timeout   = 1500s par tâche (qwen3.5-9b est lent même avec KV quantisé)
#
# QUAND LANCER :
#   À lancer SEULEMENT quand `~/bench-results/bench_new.pid` n'existe plus
#   ou quand `ps -p <pid>` montre que le process bench est mort :
#
#     test -f ~/bench-results/bench_new.pid && \
#         ps -p $(cat ~/bench-results/bench_new.pid) >/dev/null \
#         && echo "BENCH ENCORE EN COURS — NE PAS LANCER" \
#         || /Users/electron/mlx-stack/.venv/bin/python \
#                ~/scripts/bench_oom_retry.py
#
# DRY-RUN :
#     python3 ~/scripts/bench_oom_retry.py --dry-run
#   imprime la matrice (modèle, tâche, commande exacte) sans rien exécuter.
# ============================================================================

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Constantes
# --------------------------------------------------------------------------- #

HOME = Path.home()
BENCH_DIR = HOME / "bench-results"
LOGS_DIR = HOME / "logs"
ALL_MODELS_TXT = BENCH_DIR / "all_models.txt"
BENCH_PID_FILE = BENCH_DIR / "bench_new.pid"

PYBIN = HOME / "mlx-stack" / ".venv" / "bin"
PYTHON = str(PYBIN / "python")

# (nickname, hf_id, set de tâches à relancer)
RETRIES: list[tuple[str, str, list[str]]] = [
    (
        "ministral-3-8b",
        "mlx-community/Ministral-3-8B-Instruct-2512-4bit",
        ["gsm8k_cot"],
    ),
    (
        "qwen3.5-9b",
        "mlx-community/Qwen3.5-9B-MLX-4bit",
        ["gsm8k_cot", "arc_easy", "mmlu_pro_computer_science"],
    ),
    (
        "helium-1-2b",
        "kyutai/helium-1-2b",
        ["gsm8k_cot", "arc_easy", "mmlu_pro_computer_science"],
    ),
]

LIMIT_PER_TASK = 100
TASK_TIMEOUT = 1500  # 25 min, qwen 9B reste lent même avec KV quantisé
KV_BITS = 8
KV_GROUP_SIZE = 64
# Pour gsm8k_cot on rabaisse les shots et on cap les tokens générés afin de
# garder une marge mémoire confortable (sinon le 8-shot de gsm8k a tendance à
# saturer même avec QuantizedKVCache sur les 9B).
GSM8K_NUM_SHOTS = 4
GSM8K_MAX_TOKENS = 1024

TIMESTAMP = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
LOG_FILE = LOGS_DIR / f"bench-oom-retry-{TIMESTAMP}.log"


# --------------------------------------------------------------------------- #
# Wrapper Python lancé en sous-processus
# --------------------------------------------------------------------------- #
# Ce snippet est exécuté par /Users/electron/mlx-stack/.venv/bin/python -c
# Il :
#   1. Monkey-patch mlx_lm.models.cache.make_prompt_cache pour retourner des
#      QuantizedKVCache (kv_bits=KV_BITS, group_size=KV_GROUP_SIZE).
#   2. Patche aussi mlx_lm.evaluate.make_prompt_cache (rebind via from-import).
#   3. Réécrit sys.argv et appelle mlx_lm.evaluate.main() comme si la CLI
#      avait été invoquée normalement.
#
# La variable d'environnement MLX_KV_BITS / MLX_KV_GROUP_SIZE permet d'ajuster
# sans rééditer le wrapper.
WRAPPER_TEMPLATE = r"""
import os, sys
KV_BITS = int(os.environ.get("MLX_KV_BITS", "8"))
KV_GS = int(os.environ.get("MLX_KV_GROUP_SIZE", "64"))

import mlx_lm.models.cache as _cache
from mlx_lm.models.cache import QuantizedKVCache

_orig_make = _cache.make_prompt_cache

def _patched_make_prompt_cache(model, max_kv_size=None):
    # On ignore max_kv_size (None par défaut côté mlx_lm.evaluate) et on
    # construit un QuantizedKVCache par couche du modèle. Le nombre de couches
    # est récupéré via model.layers (convention partagée llama/qwen/mistral).
    layers = getattr(model, "layers", None)
    if layers is None:
        # fallback : laisser le helper original gérer
        return _orig_make(model, max_kv_size=max_kv_size)
    return [QuantizedKVCache(group_size=KV_GS, bits=KV_BITS) for _ in layers]

_cache.make_prompt_cache = _patched_make_prompt_cache

# Rebind dans evaluate (importé via "from .models.cache import make_prompt_cache")
import mlx_lm.evaluate as _ev
_ev.make_prompt_cache = _patched_make_prompt_cache

# Réécrit argv : sys.argv[0] sera remplacé par "mlx_lm.evaluate"
sys.argv = ["mlx_lm.evaluate"] + sys.argv[1:]
print(f"[wrapper] QuantizedKVCache active (bits={KV_BITS}, group_size={KV_GS})", flush=True)
_ev.main()
"""


# --------------------------------------------------------------------------- #
# Utilitaires
# --------------------------------------------------------------------------- #

def log(msg: str, *, log_fh=None) -> None:
    ts = dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    if log_fh is not None:
        log_fh.write(line + "\n")
        log_fh.flush()


def append_result(text: str) -> None:
    """Append (jamais écraser) au all_models.txt."""
    with ALL_MODELS_TXT.open("a") as fh:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")


def bench_pid_alive() -> int | None:
    """Retourne le PID du bench en cours s'il tourne encore, sinon None."""
    if not BENCH_PID_FILE.exists():
        return None
    try:
        pid = int(BENCH_PID_FILE.read_text().strip())
    except Exception:
        return None
    try:
        os.kill(pid, 0)  # signal 0 = ping
        return pid
    except OSError:
        return None


def find_eval_json(out_dir: Path, task: str) -> Path | None:
    if not out_dir.exists():
        return None
    candidates = sorted(out_dir.glob(f"eval_*_{task}"))
    if candidates:
        return candidates[-1]
    candidates = sorted(p for p in out_dir.iterdir() if task in p.name and p.is_file())
    return candidates[-1] if candidates else None


def extract_metrics(json_path: Path, task: str) -> str:
    try:
        data = json.loads(json_path.read_text())
    except Exception as exc:
        return f"_ERROR: cannot parse {json_path.name}: {exc}_"

    payload = data.get(task) or data.get("results", {}).get(task) or data
    lines: list[str] = []
    if isinstance(payload, dict):
        for k, v in payload.items():
            if isinstance(v, float):
                lines.append(f'    "{k}": {v},')
            elif isinstance(v, str):
                lines.append(f'    "{k}": "{v}",')
            elif isinstance(v, int):
                lines.append(f'    "{k}": {v},')
        if lines:
            lines[-1] = lines[-1].rstrip(",")
    return "\n".join(lines) if lines else "_NO RESULT (empty payload)_"


def build_cmd(nickname: str, model_id: str, task: str) -> tuple[list[str], Path]:
    """Construit la commande wrapper qui patch make_prompt_cache puis lance
    mlx_lm.evaluate, et retourne aussi le out_dir associé."""
    # Suffixe -kvq8 pour ne pas écraser l'output_dir du run précédent
    out_dir = BENCH_DIR / f"{nickname}-{task}-kvq8"
    out_dir.mkdir(parents=True, exist_ok=True)

    eval_args = [
        "--model", model_id,
        "--tasks", task,
        "--output-dir", str(out_dir),
        "--limit", str(LIMIT_PER_TASK),
        "--seed", "0",
    ]
    if task == "gsm8k_cot":
        eval_args += [
            "--num-shots", str(GSM8K_NUM_SHOTS),
            "--max-tokens", str(GSM8K_MAX_TOKENS),
        ]
    else:
        eval_args += ["--num-shots", "0"]

    cmd = [PYTHON, "-c", WRAPPER_TEMPLATE] + eval_args
    return cmd, out_dir


def run(cmd: list[str], timeout: int, *, log_fh) -> tuple[int, str, str]:
    log("RUN: " + " ".join(shlex.quote(p) if i != 2 else "<wrapper>"
                            for i, p in enumerate(cmd)),
        log_fh=log_fh)
    env = os.environ.copy()
    env["MLX_KV_BITS"] = str(KV_BITS)
    env["MLX_KV_GROUP_SIZE"] = str(KV_GROUP_SIZE)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        log(f"TIMEOUT after {timeout}s", log_fh=log_fh)
        return 124, out, err


def bench_one(nickname: str, model_id: str, task: str, *, log_fh) -> str:
    cmd, out_dir = build_cmd(nickname, model_id, task)
    rc, stdout, stderr = run(cmd, TASK_TIMEOUT, log_fh=log_fh)

    header = f"\n--- {nickname} / {task} (kvq8) ---\n"

    if rc == 124:
        return header + f"_TIMEOUT after {TASK_TIMEOUT}s (kvq8 retry)_\n"

    if rc != 0:
        log(f"FAIL ({rc}) on {nickname}/{task} — stderr tail:", log_fh=log_fh)
        log(stderr[-800:], log_fh=log_fh)
        json_path = find_eval_json(out_dir, task)
        if json_path is None:
            return header + f"_NO RESULT (rc={rc}, kvq8 retry)_\n"

    json_path = find_eval_json(out_dir, task)
    if json_path is None:
        return header + "_NO RESULT (likely crashed/short output, kvq8 retry)_\n"

    return header + extract_metrics(json_path, task) + "\n"


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Relance ciblée OOM/timeout/NO_RESULT avec QuantizedKVCache 8-bit"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="N'exécute rien, imprime juste la matrice (modèle, tâche, cmd).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Lance même si bench_new.pid pointe vers un process vivant (DANGER).",
    )
    args = parser.parse_args()

    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print(f"# Dry run — log file would be {LOG_FILE}")
        print(f"# Append target           = {ALL_MODELS_TXT}")
        print(f"# QuantizedKVCache config  = bits={KV_BITS}, group_size={KV_GROUP_SIZE}")
        print(f"# Task timeout             = {TASK_TIMEOUT}s")
        for nickname, model_id, tasks in RETRIES:
            for task in tasks:
                cmd, out_dir = build_cmd(nickname, model_id, task)
                print()
                print(f"# {nickname} / {task} -> {out_dir}")
                # On masque le wrapper (très long) dans l'affichage
                shown = [shlex.quote(p) if i != 2 else "<wrapper-snippet>"
                         for i, p in enumerate(cmd)]
                print("  " + " ".join(shown))
        return 0

    # Sécurité : ne pas lancer si le bench original tourne encore.
    pid = bench_pid_alive()
    if pid is not None and not args.force:
        print(
            f"ABORT: bench original encore vivant (PID {pid} via {BENCH_PID_FILE}).",
            file=sys.stderr,
        )
        print("Relance avec --force si tu sais ce que tu fais.", file=sys.stderr)
        return 2

    with LOG_FILE.open("a") as log_fh:
        log(f"=== bench_oom_retry start (PID {os.getpid()}) ===", log_fh=log_fh)
        log(f"all_models.txt = {ALL_MODELS_TXT}", log_fh=log_fh)
        log(f"log file       = {LOG_FILE}", log_fh=log_fh)
        log(f"KV cache       = QuantizedKVCache(bits={KV_BITS}, group_size={KV_GROUP_SIZE})",
            log_fh=log_fh)

        # Marqueur de section dans all_models.txt
        marker = (
            f"\n=== OOM/TIMEOUT RETRY (kvq8, num_shots gsm8k={GSM8K_NUM_SHOTS}, "
            f"max_tokens gsm8k={GSM8K_MAX_TOKENS}) — {TIMESTAMP} ===\n"
        )
        append_result(marker)

        for nickname, model_id, tasks in RETRIES:
            log(f"\n############ MODEL: {nickname} ({model_id}) ############",
                log_fh=log_fh)
            for task in tasks:
                chunk = bench_one(nickname, model_id, task, log_fh=log_fh)
                append_result(chunk)
                log(f"appended {nickname}/{task} (kvq8)", log_fh=log_fh)

        log("=== bench_oom_retry END ===", log_fh=log_fh)

    return 0


if __name__ == "__main__":
    sys.exit(main())
