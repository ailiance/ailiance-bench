#!/usr/bin/env bash
# Orchestrateur Phase 6 FULL — chaine sequentielle des 3 recommandations.
# Bash 3.2 compat. Lance via persist_run pour survivre au shell parent.
#
# Sequence :
#   [1/3] reco #26 — completion PURE 14b/30b   (~1-2h)
#   [2/3] reco #24 — task completion prefix    (~3-4h)
#   [3/3] reco #25 — fine-tune gemma kicad9plus (~6h GPU)

set -uo pipefail
source "$HOME/scripts/lib_persist.sh"

LOG="$HOME/logs/phase6_full-$(date +%Y%m%d-%H%M%S).log"
mkdir -p "$HOME/logs"
exec > >(tee -a "$LOG") 2>&1

VENV_PYTHON="/Users/electron/mlx-stack/.venv/bin/python"

echo "=== Phase 6 FULL pipeline start $(date) ==="
echo "Log : $LOG"

echo ""
echo "[1/3] reco #26 — completion PURE ministral-14b/granite-30b"
"$VENV_PYTHON" "$HOME/scripts/bench_kicad_phase6_completion_pure.py"
rc1=$?
echo "[1/3] done rc=$rc1 $(date)"

sleep 30
echo ""
echo "[2/3] reco #24 — task completion prefix header (10 modeles)"
"$VENV_PYTHON" "$HOME/scripts/bench_kicad_phase6_completion.py"
rc2=$?
echo "[2/3] done rc=$rc2 $(date)"

sleep 30
echo ""
echo "[3/3] reco #25 — fine-tune gemma-e4b sur kicad9plus-permissive"
bash "$HOME/scripts/finetune_kicad9plus_orchestrator.sh"
rc3=$?
echo "[3/3] done rc=$rc3 $(date)"

echo ""
echo "=== Phase 6 FULL pipeline end $(date) ==="
echo "Final rc summary: reco26=$rc1 reco24=$rc2 reco25=$rc3"

# Exit non-zero si une etape a echoue
if [ $rc1 -ne 0 ] || [ $rc2 -ne 0 ] || [ $rc3 -ne 0 ]; then
  exit 1
fi
exit 0
