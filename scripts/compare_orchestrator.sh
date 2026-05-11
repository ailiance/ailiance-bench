#!/usr/bin/env bash
# compare_orchestrator.sh — Phase 5 (ERC delta) + compare_base_vs_lora.
#
# Sequence :
#   1. persist_wait lora_phase234   (attend la fin des LoRA P2/3/4)
#   2. sleep 30  (marge GPU release / fs sync)
#   3. python bench_kicad_phase5.py     (re-score base + lora si dispo)
#   4. sleep 10
#   5. python compare_base_vs_lora.py    (matrice de lift)
#
# Lance via :
#   source ~/scripts/lib_persist.sh
#   persist_run compare_lift "bash ~/scripts/compare_orchestrator.sh"
#
# Bash 3.2 compat (macOS) — pas de declare -A, pas de mapfile.

set -uo pipefail

# shellcheck source=/dev/null
source "$HOME/scripts/lib_persist.sh"

PYBIN="${PYBIN:-$HOME/mlx-stack/.venv/bin/python}"
WAIT_JOB="${WAIT_JOB:-lora_phase234}"

echo "[orch-compare] start $(date) pid=$$"
echo "[orch-compare] PYBIN=$PYBIN"
echo "[orch-compare] WAIT_JOB=$WAIT_JOB"

# --- 1. wait LoRA P2/3/4 ---
if [ -n "$WAIT_JOB" ]; then
  echo "[orch-compare] persist_wait $WAIT_JOB ..."
  persist_wait "$WAIT_JOB" 60
  echo "[orch-compare] $WAIT_JOB done — $(persist_status "$WAIT_JOB" 2>/dev/null || echo 'no status')"
  echo "[orch-compare] sleep 30s for GPU/fs release ..."
  sleep 30
fi

# --- 2. sanity ---
if [ ! -x "$PYBIN" ]; then
  echo "[orch-compare] FATAL: python venv introuvable: $PYBIN"
  exit 2
fi
PHASE5_SCRIPT="$HOME/scripts/bench_kicad_phase5.py"
COMPARE_SCRIPT="$HOME/scripts/compare_base_vs_lora.py"
for s in "$PHASE5_SCRIPT" "$COMPARE_SCRIPT"; do
  if [ ! -f "$s" ]; then
    echo "[orch-compare] FATAL: script introuvable: $s"
    exit 2
  fi
done

# --- 3. Phase 5 : ERC delta sur base + lora ---
echo "[orch-compare] === PHASE 5 (ERC delta vs ref) ==="
echo "[orch-compare] launching: $PYBIN $PHASE5_SCRIPT"
"$PYBIN" "$PHASE5_SCRIPT"
RC5=$?
echo "[orch-compare] phase5 exit=$RC5 at $(date)"

sleep 10

# --- 4. Compare base vs LoRA ---
echo "[orch-compare] === COMPARE BASE vs LORA ==="
echo "[orch-compare] launching: $PYBIN $COMPARE_SCRIPT"
"$PYBIN" "$COMPARE_SCRIPT"
RC_C=$?
echo "[orch-compare] compare exit=$RC_C at $(date)"

echo "[orch-compare] all done $(date) (rc5=$RC5 rc_compare=$RC_C)"
exit $RC_C
