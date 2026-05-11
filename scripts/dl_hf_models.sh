#!/usr/bin/env bash
# dl_hf_models.sh — télécharge une liste de repos HF de façon idempotente.
# Utilise hf_transfer (multi-thread Rust) pour accélérer x5-10.
# `hf download` est nativement idempotent : reprend où il s'est arrêté.
#
# Usage :
#   bash ~/scripts/dl_hf_models.sh repo1 repo2 repo3 ...
# OU lecture depuis stdin :
#   echo -e "repo1\nrepo2" | bash ~/scripts/dl_hf_models.sh

set -uo pipefail

# Activation accélérateur Rust multi-thread (x5-10 vs python natif)
export HF_HUB_ENABLE_HF_TRANSFER=1

VENV=/Users/electron/mlx-stack/.venv
HF=$VENV/bin/hf

if [ $# -eq 0 ]; then
  REPOS=()
  while IFS= read -r line; do
    [ -n "$line" ] && REPOS+=("$line")
  done
else
  REPOS=("$@")
fi

echo "[dl_hf_models] start $(date) — ${#REPOS[@]} repo(s) — HF_TRANSFER=on"

for repo in "${REPOS[@]}"; do
  echo ""
  echo "[DL] $repo @ $(date +%H:%M:%S)"
  cache_name="models--${repo//\//--}"
  cache_dir="$HOME/.cache/huggingface/hub/$cache_name"

  if "$HF" download "$repo" 2>&1 | tail -5; then
    sz=$(du -sh "$cache_dir" 2>/dev/null | cut -f1)
    echo "[OK]   $repo  ($sz) @ $(date +%H:%M:%S)"
  else
    echo "[FAIL] $repo @ $(date +%H:%M:%S)"
  fi
done

echo ""
echo "[dl_hf_models] end $(date)"
