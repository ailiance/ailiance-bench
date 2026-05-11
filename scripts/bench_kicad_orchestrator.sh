#!/usr/bin/env bash
# bench_kicad_orchestrator.sh — Phase 1 KiCad functional bench.
#
# Sequence :
#   1. Attend la fin du job persist 'bench31' (perplexity baseline).
#   2. Sleep 30s (marge GPU release).
#   3. Lance python ~/scripts/bench_kicad_functional.py.
#
# Lance via :
#   source ~/scripts/lib_persist.sh
#   persist_run kicad_phase1 "bash ~/scripts/bench_kicad_orchestrator.sh"
#
# Bash 3.2 compat (macOS).

set -uo pipefail
source "$HOME/scripts/lib_persist.sh"

PYBIN="$HOME/mlx-stack/.venv/bin/python"
SCRIPT="$HOME/scripts/bench_kicad_functional.py"
WAIT_JOB="bench31"

echo "[orch] start $(date) pid=$$"
echo "[orch] PYBIN=$PYBIN"
echo "[orch] SCRIPT=$SCRIPT"

# --- 1. wait for bench31 ---
echo "[orch] waiting for persist job '$WAIT_JOB' ..."
persist_wait "$WAIT_JOB" 60
echo "[orch] '$WAIT_JOB' finished — $(persist_status "$WAIT_JOB")"

# --- 2. GPU release margin ---
echo "[orch] sleep 30s for GPU release ..."
sleep 30

# --- 3. sanity ---
if [ ! -x "$PYBIN" ]; then
  echo "[orch] FATAL: python venv introuvable: $PYBIN"
  exit 2
fi
if [ ! -f "$SCRIPT" ]; then
  echo "[orch] FATAL: script introuvable: $SCRIPT"
  exit 2
fi

# --- 4. launch bench (logs go to caller persist log) ---
echo "[orch] launching bench at $(date)"
"$PYBIN" "$SCRIPT"
RC=$?
echo "[orch] bench exit=$RC at $(date)"
exit $RC
