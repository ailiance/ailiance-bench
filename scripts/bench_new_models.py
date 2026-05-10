#!/usr/bin/env python3
"""
Bench des modèles MLX nouvellement téléchargés.

Lance pour chaque modèle :
  - 3 tâches lm-eval-harness via mlx_lm.evaluate (gsm8k_cot, arc_easy, mmlu_pro_computer_science)
    avec timeout 900s (15 min) chacune.
  - 5 perplexity tests via mlx_lm.perplexity sur les niches
    (spice, stm32, kicad, embedded_iot, emc_power).

Append les résultats au format identique à ~/bench-results/all_models.txt :
  === <nickname> ===
  --- <nickname> / <task> ---
  <extrait JSON des métriques OU "Perplexity: X ± Y">

Les résultats individuels (--output-dir) sont stockés sous
~/bench-results/<nickname>-<task>/.
"""

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
NICHES_DIR = HOME / "lora-data-niches"
ALL_MODELS_TXT = BENCH_DIR / "all_models.txt"

PYBIN = HOME / "mlx-stack" / ".venv" / "bin"
MLX_EVALUATE = str(PYBIN / "mlx_lm.evaluate")
MLX_PERPLEXITY = str(PYBIN / "mlx_lm.perplexity")

MODELS: list[tuple[str, str]] = [
    ("ministral-3-8b", "mlx-community/Ministral-3-8B-Instruct-2512-4bit"),
    ("granite-4.1-3b", "mlx-community/granite-4.1-3b-4bit"),
]

LM_TASKS: list[str] = [
    "gsm8k_cot",
    "arc_easy",
    "mmlu_pro_computer_science",
]

NICHES: list[str] = [
    "spice",
    "stm32",
    "kicad",
    "embedded_iot",
    "emc_power",
]

# Nombre d'exemples (cohérent avec les autres modèles dont stderr ≈ 0.04 → n=100)
LIMIT_PER_TASK = 100
# Timeout par tâche lm-eval (900s = 15 min, plus généreux que les 600s qui ont fait timeout qwen3.5-9b)
TASK_TIMEOUT = 900
# Perplexity : 20 samples × 1024 seq comme niches_ppl_v2.txt
PPL_NUM_SAMPLES = 20
PPL_SEQ_LEN = 1024
PPL_TIMEOUT = 900


# --------------------------------------------------------------------------- #
# Utilitaires
# --------------------------------------------------------------------------- #

def log(msg: str) -> None:
    ts = dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    print(line, file=sys.stderr, flush=True)


def append_result(text: str) -> None:
    """Append (jamais écraser) au all_models.txt."""
    with ALL_MODELS_TXT.open("a") as fh:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")


def run(cmd: list[str], timeout: int) -> tuple[int, str, str]:
    """Lance une commande, capture stdout/stderr, applique un timeout."""
    log("RUN: " + " ".join(shlex.quote(p) for p in cmd))
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
        log(f"TIMEOUT after {timeout}s")
        return 124, out, err


# --------------------------------------------------------------------------- #
# Bench LM-eval
# --------------------------------------------------------------------------- #

def find_eval_json(out_dir: Path, task: str) -> Path | None:
    """Cherche le fichier JSON produit par mlx_lm.evaluate pour ce task."""
    if not out_dir.exists():
        return None
    candidates = sorted(out_dir.glob(f"eval_*_{task}"))
    if candidates:
        return candidates[-1]
    # fallback : n'importe quel fichier contenant le nom du task
    candidates = sorted(p for p in out_dir.iterdir() if task in p.name and p.is_file())
    return candidates[-1] if candidates else None


def extract_metrics(json_path: Path, task: str) -> str:
    """Extrait l'extrait des métriques au format identique aux autres sections."""
    try:
        data = json.loads(json_path.read_text())
    except Exception as exc:  # pragma: no cover
        return f"_ERROR: cannot parse {json_path.name}: {exc}_"

    # Format : { "<task>": { ...metrics... } } ou imbriqué
    payload = data.get(task) or data.get("results", {}).get(task) or data
    lines: list[str] = []

    if isinstance(payload, dict):
        # Préserver l'ordre des clés tel que mlx_lm.evaluate les écrit
        for k, v in payload.items():
            if isinstance(v, float):
                lines.append(f'    "{k}": {v},')
            elif isinstance(v, str):
                lines.append(f'    "{k}": "{v}",')
            elif isinstance(v, int):
                lines.append(f'    "{k}": {v},')
        # Retirer la dernière virgule
        if lines:
            lines[-1] = lines[-1].rstrip(",")
    return "\n".join(lines) if lines else "_NO RESULT (empty payload)_"


def bench_lm_task(nickname: str, model_id: str, task: str) -> str:
    """Lance une tâche lm-eval. Retourne le texte à append à all_models.txt."""
    out_dir = BENCH_DIR / f"{nickname}-{task}"
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        MLX_EVALUATE,
        "--model", model_id,
        "--tasks", task,
        "--output-dir", str(out_dir),
        "--num-shots", "8" if task == "gsm8k_cot" else "0",
        "--limit", str(LIMIT_PER_TASK),
        "--seed", "0",
    ]

    rc, stdout, stderr = run(cmd, TASK_TIMEOUT)

    header = f"\n--- {nickname} / {task} ---\n"

    if rc == 124:
        return header + f"_TIMEOUT after {TASK_TIMEOUT}s_\n"

    if rc != 0:
        log(f"FAIL ({rc}) on {nickname}/{task} — stderr tail:")
        log(stderr[-500:])
        # Tente quand même de récupérer un fichier produit
        json_path = find_eval_json(out_dir, task)
        if json_path is None:
            return header + f"_NO RESULT (rc={rc})_\n"

    json_path = find_eval_json(out_dir, task)
    if json_path is None:
        return header + "_NO RESULT (likely crashed/short output)_\n"

    return header + extract_metrics(json_path, task) + "\n"


# --------------------------------------------------------------------------- #
# Bench perplexity
# --------------------------------------------------------------------------- #

def bench_perplexity(nickname: str, model_id: str, niche: str) -> str:
    """Lance mlx_lm.perplexity sur une niche locale."""
    data_path = NICHES_DIR / niche
    header = f"\n--- {nickname} / ppl-{niche} ---\n"

    if not data_path.exists():
        return header + f"_NO DATASET at {data_path}_\n"

    cmd = [
        MLX_PERPLEXITY,
        "--model", model_id,
        "--data-path", str(data_path),
        "--num-samples", str(PPL_NUM_SAMPLES),
        "--sequence-length", str(PPL_SEQ_LEN),
        "--seed", "0",
    ]

    rc, stdout, stderr = run(cmd, PPL_TIMEOUT)

    if rc == 124:
        return header + f"_TIMEOUT after {PPL_TIMEOUT}s_\n"

    # mlx_lm.perplexity imprime "Perplexity: X.XXX ± Y.YYY"
    ppl_line = next(
        (ln for ln in stdout.splitlines() if ln.strip().startswith("Perplexity:")),
        None,
    )
    if ppl_line is None:
        # Parfois sur stderr
        ppl_line = next(
            (ln for ln in stderr.splitlines() if ln.strip().startswith("Perplexity:")),
            None,
        )

    if ppl_line is None:
        log(f"FAIL on {nickname}/ppl-{niche} (rc={rc}) — stderr tail:")
        log(stderr[-500:])
        return header + f"_NO RESULT (rc={rc})_\n"

    return header + ppl_line.strip() + "\n"


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    log(f"=== bench_new_models start (PID {os.getpid()}) ===")
    log(f"all_models.txt = {ALL_MODELS_TXT}")
    log(f"models = {[n for n, _ in MODELS]}")

    for nickname, model_id in MODELS:
        log(f"\n############ MODEL: {nickname} ({model_id}) ############")
        section_header = f"\n=== {nickname} ===\n"
        append_result(section_header)

        # 1) lm-eval tasks
        for task in LM_TASKS:
            chunk = bench_lm_task(nickname, model_id, task)
            append_result(chunk)
            log(f"appended {nickname}/{task}")

        # 2) perplexity niches
        for niche in NICHES:
            chunk = bench_perplexity(nickname, model_id, niche)
            append_result(chunk)
            log(f"appended {nickname}/ppl-{niche}")

        log(f"=== done {nickname} ===")

    log("=== bench_new_models END ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
