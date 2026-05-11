#!/usr/bin/env bash
# post_fork_pipeline.sh
# Pipeline auto enchaine apres la fin du test fork ministral :
#   1. attendre la fin du test fork ministral (PID dans ~/bench-results/fork_test.pid)
#   2. lancer bench_fork_retry.py (qwen3.5-9b + helium-1-2b avec wheel fork)
#   3. regenerer ~/bench-results/BENCH_TABLE.md
#   4. sync vers ~/ailiance-bench/, commit + push
#
# Compatible Bash 3.2 macOS : pas de `declare -A`, pas d'arrays associatifs,
# juste des variables simples ou des boucles.

set -uo pipefail

LOG=~/logs/post-fork-pipeline-$(date +%Y%m%d-%H%M%S).log
exec > >(tee -a "$LOG") 2>&1

echo "=== post_fork_pipeline start $(date) ==="
echo "PID self=$$  log=$LOG"

# ---------------------------------------------------------------------------
# 1. Wait for current fork test (ministral)
# ---------------------------------------------------------------------------
TEST_PID=$(cat ~/bench-results/fork_test.pid 2>/dev/null || echo 0)
if [ "$TEST_PID" != "0" ] && [ -n "$TEST_PID" ]; then
  echo "[1/4] Waiting for fork test PID $TEST_PID"
  while kill -0 "$TEST_PID" 2>/dev/null; do
    sleep 30
  done
  echo "[1/4] Fork test done at $(date)"
else
  echo "[1/4] No fork test PID found, skipping wait."
fi
sleep 5

# ---------------------------------------------------------------------------
# 2. Bench fork retry (qwen + helium)
# ---------------------------------------------------------------------------
echo ""
echo "[2/4] Lancement bench_fork_retry.py"
/Users/electron/mlx-stack/.venv/bin/python ~/scripts/bench_fork_retry.py
RC_BENCH=$?
echo "[2/4] bench_fork_retry.py done (rc=$RC_BENCH)"

# ---------------------------------------------------------------------------
# 3. Regen BENCH_TABLE.md
# ---------------------------------------------------------------------------
echo ""
echo "[3/4] Regen BENCH_TABLE.md"
/Users/electron/mlx-stack/.venv/bin/python ~/scripts/regen_bench_table.py
RC_REGEN=$?
echo "[3/4] regen_bench_table.py done (rc=$RC_REGEN)"

# ---------------------------------------------------------------------------
# 4. Sync to ~/ailiance-bench/ and commit/push
# ---------------------------------------------------------------------------
echo ""
echo "[4/4] Sync ailiance-bench repo + commit + push"

mkdir -p ~/ailiance-bench/scripts ~/ailiance-bench/bench-results

cp ~/scripts/bench_new_models.py     ~/ailiance-bench/scripts/ 2>/dev/null || echo "  (skip bench_new_models.py)"
cp ~/scripts/bench_oom_retry.py      ~/ailiance-bench/scripts/ 2>/dev/null || echo "  (skip bench_oom_retry.py)"
cp ~/scripts/bench_fork_retry.py     ~/ailiance-bench/scripts/ 2>/dev/null || echo "  (skip bench_fork_retry.py)"
cp ~/scripts/regen_bench_table.py    ~/ailiance-bench/scripts/ 2>/dev/null || echo "  (skip regen_bench_table.py)"
cp ~/scripts/post_fork_pipeline.sh   ~/ailiance-bench/scripts/ 2>/dev/null || echo "  (skip post_fork_pipeline.sh)"
cp ~/bench-results/BENCH_TABLE.md    ~/ailiance-bench/bench-results/ 2>/dev/null || echo "  (skip BENCH_TABLE.md)"
cp ~/bench-results/all_models.txt    ~/ailiance-bench/bench-results/ 2>/dev/null || echo "  (skip all_models.txt)"

cd ~/ailiance-bench || { echo "[4/4] FATAL: cannot cd to ~/ailiance-bench"; exit 0; }
git add scripts/ bench-results/ 2>&1 || echo "  (git add a echoue)"

if git diff --cached --quiet; then
  echo "Pas de changements a commiter"
else
  echo "Creating commit..."
  git -c user.email=108685187+electron-rare@users.noreply.github.com \
      -c user.name="electron-rare" \
      commit -m "feat: bench fork mlx (wheel +eaa16e95, patch iogpu.rsrc_limit 1.5x)

- Retest qwen3.5-9b et helium-1-2b avec mlx fork (pas de timeout/NO_RESULT)
- Test ministral-3-8b/gsm8k_cot 8-shot fix l'OOM Metal originel
- Ajout scripts bench_oom_retry.py, bench_fork_retry.py, post_fork_pipeline.sh
- Mise a jour BENCH_TABLE.md avec marqueurs (fork) et (kvq8)" 2>&1 \
    || { echo "[4/4] commit failed (continuing)"; }

  echo "Pushing to origin main..."
  git push origin main 2>&1 \
    && echo "Push OK: $(git log -1 --oneline)" \
    || echo "[4/4] push failed (continuing) — verifie auth ou conflit"
fi

echo ""
echo "=== post_fork_pipeline end $(date) ==="
