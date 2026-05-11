#!/usr/bin/env bash
# bench_kicad_phase23_orchestrator.sh — chained Phase 2 + Phase 3.
#
# Sequence :
#   1. Wait for kicad_phase1 (functional bench DSL+PCB+SPICE) to finish.
#   2. Sleep 30s for GPU/RAM release.
#   3. Run python bench_kicad_phase2.py (sch generation).
#   4. Sleep 30s.
#   5. Run python bench_kicad_phase3.py (sch -> JSON extraction).
#
# Launch via :
#   source ~/scripts/lib_persist.sh
#   persist_run kicad_phase23 "bash ~/scripts/bench_kicad_phase23_orchestrator.sh"
#
# Bash 3.2 compat (macOS).

set -uo pipefail
source "$HOME/scripts/lib_persist.sh"

PYBIN="$HOME/mlx-stack/.venv/bin/python"
SCRIPT2="$HOME/scripts/bench_kicad_phase2.py"
SCRIPT3="$HOME/scripts/bench_kicad_phase3.py"
WAIT_JOB="kicad_phase1"

echo "[orch23] start $(date) pid=$$"
echo "[orch23] PYBIN=$PYBIN"
echo "[orch23] SCRIPT2=$SCRIPT2"
echo "[orch23] SCRIPT3=$SCRIPT3"

# --- 1. wait for phase1 ---
echo "[orch23] waiting for persist job '$WAIT_JOB' ..."
persist_wait "$WAIT_JOB" 60
echo "[orch23] '$WAIT_JOB' finished — $(persist_status "$WAIT_JOB")"

# --- 2. GPU release margin ---
echo "[orch23] sleep 30s for GPU release ..."
sleep 30

# --- sanity ---
if [ ! -x "$PYBIN" ]; then
  echo "[orch23] FATAL: python venv introuvable: $PYBIN"
  exit 2
fi
if [ ! -f "$SCRIPT2" ]; then
  echo "[orch23] FATAL: script Phase 2 introuvable: $SCRIPT2"
  exit 2
fi
if [ ! -f "$SCRIPT3" ]; then
  echo "[orch23] FATAL: script Phase 3 introuvable: $SCRIPT3"
  exit 2
fi

# --- 3. Phase 2 ---
echo "[orch23] === launching Phase 2 at $(date) ==="
"$PYBIN" "$SCRIPT2"
RC2=$?
echo "[orch23] Phase 2 exit=$RC2 at $(date)"

# --- 4. inter-phase margin ---
echo "[orch23] sleep 30s before Phase 3 ..."
sleep 30

# --- 5. Phase 3 ---
echo "[orch23] === launching Phase 3 at $(date) ==="
"$PYBIN" "$SCRIPT3"
RC3=$?
echo "[orch23] Phase 3 exit=$RC3 at $(date)"

# Compose final rc : 0 si tout ok, sinon le 1er rc non-nul
if [ "$RC2" -ne 0 ]; then
  exit "$RC2"
fi
exit "$RC3"
