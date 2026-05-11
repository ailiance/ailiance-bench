#!/usr/bin/env bash
# Wait for Phase 7 to finish, then run iact-bench Phase 8 on the 5 orphan LoRA.

set -uo pipefail
PHASE7_LOG="/tmp/phase7_outer.log"
PHASE8_LOG="/tmp/phase8_outer.log"

echo "=== phase8 chainer started $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$PHASE8_LOG"

# Poll until Phase 7 wrote its "=== phase7 finished" footer.
while ! grep -q "=== phase7 finished" "$PHASE7_LOG" 2>/dev/null; do
    sleep 60
    if ! pgrep -lf 'wait_phase7\|bench_phase7_cuda' > /dev/null; then
        if grep -q "=== phase7 finished" "$PHASE7_LOG" 2>/dev/null; then
            break
        fi
        echo "  phase7 chainer gone without footer, aborting" | tee -a "$PHASE8_LOG"
        tail -10 "$PHASE7_LOG" >> "$PHASE8_LOG"
        exit 1
    fi
done

echo "=== phase7 done at $(date -u +%Y-%m-%dT%H:%M:%SZ), starting Phase 8 ===" | tee -a "$PHASE8_LOG"

cd "$HOME/ailiance-models-tuning" || exit 1
source .venv/bin/activate || exit 1

# Verify Docker images are pulled on electron-server (via ssh)
ssh electron-server 'docker images 2>&1 | grep -cE "iact-bench-(embedded|platformio|freecad|kicad)"' >> "$PHASE8_LOG" 2>&1 || true

echo "" | tee -a "$PHASE8_LOG"
echo "=== bench_phase8_iact.py start $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$PHASE8_LOG"
python /tmp/bench_phase8_iact.py --n-samples 10 --update-cards 2>&1 | tee -a "$PHASE8_LOG"
RC=$?
echo "=== phase8 finished rc=$RC at $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$PHASE8_LOG"
exit $RC
