#!/usr/bin/env bash
# bench_lora_orchestrator.sh — Phase 1 LORA KiCad functional bench.
#
# Sequence :
#   1. (Optionnel) attend la fin d'un job persist nomme par WAIT_JOB env (default: aucun).
#   2. Sleep 30s (marge GPU release) si on a attendu un job.
#   3. Lance python ~/scripts/bench_kicad_lora.py.
#
# Lance via :
#   source ~/scripts/lib_persist.sh
#   persist_run lora_phase1 "bash ~/scripts/bench_lora_orchestrator.sh"
#
# Variables d'env optionnelles :
#   WAIT_JOB="kicad_phase4"      # nom de job persist a attendre avant de demarrer
#   LORA_MODELS="gemma-e4b-eukiki-final gemma-e4b-mascarade-final"
#   LORA_DATASETS="kicad-dsl kicad-pcb spice-sim"
#   LORA_NSAMPLES="20"
#   LORA_DRY_RUN="1"             # si non vide, lance --dry-run
#
# Bash 3.2 compat (macOS) — pas de declare -A, pas de mapfile.

set -uo pipefail

source "$HOME/scripts/lib_persist.sh"

PYBIN="${PYBIN:-$HOME/mlx-stack/.venv/bin/python}"
SCRIPT="${SCRIPT:-$HOME/scripts/bench_kicad_lora.py}"
WAIT_JOB="${WAIT_JOB:-}"
LORA_MODELS="${LORA_MODELS:-}"
LORA_DATASETS="${LORA_DATASETS:-}"
LORA_NSAMPLES="${LORA_NSAMPLES:-20}"
LORA_DRY_RUN="${LORA_DRY_RUN:-}"

echo "[orch-lora] start $(date) pid=$$"
echo "[orch-lora] PYBIN=$PYBIN"
echo "[orch-lora] SCRIPT=$SCRIPT"
echo "[orch-lora] WAIT_JOB=${WAIT_JOB:-<none>}"
echo "[orch-lora] LORA_MODELS=${LORA_MODELS:-<all>}"
echo "[orch-lora] LORA_DATASETS=${LORA_DATASETS:-<all>}"
echo "[orch-lora] LORA_NSAMPLES=$LORA_NSAMPLES"
echo "[orch-lora] LORA_DRY_RUN=${LORA_DRY_RUN:-<no>}"

# --- 1. wait (optional) ---
if [ -n "$WAIT_JOB" ]; then
  echo "[orch-lora] waiting for persist job '$WAIT_JOB' ..."
  persist_wait "$WAIT_JOB" 60
  echo "[orch-lora] '$WAIT_JOB' finished — $(persist_status "$WAIT_JOB" 2>/dev/null || echo 'no status')"
  echo "[orch-lora] sleep 30s for GPU release ..."
  sleep 30
fi

# --- 2. sanity ---
if [ ! -x "$PYBIN" ]; then
  echo "[orch-lora] FATAL: python venv introuvable: $PYBIN"
  exit 2
fi
if [ ! -f "$SCRIPT" ]; then
  echo "[orch-lora] FATAL: script introuvable: $SCRIPT"
  exit 2
fi

# --- 3. construct args (Bash 3.2 : pas de array indirect, on construit a la main) ---
ARGS=""
ARGS="$ARGS --n-samples $LORA_NSAMPLES"
if [ -n "$LORA_MODELS" ]; then
  ARGS="$ARGS --models $LORA_MODELS"
fi
if [ -n "$LORA_DATASETS" ]; then
  ARGS="$ARGS --datasets $LORA_DATASETS"
fi
if [ -n "$LORA_DRY_RUN" ]; then
  ARGS="$ARGS --dry-run"
fi

# --- 4. launch bench (logs go to caller persist log) ---
echo "[orch-lora] launching: $PYBIN $SCRIPT $ARGS"
echo "[orch-lora] start at $(date)"
# shellcheck disable=SC2086
"$PYBIN" "$SCRIPT" $ARGS
RC=$?
echo "[orch-lora] bench exit=$RC at $(date)"
exit $RC
