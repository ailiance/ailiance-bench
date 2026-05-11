#!/bin/bash
# Upload enriched JSONLs + updated READMEs to HF, both org mirrors.
# Args: list of dataset short-names (power|dsp|emc|kicad).
# Reads HF token from ~/.cache/huggingface/token.
set -u

if [ "$#" -lt 1 ]; then
  echo "usage: $0 <ds1> [ds2] ..." >&2
  exit 1
fi

TOKEN=$(cat ~/.cache/huggingface/token)
export HF_TOKEN="$TOKEN"
HF=/Users/electron/mlx-stack/.venv/bin/hf
ED=/Users/electron/eu-kiki-data
RD=$ED/readme-rendered

for ds in "$@"; do
  case "$ds" in
    power|dsp|emc|kicad) ;;
    *) echo "[err] unknown dataset: $ds (must be power|dsp|emc|kicad)"; continue;;
  esac

  jsonl_local="$ED/${ds}_chat_enriched.jsonl"
  if [ ! -f "$jsonl_local" ]; then
    echo "[err] missing $jsonl_local"; continue
  fi
  remote_jsonl="${ds}_chat.jsonl"

  for org in electron-rare Ailiance-fr; do
    repo="$org/mascarade-${ds}-dataset"
    readme_local="$RD/${org}__${ds}.md"
    if [ ! -f "$readme_local" ]; then
      echo "[err] missing $readme_local"; continue
    fi
    echo "=== uploading $repo ==="
    # JSONL
    "$HF" upload "$repo" "$jsonl_local" "$remote_jsonl" --repo-type dataset \
      --commit-message "SE attribution audit ${ds}: per-sample metadata.stack_exchange_attribution + attribution_recovery markers" 2>&1 | tail -6
    sleep 2
    # README
    "$HF" upload "$repo" "$readme_local" README.md --repo-type dataset \
      --commit-message "SE attribution audit ${ds}: replace ~30% banner with audited numbers" 2>&1 | tail -6
    sleep 2
  done
done

echo "[done]"
