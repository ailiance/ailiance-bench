#!/usr/bin/env bash
# Phase 5 — Create HF dataset repo + upload dataset.jsonl + LICENSE_INVENTORY.md + README.md
set -u
ROOT=~/ailiance-data/kicad9plus-corpus
LOG=~/bench-results/kicad9plus-upload.log
REPO="electron-rare/kicad9plus-sch-corpus"

export HF_TOKEN=$(cat ~/.cache/huggingface/token)
export HUGGING_FACE_HUB_TOKEN="$HF_TOKEN"

echo "=== Phase 5 upload start $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$LOG"

# 1. Create repo (idempotent — succeed if already exists)
hf repo create "$REPO" --repo-type dataset 2>&1 | tee -a "$LOG" || \
  echo "[create] repo may already exist — continuing" | tee -a "$LOG"

# 2. Build README.md (dataset card)
N_SAMPLES=$(wc -l < "$ROOT/dataset.jsonl" | xargs)
SIZE_CAT="1K<n<10K"
[ "$N_SAMPLES" -lt 1000 ] && SIZE_CAT="n<1K"
[ "$N_SAMPLES" -ge 10000 ] && SIZE_CAT="10K<n<100K"

# License distribution from stats.json
LIC_TABLE=$(python3 -c "
import json
d = json.load(open('$ROOT/stats.json'))
for lic, count in sorted(d['license_distribution'].items(), key=lambda x:-x[1]):
    print(f'| {lic} | {count} |')
")
TOP_REPOS=$(python3 -c "
import json
d = json.load(open('$ROOT/stats.json'))
for repo, count in d['top_repos'].items():
    print(f'| \`{repo}\` | {count} |')
" | head -15)

cat > "$ROOT/README.md" <<EOF
---
license: cc-by-sa-4.0
language:
- en
pretty_name: KiCad 9+ Schematic Corpus
task_categories:
- text-generation
tags:
- kicad
- eda
- schematic
- s-expression
- electronics
size_categories:
- $SIZE_CAT
---

# KiCad 9+ Schematic Corpus

A curated dataset of **${N_SAMPLES}** real-world \`.kicad_sch\` files in the
KiCad 9+ S-expression format (file format version >= **20240722**, including
KiCad 10 strict files at version **20260306**). Designed for fine-tuning LLMs
on EDA tasks: schematic generation, completion, parsing, and analysis.

## Dataset structure

Each line of \`dataset.jsonl\` is a chat-formatted training sample:

\`\`\`json
{
  "messages": [
    {"role": "user", "content": "Generate a KiCad 10 schematic (...hint...)."},
    {"role": "assistant", "content": "(kicad_sch (version 20260306) ...)"}
  ],
  "metadata": {
    "source_url": "https://github.com/owner/repo/blob/COMMIT/path.kicad_sch",
    "license_spdx": "MIT",
    "commit_sha": "abc123...",
    "kicad_version": "20260306",
    "repo": "owner/repo",
    "rel_path": "path/to/file.kicad_sch",
    "file_size_bytes": 4523,
    "file_sha256": "...",
    "ia_act_status": "compliant",
    "compliance_notes": "permissive license (MIT), public repo, attribution required",
    "downloaded_at": "2026-05-11T05:30:00Z"
  }
}
\`\`\`

## Method

1. \`gh search code\` for \`(kicad_sch (version >= 20240722)\` across GitHub
2. Sparse-clone repos with permissive (MIT/Apache/BSD/MPL) and copyleft (GPL/LGPL/CERN-OHL) licenses
3. Filter by KiCad file format version (>= 20240722)
4. Validate with \`kicad-cli sch erc\` (parse-OK; ERC violations are kept as feature signal)
5. De-duplicate via SHA-256
6. Truncate file content to 8 KB to fit context windows

## License distribution

| License | Sample count |
|---|---|
$LIC_TABLE

## Top source repositories

| Repository | Sample count |
|---|---|
$TOP_REPOS

## License — CC-BY-SA-4.0

This dataset is released under **Creative Commons Attribution-ShareAlike 4.0
International** (CC-BY-SA-4.0). It aggregates content from upstream repositories
under multiple licenses (MIT, Apache-2.0, BSD, MPL-2.0, GPL, LGPL, CERN-OHL).

CC-BY-SA-4.0 is chosen because:
- Compatible with all upstream permissive licenses via attribution
- Compatible with copyleft via reciprocal share-alike
- Aligns with **GPAI Code of Practice (August 2025)** transparency expectations

**Per-sample license is preserved in \`metadata.license_spdx\`**, and the
upstream commit SHA + source URL is in \`metadata.source_url\` for full
traceability.

See \`LICENSE_INVENTORY.md\` for a full per-sample license inventory.

## EU AI Act compliance

This dataset is built to support GPAI providers' transparency and copyright
obligations under the EU AI Act:

- **Provenance**: every sample carries the upstream commit SHA, repo, and source URL
- **License chain**: per-sample SPDX identifier preserved
- **Public-data only**: only public GitHub repos with declared licenses included
- **Opt-out respected**: dataset will be updated if upstream rights-holders request removal
- **Risk class**: low — public technical artefacts (electronics CAD files)
- **Filter exclusions**: PROPRIETARY/UNKNOWN-license files excluded by default

## Citation

\`\`\`bibtex
@dataset{electron_rare_kicad9plus_2026,
  author       = {Electron Rare contributors},
  title        = {KiCad 9+ Schematic Corpus},
  year         = {2026},
  publisher    = {Hugging Face},
  url          = {https://huggingface.co/datasets/electron-rare/kicad9plus-sch-corpus}
}
\`\`\`

Upstream KiCad source files are subject to their original licenses; please
honor attribution and share-alike when applicable. See \`metadata\` per-sample.

## Contact

Electron Rare — \`clemsail\` on Hugging Face / \`electron-rare\` on GitHub.

To request take-down of any sample under your copyright, open an issue on the
dataset repo with the \`metadata.source_url\`.
EOF

# 3. Upload artifacts (idempotent)
for f in dataset.jsonl LICENSE_INVENTORY.md README.md stats.json; do
  src="$ROOT/$f"
  if [ -f "$src" ]; then
    echo "[upload] $f ($(du -h "$src" | awk '{print $1}'))" | tee -a "$LOG"
    hf upload "$REPO" "$src" "$f" --repo-type dataset \
      --commit-message "Upload $f (Phase 5 pipeline)" >> "$LOG" 2>&1 || \
      echo "[upload] $f FAILED" | tee -a "$LOG"
  fi
done

echo "[upload] Repo URL: https://huggingface.co/datasets/$REPO" | tee -a "$LOG"
echo "=== Phase 5 done $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$LOG"
