#!/usr/bin/env bash
# bench_kicad9plus_lora_full.sh
# ---------------------------------------------------------------------------
# Bench complet du LoRA gemma4-e4b-kicad9plus-final (fine-tune sur
# kicad9plus-permissive) sur toutes les phases (1..6) + regen compare matrix.
#
# Strategie :
#   1. Attendre fin de phase6_full (qui inclut le fine-tune kicad9plus)
#   2. Verifier que ~/lora-adapters/gemma4-e4b-kicad9plus/final/ existe
#   3. Phase 1 LoRA  -> bench_kicad_lora.py --models gemma-e4b-kicad9plus-final
#   4. Phase 2 LoRA  -> bench_kicad_lora_phase2.py --models gemma-e4b-kicad9plus-final
#   5. Phase 3 LoRA  -> bench_kicad_lora_phase3.py --models gemma-e4b-kicad9plus-final
#   6. Phase 4 LoRA  -> bench_kicad_lora_phase4.py --models gemma-e4b-kicad9plus-final
#   7. Phase 5       -> bench_kicad_phase5.py (re-score delta — base + lora)
#   8. Phase 6 compl -> bench_kicad_phase6_completion.py --models gemma-e4b-kicad9plus-final
#   9. compare_base_vs_lora.py (regen matrix)
#
# Compatible Bash 3.2 macOS.
# ---------------------------------------------------------------------------

set -uo pipefail
source ~/scripts/lib_persist.sh

TS=$(date +%Y%m%d-%H%M%S)
LOG="$HOME/logs/bench_kicad9plus_lora_full-${TS}.log"
exec > >(tee -a "$LOG") 2>&1

echo "=== bench kicad9plus LoRA full pipeline start $(date) ==="
echo "  log : $LOG"

# --- 1. Attendre fin de phase6_full ----------------------------------------
echo ""
echo "[wait] waiting for phase6_full to complete (poll 60s)..."
persist_wait phase6_full 60
echo "[wait] phase6_full done at $(date)"

# --- 2. Verifier que le LoRA est bien cree ---------------------------------
ADAPTER="$HOME/lora-adapters/gemma4-e4b-kicad9plus/final"
if [ ! -d "$ADAPTER" ]; then
  echo "[ERR] LoRA adapter directory absent : $ADAPTER"
  echo "[ERR] phase6_full may have failed during fine-tune step"
  echo "[ERR] check ~/logs/phase6_full-*.log"
  exit 1
fi

# adapter_config.json + adapters.safetensors expected
if [ ! -f "$ADAPTER/adapter_config.json" ] || [ ! -f "$ADAPTER/adapters.safetensors" ]; then
  echo "[ERR] LoRA adapter incomplete at $ADAPTER"
  echo "[ERR] missing adapter_config.json or adapters.safetensors"
  ls -la "$ADAPTER" || true
  exit 1
fi

echo "[ok] adapter found and complete: $ADAPTER"
ls -la "$ADAPTER"

# Note : si fine-tune produit un LoRA cassé (poids degeneres), le bench tourne
# quand meme — on observe simplement composite faible.

echo ""
echo "[gpu] sleeping 30s to let GPU release from phase6_full..."
sleep 30

# --- venv MLX --------------------------------------------------------------
VENV="$HOME/mlx-stack/.venv/bin/python"
if [ ! -x "$VENV" ]; then
  echo "[ERR] venv python not executable: $VENV"
  exit 2
fi
echo "[venv] $VENV"

NICK="gemma-e4b-kicad9plus-final"

# --- 3. Phase 1 LoRA -------------------------------------------------------
echo ""
echo "############################################################"
echo "[1/6] Phase 1 LoRA (kicad-dsl + kicad-pcb + spice-sim)  $(date)"
echo "############################################################"
"$VENV" "$HOME/scripts/bench_kicad_lora.py" --models "$NICK" \
  || echo "[WARN] P1 returned rc=$?"

sleep 20

# --- 4. Phase 2 LoRA -------------------------------------------------------
echo ""
echo "############################################################"
echo "[2/6] Phase 2 LoRA (gen .kicad_sch full)  $(date)"
echo "############################################################"
"$VENV" "$HOME/scripts/bench_kicad_lora_phase2.py" --models "$NICK" \
  || echo "[WARN] P2 returned rc=$?"

sleep 20

# --- 5. Phase 3 LoRA -------------------------------------------------------
echo ""
echo "############################################################"
echo "[3/6] Phase 3 LoRA (extraction inverse sch->JSON)  $(date)"
echo "############################################################"
"$VENV" "$HOME/scripts/bench_kicad_lora_phase3.py" --models "$NICK" \
  || echo "[WARN] P3 returned rc=$?"

sleep 20

# --- 6. Phase 4 LoRA -------------------------------------------------------
echo ""
echo "############################################################"
echo "[4/6] Phase 4 LoRA (ERC kicad-cli sur sch Phase 2)  $(date)"
echo "############################################################"
"$VENV" "$HOME/scripts/bench_kicad_lora_phase4.py" --models "$NICK" \
  || echo "[WARN] P4 returned rc=$?"

sleep 20

# --- 7. Phase 5 (re-score delta — base + lora) -----------------------------
# Phase 5 ne prend pas --models : elle re-score TOUT depuis phase4*.json
# C'est intentionnel (delta vs ref invariant par modele).
echo ""
echo "############################################################"
echo "[5/6] Phase 5 (ERC delta re-scoring base + lora)  $(date)"
echo "############################################################"
"$VENV" "$HOME/scripts/bench_kicad_phase5.py" \
  || echo "[WARN] P5 returned rc=$?"

sleep 20

# --- 8. Phase 6 completion (prefix header) ---------------------------------
echo ""
echo "############################################################"
echo "[6/6] Phase 6 completion (prefixe header)  $(date)"
echo "############################################################"
"$VENV" "$HOME/scripts/bench_kicad_phase6_completion.py" --models "$NICK" \
  || echo "[WARN] P6 returned rc=$?"

sleep 20

# --- 9. Regen compare matrix -----------------------------------------------
echo ""
echo "############################################################"
echo "[final] Regen compare_base_vs_lora.md  $(date)"
echo "############################################################"
"$VENV" "$HOME/scripts/compare_base_vs_lora.py" \
  || echo "[WARN] compare returned rc=$?"

echo ""
echo "=== bench kicad9plus LoRA full pipeline end $(date) ==="
echo "  outputs :"
echo "    ~/bench-results/kicad_functional_phase1_lora.json"
echo "    ~/bench-results/kicad_phase2_lora.json"
echo "    ~/bench-results/kicad_phase3_lora.json"
echo "    ~/bench-results/kicad_phase4_lora.json"
echo "    ~/bench-results/kicad_phase5_lora.json"
echo "    ~/bench-results/kicad_phase6_completion.json"
echo "    ~/bench-results/compare_base_vs_lora.md"
echo "  log : $LOG"
