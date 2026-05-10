#!/usr/bin/env bash
# Wrapper qui attend la fin du pipeline post_fork (PID dans bench-results/post_fork.pid)
# puis lance bench_31_domains_base.py (10 modèles × 31 domaines, perplexité).
# ETA total ~7h45.
set -uo pipefail

LOG=~/logs/bench31-orchestrator-$(date +%Y%m%d-%H%M%S).log
exec > >(tee -a "$LOG") 2>&1

echo "=== bench31 orchestrator start $(date) ==="

# 1. Wait for post_fork pipeline
PIPE_PID=$(cat ~/bench-results/post_fork.pid 2>/dev/null || echo 0)
if [ "$PIPE_PID" != "0" ]; then
  echo "[1/2] Waiting for post_fork pipeline PID $PIPE_PID"
  while kill -0 "$PIPE_PID" 2>/dev/null; do sleep 60; done
  echo "[1/2] Pipeline finished at $(date)"
fi
sleep 10  # marge GPU release

# 2. Lancer bench 31 domaines
echo "[2/2] Lancement bench_31_domains_base.py"
BENCH_LOG=~/logs/bench-31-domains-$(date +%Y%m%d-%H%M%S).log
echo "  bench log: $BENCH_LOG"
echo "$$" > ~/bench-results/bench31.pid
/Users/electron/mlx-stack/.venv/bin/python ~/scripts/bench_31_domains_base.py > "$BENCH_LOG" 2>&1
RC=$?
echo "[2/2] bench_31_domains_base.py exit=$RC at $(date)"
rm -f ~/bench-results/bench31.pid

echo "=== bench31 orchestrator end $(date) ==="
