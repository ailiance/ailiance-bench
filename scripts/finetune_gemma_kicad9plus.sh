#!/usr/bin/env bash
# Fine-tune LoRA gemma-4-E4B sur kicad9plus-permissive (98 samples MIT/Apache/CC0).
# Config alignee sur ailiance existant : rank=32, scale=2.0 (lora_parameters defaults
# mlx_lm si pas de YAML), num_layers=16, lr=1e-5, batch=1, max_seq=4096.
#
# Bash 3.2 compat strict. Source: persist via wrapper.

set -uo pipefail

VENV_BIN="/Users/electron/mlx-stack/.venv/bin"
MLX_LM="$VENV_BIN/mlx_lm"
DATA_DIR="$HOME/lora-data-kicad9plus"
ADAPTER_DIR="$HOME/lora-adapters/gemma4-e4b-kicad9plus/final"
BASE_MODEL="lmstudio-community/gemma-4-E4B-it-MLX-4bit"

mkdir -p "$ADAPTER_DIR"

echo "=== finetune_gemma_kicad9plus start $(date) ==="
echo "VENV     : $VENV_BIN"
echo "BASE     : $BASE_MODEL"
echo "DATA     : $DATA_DIR"
echo "ADAPTER  : $ADAPTER_DIR"

# Sanity : data files exist
for split in train valid test; do
  f="$DATA_DIR/$split.jsonl"
  if [ ! -f "$f" ]; then
    echo "FATAL: missing $f — run convert_kicad9plus_for_lora.py first"
    exit 2
  fi
  n=$(wc -l < "$f" | xargs)
  echo "  $split.jsonl : $n samples"
done

echo "Starting mlx_lm lora training ..."
"$MLX_LM" lora \
  --model "$BASE_MODEL" \
  --train \
  --data "$DATA_DIR" \
  --fine-tune-type lora \
  --iters 1200 \
  --batch-size 1 \
  --num-layers 16 \
  --learning-rate 1e-5 \
  --max-seq-length 4096 \
  --adapter-path "$ADAPTER_DIR" \
  --steps-per-report 50 \
  --steps-per-eval 200 \
  --val-batches 10 \
  --save-every 200 \
  --grad-checkpoint
rc=$?
echo "=== mlx_lm lora rc=$rc ==="

if [ $rc -eq 0 ] && [ -f "$ADAPTER_DIR/adapters.safetensors" ]; then
  echo "Adapter saved successfully:"
  ls -la "$ADAPTER_DIR" | head -20
fi

echo "=== finetune_gemma_kicad9plus end $(date) ==="
exit $rc
