#!/usr/bin/env bash
# Wait for Phase 8 to finish, then run baseline + cross-domain forgetting matrix.

set -uo pipefail
PHASE8_LOG="/tmp/phase8_outer.log"
PHASE9_LOG="/tmp/phase9_outer.log"

echo "=== phase9 chainer started $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$PHASE9_LOG"

while ! grep -q "=== phase8 finished" "$PHASE8_LOG" 2>/dev/null; do
    sleep 60
    if ! pgrep -lf 'wait_phase8\|bench_phase8_iact' > /dev/null; then
        if grep -q "=== phase8 finished" "$PHASE8_LOG" 2>/dev/null; then
            break
        fi
        echo "  phase8 chainer gone without footer, aborting" | tee -a "$PHASE9_LOG"
        tail -10 "$PHASE8_LOG" >> "$PHASE9_LOG"
        exit 1
    fi
done

echo "=== phase8 done at $(date -u +%Y-%m-%dT%H:%M:%SZ), starting Phase 9 ===" | tee -a "$PHASE9_LOG"

cd "$HOME/ailiance-models-tuning" || exit 1
source .venv/bin/activate || exit 1

echo "" | tee -a "$PHASE9_LOG"
echo "=== bench_phase9_baseline_forgetting.py start $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$PHASE9_LOG"
python /tmp/bench_phase9_baseline_forgetting.py --n-samples 5 --update-cards 2>&1 | tee -a "$PHASE9_LOG"
RC=$?
echo "=== phase9 finished rc=$RC at $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$PHASE9_LOG"
exit $RC
