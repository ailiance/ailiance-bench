#!/usr/bin/env python3
# ============================================================================
# bench_fork_retry.py
# ----------------------------------------------------------------------------
# Bench retry de qwen3.5-9b et helium-1-2b avec le wheel mlx fork
# (mlx==0.32.0.dev20260510+eaa16e95) qui patche iogpu.rsrc_limit a 1.5x sur
# Mac M1 Max 32 Go RAM. Pas de QuantizedKVCache (le fork debloque l'OOM
# upstream), juste mlx_lm.evaluate standard.
#
# Modeles + taches :
#   - qwen3.5-9b   (mlx-community/Qwen3.5-9B-MLX-4bit)
#       gsm8k_cot (8-shot), arc_easy (0-shot), mmlu_pro_computer_science (0-shot)
#       timeout 1500s par tache
#   - helium-1-2b  (kyutai/helium-1-2b — confirme via all_models.txt section)
#       memes 3 taches, timeout 600s (modele plus petit)
#
# Sortie :
#   - append a ~/bench-results/all_models.txt avec marqueur
#       === FORK RETEST (wheel +eaa16e95, 1.5x) — <timestamp> ===
#       --- <nickname> / <task> (fork) ---
#   - log file : ~/logs/bench-fork-retry-<timestamp>.log
#   - resultats individuels : ~/bench-results/<nickname>-<task>-fork/
# ============================================================================

from __future__ import annotations

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

PYBIN = HOME / "mlx-stack" / ".venv" / "bin"
MLX_EVALUATE = str(PYBIN / "mlx_lm.evaluate")

# (nickname, hf_id, list de taches, timeout)
RETRIES: list[tuple[str, str, list[str], int]] = [
    (
        "qwen3.5-9b",
        "mlx-community/Qwen3.5-9B-MLX-4bit",
        ["gsm8k_cot", "arc_easy", "mmlu_pro_computer_science"],
        1500,
    ),
    (
        "helium-1-2b",
        "kyutai/helium-1-2b",
        ["gsm8k_cot", "arc_easy", "mmlu_pro_computer_science"],
        600,
    ),
]

LIMIT_PER_TASK = 100
GSM8K_NUM_SHOTS = 8

TIMESTAMP = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
LOG_FILE = LOGS_DIR / f"bench-fork-retry-{TIMESTAMP}.log"


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
    """Append (jamais ecraser) au all_models.txt."""
    with ALL_MODELS_TXT.open("a") as fh:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")


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


def run(cmd: list[str], timeout: int, *, log_fh) -> tuple[int, str, str]:
    log("RUN: " + " ".join(shlex.quote(p) for p in cmd), log_fh=log_fh)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        log(f"TIMEOUT after {timeout}s", log_fh=log_fh)
        return 124, out, err


def bench_one(nickname: str, model_id: str, task: str, timeout: int, *, log_fh) -> str:
    out_dir = BENCH_DIR / f"{nickname}-{task}-fork"
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        MLX_EVALUATE,
        "--model", model_id,
        "--tasks", task,
        "--output-dir", str(out_dir),
        "--num-shots", str(GSM8K_NUM_SHOTS) if task == "gsm8k_cot" else "0",
        "--limit", str(LIMIT_PER_TASK),
        "--seed", "0",
    ]

    rc, stdout, stderr = run(cmd, timeout, log_fh=log_fh)

    header = f"\n--- {nickname} / {task} (fork) ---\n"

    if rc == 124:
        return header + f"_TIMEOUT after {timeout}s (fork retry)_\n"

    if rc != 0:
        log(f"FAIL ({rc}) on {nickname}/{task} — stderr tail:", log_fh=log_fh)
        log(stderr[-800:], log_fh=log_fh)
        json_path = find_eval_json(out_dir, task)
        if json_path is None:
            return header + f"_NO RESULT (rc={rc}, fork retry)_\n"

    json_path = find_eval_json(out_dir, task)
    if json_path is None:
        return header + "_NO RESULT (likely crashed/short output, fork retry)_\n"

    return header + extract_metrics(json_path, task) + "\n"


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    with LOG_FILE.open("a") as log_fh:
        log(f"=== bench_fork_retry start (PID {os.getpid()}) ===", log_fh=log_fh)
        log(f"all_models.txt = {ALL_MODELS_TXT}", log_fh=log_fh)
        log(f"log file       = {LOG_FILE}", log_fh=log_fh)

        marker = (
            f"\n=== FORK RETEST (wheel +eaa16e95, 1.5x) — {TIMESTAMP} ===\n"
        )
        append_result(marker)

        for nickname, model_id, tasks, timeout in RETRIES:
            log(f"\n############ MODEL: {nickname} ({model_id}) timeout={timeout}s ############",
                log_fh=log_fh)
            for task in tasks:
                chunk = bench_one(nickname, model_id, task, timeout, log_fh=log_fh)
                append_result(chunk)
                log(f"appended {nickname}/{task} (fork)", log_fh=log_fh)

        log("=== bench_fork_retry END ===", log_fh=log_fh)

    return 0


if __name__ == "__main__":
    sys.exit(main())
