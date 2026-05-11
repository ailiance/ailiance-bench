#!/usr/bin/env bash
# bench_kicad_phase4_orchestrator.sh — attend Phase 2/3 puis lance ERC reel.
#
# Sequence :
#   1. Wait for kicad_phase23 (gen sch + extract) to finish.
#   2. Sleep 30s pour laisser GPU/RAM se relacher.
#   3. Verifie que ~/bench-results/kicad_phase2.json existe.
#   4. Run python bench_kicad_phase4.py (ERC via kicad-cli).
#
# Launch via :
#   source ~/scripts/lib_persist.sh
#   persist_run kicad_phase4 "bash ~/scripts/bench_kicad_phase4_orchestrator.sh"
#
# Bash 3.2 compat (macOS, pas de declare -A, pas de mapfile).

set -uo pipefail
source "$HOME/scripts/lib_persist.sh"

PYBIN="$HOME/mlx-stack/.venv/bin/python"
SCRIPT4="$HOME/scripts/bench_kicad_phase4.py"
WAIT_JOB="kicad_phase23"
PHASE2_JSON="$HOME/bench-results/kicad_phase2.json"

echo "[orch4] start $(date) pid=$$"
echo "[orch4] PYBIN=$PYBIN"
echo "[orch4] SCRIPT4=$SCRIPT4"
echo "[orch4] WAIT_JOB=$WAIT_JOB"

# --- 1. wait for phase23 (Phase 2 generates phase2.json) ---
echo "[orch4] waiting for persist job '$WAIT_JOB' ..."
persist_wait "$WAIT_JOB" 60
echo "[orch4] '$WAIT_JOB' finished — $(persist_status "$WAIT_JOB")"

# --- 2. GPU release margin ---
echo "[orch4] sleep 30s for GPU/RAM release ..."
sleep 30

# --- sanity ---
if [ ! -x "$PYBIN" ]; then
  echo "[orch4] FATAL: python venv introuvable: $PYBIN"
  exit 2
fi
if [ ! -f "$SCRIPT4" ]; then
  echo "[orch4] FATAL: script Phase 4 introuvable: $SCRIPT4"
  exit 2
fi
if [ ! -f "$PHASE2_JSON" ]; then
  echo "[orch4] FATAL: phase2.json absent: $PHASE2_JSON"
  echo "[orch4] -> Phase 2 a probablement echoue ; rien a scorer."
  exit 3
fi

# --- 3. Phase 4 ---
echo "[orch4] === launching Phase 4 at $(date) ==="
"$PYBIN" "$SCRIPT4"
RC4=$?
echo "[orch4] Phase 4 exit=$RC4 at $(date)"

exit "$RC4"
