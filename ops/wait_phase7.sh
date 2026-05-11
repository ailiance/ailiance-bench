#!/usr/bin/env bash
# Wait for eval_mascarade_lora (the first chainer) to finish, then run
# Phase 7 CUDA bench on the 10 LoRA and update model cards.

set -uo pipefail

EVAL_LOG="/tmp/eval_mascarade_outer.log"
PHASE7_LOG="/tmp/phase7_outer.log"

echo "=== phase7 chainer started $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$PHASE7_LOG"

# Poll until the eval chainer wrote its "=== eval finished" footer.
while ! grep -q "=== eval finished" "$EVAL_LOG" 2>/dev/null; do
    sleep 60
    # Sanity: if both retry+eval are gone but no footer, abort.
    if ! pgrep -lf 'wait_and_eval\|eval_mascarade_lora\|ship_qwen3_mascarade_retry' > /dev/null; then
        if grep -q "=== eval finished" "$EVAL_LOG" 2>/dev/null; then
            break
        fi
        echo "  upstream chainer gone without footer — checking tail:" | tee -a "$PHASE7_LOG"
        tail -10 "$EVAL_LOG" >> "$PHASE7_LOG"
        echo "  aborting phase7 (no eval to chain from)" | tee -a "$PHASE7_LOG"
        exit 1
    fi
done

echo "=== eval finished at $(date -u +%Y-%m-%dT%H:%M:%SZ), starting Phase 7 ===" | tee -a "$PHASE7_LOG"

cd "$HOME/ailiance-models-tuning" || exit 1
source .venv/bin/activate || exit 1

# Install peft if missing (was in deps but verify).
python -c "import peft" 2>/dev/null || pip install -q peft

echo "" | tee -a "$PHASE7_LOG"
echo "=== bench_phase7_cuda.py start $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$PHASE7_LOG"
python /tmp/bench_phase7_cuda.py --n-samples 10 --update-cards 2>&1 | tee -a "$PHASE7_LOG"
RC=$?
echo "=== phase7 finished rc=$RC at $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$PHASE7_LOG"
exit $RC
