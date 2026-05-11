#!/usr/bin/env bash
# kill_mlx_servers_before_granite30b.sh
# Surveille le log bench31 et tue les serveurs MLX gemma (eu-kiki + mascarade)
# quand granite-4.1-3b commence — pour libérer ~12 Go RAM avant que bench
# attaque granite-4.1-30b (17 Go en 4-bit) sur cette machine 32 Go.
#
# Sans ce nettoyage : 17 Go (granite 30b) + 12 Go (2 serveurs gemma) = 29 Go,
# marge ultra-serrée vs 32 Go physique → risque OOM élevé.
#
# Usage : persist_run kill_mlx_pre_granite "bash ~/scripts/kill_mlx_servers_before_granite30b.sh"

set -uo pipefail

LOG=$(ls -t ~/logs/bench31-*.log 2>/dev/null | head -1)
if [ -z "$LOG" ]; then
  echo "ERREUR: aucun log bench31-*.log trouvé"
  exit 1
fi

echo "[$(date)] watching $LOG"
echo "[$(date)] trigger : ligne mentionnant 'granite-4.1-3b' (premier granite, juste avant le 30B)"

# PIDs des serveurs à killer (eu-kiki port 8502, mascarade port 8503)
# On résout dynamiquement pour gérer le cas où ils auraient été restartés
TRIGGER_PATTERN="granite-4.1-3b"

while true; do
  # Détecter quand granite-4.1-3b est mentionné dans le log
  # (soit en début de section "MODEL: granite-4.1-3b", soit "-> granite-4.1-3b /")
  if grep -qE "MODEL: $TRIGGER_PATTERN|-> $TRIGGER_PATTERN /" "$LOG" 2>/dev/null; then
    echo "[$(date)] granite-4.1-3b détecté dans le log — kill serveurs MLX gemma"

    # Trouver les PIDs des serveurs MLX gemma (eu-kiki + mascarade)
    PIDS=$(pgrep -f "mlx_lm.server.*gemma4-e4b-(eukiki|mascarade)" 2>/dev/null | head -10)
    if [ -z "$PIDS" ]; then
      echo "[$(date)] aucun serveur MLX gemma actif (peut-être déjà killés)"
    else
      for pid in $PIDS; do
        cmd=$(ps -p $pid -o command= 2>/dev/null | head -1 | awk -F'adapter-path' '{print $2}' | awk '{print $1}')
        if kill $pid 2>/dev/null; then
          echo "[$(date)] killed PID $pid (adapter: $cmd)"
        else
          echo "[$(date)] échec kill PID $pid"
        fi
      done
      sleep 5
      # Verif kill OK, sinon kill -9
      for pid in $PIDS; do
        if kill -0 $pid 2>/dev/null; then
          echo "[$(date)] kill -9 sur PID $pid (résistant)"
          kill -9 $pid 2>/dev/null
        fi
      done
    fi

    # Mémoire libérée
    sleep 3
    USED_GB=$(vm_stat | awk '/Pages active/{a=$3} /Pages wired down/{w=$4} END{printf "%.1f", (a+w)*4096/1024/1024/1024}')
    echo "[$(date)] mémoire RAM utilisée après kill: ${USED_GB} Go (sur 32 Go)"
    echo "[$(date)] === fin watcher (granite-30b devrait avoir la marge nécessaire) ==="
    exit 0
  fi
  sleep 60
done
