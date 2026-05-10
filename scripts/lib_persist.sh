#!/usr/bin/env bash
# lib_persist.sh — primitives pour lancer un job vraiment détaché du shell parent.
# Compatible Bash 3.2 macOS (pas de declare -A, pas de mapfile).
#
# Usage :
#   source ~/scripts/lib_persist.sh
#   persist_run <job_name> <command>
#
# Effets :
#   - log : ~/logs/<job_name>-<ts>.log (auto-créé)
#   - pid : ~/bench-results/<job_name>.pid (PID du job détaché)
#   - status : ~/bench-results/<job_name>.status (rc final écrit par trap EXIT)
#   - stdout/stderr du job redirigés vers le log
#   - le job survit à la fermeture du shell parent (setsid + disown)

mkdir -p "$HOME/logs" "$HOME/bench-results"

persist_run() {
  local name="$1"; shift
  local ts log pid_file status_file
  ts=$(date +%Y%m%d-%H%M%S)
  log="$HOME/logs/${name}-${ts}.log"
  pid_file="$HOME/bench-results/${name}.pid"
  status_file="$HOME/bench-results/${name}.status"

  # Wrapper qui écrit son rc final dans status_file via trap EXIT.
  # nohup + disown + redirect </dev/null suffisent sur macOS pour survivre au shell parent.
  nohup bash -c "
    trap 'echo \"\$? @ \$(date)\" > '\"$status_file\"'' EXIT
    echo \"=== persist_run [$name] start \$(date) pid=\$\$ ===\"
    $*
  " < /dev/null > "$log" 2>&1 &

  local pid=$!
  disown $pid 2>/dev/null || true
  echo "$pid" > "$pid_file"
  echo "name=$name pid=$pid log=$log status=$status_file"
}

persist_alive() {
  local name="$1"
  local pid_file="$HOME/bench-results/${name}.pid"
  [ -f "$pid_file" ] || return 1
  local pid; pid=$(cat "$pid_file")
  kill -0 "$pid" 2>/dev/null
}

persist_wait() {
  # Attend qu'un job nommé soit terminé (poll 30s par défaut)
  local name="$1"; local sleep_s="${2:-30}"
  local pid_file="$HOME/bench-results/${name}.pid"
  [ -f "$pid_file" ] || return 0  # rien à attendre
  local pid; pid=$(cat "$pid_file")
  while kill -0 "$pid" 2>/dev/null; do sleep "$sleep_s"; done
}

persist_status() {
  # Affiche état d'un job : alive/dead, etime, rc si fini
  local name="$1"
  local pid_file="$HOME/bench-results/${name}.pid"
  local status_file="$HOME/bench-results/${name}.status"
  if [ ! -f "$pid_file" ]; then echo "$name: NEVER STARTED"; return; fi
  local pid; pid=$(cat "$pid_file")
  if kill -0 "$pid" 2>/dev/null; then
    local etime; etime=$(ps -o etime= -p "$pid" 2>/dev/null | xargs)
    echo "$name: ALIVE pid=$pid etime=$etime"
  else
    if [ -f "$status_file" ]; then
      echo "$name: DEAD $(cat "$status_file")"
    else
      echo "$name: DEAD (no status file — may have been killed)"
    fi
  fi
}
