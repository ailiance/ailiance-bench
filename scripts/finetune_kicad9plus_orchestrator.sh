#!/usr/bin/env bash
# Wrapper : convert dataset -> mlx_lm.lora training.
# Bash 3.2 compat. Idempotent : skip convert si {train,valid,test}.jsonl deja la.

set -uo pipefail

VENV_PYTHON="/Users/electron/mlx-stack/.venv/bin/python"
DATA_DIR="$HOME/lora-data-kicad9plus"

echo "=== finetune_kicad9plus_orchestrator start $(date) ==="

# Step 1 : convert (skip si deja fait)
if [ -f "$DATA_DIR/train.jsonl" ] && [ -f "$DATA_DIR/valid.jsonl" ] && [ -f "$DATA_DIR/test.jsonl" ]; then
  echo "[1/2] dataset already converted -> $DATA_DIR (skip)"
  for split in train valid test; do
    n=$(wc -l < "$DATA_DIR/$split.jsonl" | xargs)
    echo "      $split.jsonl : $n samples"
  done
else
  echo "[1/2] converting kicad9plus-permissive -> $DATA_DIR"
  "$VENV_PYTHON" "$HOME/scripts/convert_kicad9plus_for_lora.py" --out-dir "$DATA_DIR"
  rc=$?
  if [ $rc -ne 0 ]; then
    echo "FATAL: convert step failed rc=$rc"
    exit $rc
  fi
fi

# Step 2 : LoRA training
echo "[2/2] launching LoRA training"
bash "$HOME/scripts/finetune_gemma_kicad9plus.sh"
rc=$?
echo "=== finetune_kicad9plus_orchestrator end rc=$rc $(date) ==="
exit $rc
