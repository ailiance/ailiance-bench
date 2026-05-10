#!/usr/bin/env bash
# dl_hf_models.sh — télécharge une liste de repos HF de façon idempotente.
# Skip ce qui est déjà présent dans ~/.cache/huggingface/hub.
# Utilise le token configuré dans ~/.cache/huggingface/token.
#
# Usage :
#   bash ~/scripts/dl_hf_models.sh repo1 repo2 repo3 ...
# OU lecture depuis stdin :
#   echo -e "repo1\nrepo2" | bash ~/scripts/dl_hf_models.sh

set -uo pipefail

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

echo "[dl_hf_models] start $(date) — ${#REPOS[@]} repo(s)"

for repo in "${REPOS[@]}"; do
  cache_name="models--${repo//\//--}"
  cache_dir="$HOME/.cache/huggingface/hub/$cache_name"

  # Idempotence : si le dossier snapshots/ a au moins 1 entrée non-vide, considère DL fait
  if [ -d "$cache_dir/snapshots" ]; then
    snap=$(ls "$cache_dir/snapshots" 2>/dev/null | head -1)
    if [ -n "$snap" ] && [ -d "$cache_dir/snapshots/$snap" ]; then
      have_files=$(ls "$cache_dir/snapshots/$snap" 2>/dev/null | wc -l | xargs)
      if [ "$have_files" -gt 0 ]; then
        sz=$(du -sh "$cache_dir" 2>/dev/null | cut -f1)
        echo "[SKIP] $repo (déjà présent, $sz)"
        continue
      fi
    fi
  fi

  echo "[DL] $repo"
  if "$HF" download "$repo" 2>&1 | tail -3; then
    sz=$(du -sh "$cache_dir" 2>/dev/null | cut -f1)
    echo "[OK]   $repo  ($sz)"
  else
    echo "[FAIL] $repo"
  fi
done

echo "[dl_hf_models] end $(date)"
