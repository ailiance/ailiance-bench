#!/usr/bin/env bash
# Orchestrateur v2 — bench 31 domaines × 8 modeles EU AI Act compatibles.
#
# Sequence :
#   1. Attend la fin du pipeline post_fork PID 27019.
#   2. Attend la fin des downloads (PID dans bench-results/dl_eu_models.pid).
#   3. Sleep 10s (marge GPU release).
#   4. Lance bench_31_domains_base.py et logue vers bench-31-domains-<ts>.log.
#
# Bash 3.2 compat (pas de declare -A).
set -uo pipefail

LOG="$HOME/logs/bench31-orchestrator-v2-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

PIPELINE_PID=27019
DL_PID_FILE="$HOME/bench-results/dl_eu_models.pid"
BENCH_SCRIPT="$HOME/scripts/bench_31_domains_base.py"
PYBIN="/Users/electron/mlx-stack/.venv/bin/python"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

log "=== bench31 orchestrator v2 START (pid $$) ==="
echo "$$" > "$HOME/bench-results/bench31_orchestrator.pid"

# --- 1. Wait for post_fork pipeline ---
log "[1/4] Waiting for post_fork pipeline PID $PIPELINE_PID"
if kill -0 "$PIPELINE_PID" 2>/dev/null; then
  while kill -0 "$PIPELINE_PID" 2>/dev/null; do
    sleep 60
  done
  log "[1/4] Pipeline PID $PIPELINE_PID finished."
else
  log "[1/4] Pipeline PID $PIPELINE_PID not running, skipping wait."
fi

# --- 2. Wait for downloads ---
if [ -f "$DL_PID_FILE" ]; then
  DL_PID=$(cat "$DL_PID_FILE" 2>/dev/null || echo "")
  if [ -n "$DL_PID" ] && kill -0 "$DL_PID" 2>/dev/null; then
    log "[2/4] Waiting for download PID $DL_PID"
    while kill -0 "$DL_PID" 2>/dev/null; do
      sleep 30
    done
    log "[2/4] Download PID $DL_PID finished."
  else
    log "[2/4] Download PID '$DL_PID' not running, skipping wait."
  fi
else
  log "[2/4] No download PID file, skipping wait."
fi

# --- 3. GPU release margin ---
log "[3/4] Sleep 10s (GPU release margin)"
sleep 10

# --- 4. Launch bench ---
BENCH_LOG="$HOME/logs/bench-31-domains-$(date +%Y%m%d-%H%M%S).log"
log "[4/4] Launching bench_31_domains_base.py"
log "      bench log: $BENCH_LOG"
"$PYBIN" "$BENCH_SCRIPT" > "$BENCH_LOG" 2>&1
RC=$?
log "[4/4] bench_31_domains_base.py exit=$RC"

rm -f "$HOME/bench-results/bench31_orchestrator.pid"
log "=== bench31 orchestrator v2 END (rc=$RC) ==="
exit $RC
