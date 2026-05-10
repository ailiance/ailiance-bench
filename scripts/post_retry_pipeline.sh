#!/usr/bin/env bash
# post_retry_pipeline.sh
# Pipeline auto enchaînée après la fin du bench_oom_retry :
#   1. attendre la fin du retry (PID dans ~/bench-results/bench_retry.pid)
#   2. installer le wheel mlx fork
#   3. redémarrer les 2 serveurs mlx_lm.server (eukiki 8502, mascarade 8503)
#   4. relancer gsm8k_cot ministral-3-8b 8-shot pour tester le fix OOM Metal
#
# Pas de `set -e` : on veut continuer même si une étape échoue.

set -uo pipefail

LOG=~/logs/post-retry-pipeline-$(date +%Y%m%d-%H%M%S).log
exec > >(tee -a "$LOG") 2>&1

echo "=== post_retry_pipeline start $(date) ==="
echo "PID self=$$  log=$LOG"

# ---------------------------------------------------------------------------
# 1. Attendre fin du retry
# ---------------------------------------------------------------------------
RETRY_PID=$(cat ~/bench-results/bench_retry.pid 2>/dev/null || echo 0)
if [ "$RETRY_PID" != "0" ] && [ -n "$RETRY_PID" ]; then
  echo "[1/4] Waiting for retry PID $RETRY_PID to finish..."
  while kill -0 "$RETRY_PID" 2>/dev/null; do
    sleep 30
  done
  echo "[1/4] Retry finished at $(date)"
else
  echo "[1/4] No retry PID found, skipping wait."
fi
sleep 5  # marge pour flush logs

# ---------------------------------------------------------------------------
# 2. Install wheel mlx fork
# ---------------------------------------------------------------------------
WHEEL=~/Downloads/mlx-wheels/mlx-0.32.0.dev20260510+eaa16e95-cp312-cp312-macosx_26_0_arm64.whl
echo ""
echo "[2/4] Install wheel: $WHEEL"
if [ -f "$WHEEL" ]; then
  VIRTUAL_ENV=~/mlx-stack/.venv /opt/homebrew/bin/uv pip install \
    --python ~/mlx-stack/.venv/bin/python \
    --reinstall "$WHEEL" \
    || echo "[2/4] INSTALL FAILED (continuing)"
  ~/mlx-stack/.venv/bin/python -c \
    "import mlx, mlx.core as mx; print('mlx ok ->', mlx.__file__); print('dev_info:', mx.metal.device_info() if hasattr(mx, 'metal') else 'n/a')" \
    || echo "[2/4] SMOKE TEST FAILED (continuing)"
else
  echo "[2/4] WHEEL NOT FOUND: $WHEEL — skip install"
fi

# ---------------------------------------------------------------------------
# 3. Restart servers (kill + relaunch via start scripts)
#    Match sur adapter-path car le tag ne figure pas dans le binaire mlx_lm.server.
# ---------------------------------------------------------------------------
echo ""
echo "[3/4] Restart MLX servers"
declare -A SCRIPTS
SCRIPTS[eukiki]=~/mlx-stack/bin/start-gemma4-e4b-eukiki.sh
SCRIPTS[mascarade]=~/mlx-stack/bin/start-gemma4-e4b-mascarade.sh

for srv in eukiki mascarade; do
  echo ""
  echo "  --- $srv ---"
  # match sur 'gemma4-e4b-<srv>' qui apparaît dans --adapter-path
  pids=$(pgrep -f "mlx_lm.server.*gemma4-e4b-${srv}" || true)
  for pid in $pids; do
    echo "  Killing $srv server PID $pid"
    kill "$pid" 2>/dev/null
  done
  if [ -n "$pids" ]; then
    sleep 3
    for pid in $pids; do
      kill -9 "$pid" 2>/dev/null && echo "  SIGKILL on $pid"
    done
  fi

  SCRIPT="${SCRIPTS[$srv]}"
  if [ -f "$SCRIPT" ]; then
    SRV_LOG=~/logs/mlx-server-${srv}-$(date +%Y%m%d-%H%M%S).log
    echo "  Restarting $srv via $SCRIPT (log $SRV_LOG)"
    nohup bash "$SCRIPT" > "$SRV_LOG" 2>&1 &
    NEW_PID=$!
    echo "  Started: PID=$NEW_PID"
    echo "$NEW_PID" > ~/logs/gemma4-${srv}-restarted.pid
  else
    echo "  WARNING: start script for $srv not found ($SCRIPT)"
  fi
done

echo ""
echo "[3/4] Waiting 10s for servers to come up..."
sleep 10

# ---------------------------------------------------------------------------
# 4. Re-test gsm8k_cot ministral-3-8b 8-shot (config originale qui OOM)
# ---------------------------------------------------------------------------
echo ""
echo "[4/4] TEST: ministral-3-8b/gsm8k_cot 8-shot avec wheel fork"
OUT=~/bench-results/ministral-3-8b-gsm8k_cot-fork
mkdir -p "$OUT"
{
  echo ""
  echo "=== POST-FORK TEST (mlx wheel metal-1.5x-buffer-limit-32gb) ==="
  echo "--- ministral-3-8b / gsm8k_cot (8-shot, fork) ---"
} >> ~/bench-results/all_models.txt

timeout 1500 ~/mlx-stack/.venv/bin/mlx_lm.evaluate \
  --model mlx-community/Ministral-3-8B-Instruct-2512-4bit \
  --tasks gsm8k_cot \
  --output-dir "$OUT" \
  --num-shots 8 \
  --limit 100 \
  --seed 0 2>&1 | tee /tmp/ministral-fork-test.log
RC=${PIPESTATUS[0]}
echo "[4/4] mlx_lm.evaluate RC=$RC"

if [ -f "$OUT/results.json" ]; then
  ~/mlx-stack/.venv/bin/python -c \
    "import json; d=json.load(open('$OUT/results.json')); print(json.dumps(d.get('results', {}).get('gsm8k_cot', {}), indent=2))" \
    >> ~/bench-results/all_models.txt
  echo "[4/4] FORK TEST: SUCCESS — gsm8k_cot completed without OOM"
else
  echo "_NO RESULT (rc=$RC, check log)_" >> ~/bench-results/all_models.txt
  echo "[4/4] FORK TEST: FAILED (rc=$RC) — check /tmp/ministral-fork-test.log"
fi

echo ""
echo "=== post_retry_pipeline end $(date) ==="
