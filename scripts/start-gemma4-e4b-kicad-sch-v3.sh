#!/usr/bin/env bash
# start-gemma4-e4b-kicad-sch-v3.sh
# Lance un mlx_lm.server pour le LoRA kicad-sch-v3 sur un port libre.
# Bash 3.2 compatible (macOS default).
#
# Variables d'env :
#   PORT       : port d'ecoute (defaut 8504)
#   ADAPTER    : chemin adapter (defaut ~/lora-adapters/gemma4-e4b-kicad-sch-v3/final)
#   MODEL      : modele de base (defaut lmstudio-community/gemma-4-E4B-it-MLX-4bit)
#   HOST       : host bind (defaut 127.0.0.1)
#   LOG_DIR    : dossier logs (defaut ~/logs)

set -u

PORT="${PORT:-8504}"
HOST="${HOST:-127.0.0.1}"
MODEL="${MODEL:-lmstudio-community/gemma-4-E4B-it-MLX-4bit}"
ADAPTER="${ADAPTER:-$HOME/lora-adapters/gemma4-e4b-kicad-sch-v3/final}"
LOG_DIR="${LOG_DIR:-$HOME/logs}"

if [ ! -d "$ADAPTER" ]; then
  echo "ERROR: adapter not found at $ADAPTER" >&2
  echo "       set ADAPTER=/path/to/adapter to override" >&2
  exit 2
fi

# Refuse de lancer si un server tourne deja sur ce port (safety vs OOM)
if lsof -i ":$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
  EXISTING_PID=$(lsof -i ":$PORT" -sTCP:LISTEN -t 2>/dev/null | head -n1)
  echo "ERROR: port $PORT already in use (pid $EXISTING_PID)" >&2
  echo "       pick another with PORT=85xx $0" >&2
  exit 3
fi

mkdir -p "$LOG_DIR"
TS=$(date +%Y%m%d-%H%M%S)
LOG="$LOG_DIR/mlx_server_kicad-sch-v3_${PORT}_${TS}.log"

echo "Starting mlx_lm.server"
echo "  model   : $MODEL"
echo "  adapter : $ADAPTER"
echo "  bind    : $HOST:$PORT"
echo "  log     : $LOG"

nohup mlx_lm.server \
  --model "$MODEL" \
  --adapter-path "$ADAPTER" \
  --host "$HOST" \
  --port "$PORT" \
  --log-level INFO \
  > "$LOG" 2>&1 &
PID=$!
disown $PID 2>/dev/null || true

echo "PID=$PID"
echo "  to stop : kill $PID"
echo "  to test : curl -s http://$HOST:$PORT/v1/models | head"
