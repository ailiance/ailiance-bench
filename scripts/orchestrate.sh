#!/usr/bin/env bash
# orchestrate.sh — orchestrateur générique : attend N jobs persistents puis enchaîne une commande.
# Usage :
#   bash ~/scripts/orchestrate.sh "after:job1,job2" "command to run"
#   bash ~/scripts/orchestrate.sh "after:" "command"   # pas d'attente, exec direct
#
# Doit être lancé via persist_run pour survivre à la session :
#   source ~/scripts/lib_persist.sh
#   persist_run myorch "bash ~/scripts/orchestrate.sh after:job1,job2 'final-command'"

set -uo pipefail
source /Users/electron/scripts/lib_persist.sh

DEPS_SPEC="${1:-after:}"
shift || true
CMD="$*"

DEPS="${DEPS_SPEC#after:}"

echo "[orchestrate] start $(date)"
echo "[orchestrate] waiting for: $DEPS"
echo "[orchestrate] then run: $CMD"

# Attendre chaque dépendance (séparées par virgule)
if [ -n "$DEPS" ]; then
  IFS=','
  for dep in $DEPS; do
    dep=$(echo "$dep" | xargs)  # trim
    [ -z "$dep" ] && continue
    echo "[orchestrate] waiting on job '$dep'..."
    persist_wait "$dep" 30
    echo "[orchestrate] '$dep' done — $(persist_status "$dep")"
  done
  unset IFS
fi

sleep 5  # marge GPU release
echo "[orchestrate] launching final command at $(date)"
eval "$CMD"
RC=$?
echo "[orchestrate] final command exit=$RC at $(date)"
exit $RC
