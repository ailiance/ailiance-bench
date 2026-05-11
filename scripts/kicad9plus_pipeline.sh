#!/usr/bin/env bash
# Master pipeline — exécute Phases 1→5 séquentiellement
set -u
LOG=~/bench-results/kicad9plus_pipeline.log
START=$(date -u +%s)

echo "================================================================"
echo "=== KiCad 9+ pipeline START $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "================================================================"

set +e
echo ">>> PHASE 1 — license fixes"
bash ~/scripts/kicad9plus_phase1_licenses.sh
P1=$?
echo ">>> PHASE 1 rc=$P1"

echo ">>> PHASE 2 — download corpus"
bash ~/scripts/kicad9plus_phase2_download.sh
P2=$?
echo ">>> PHASE 2 rc=$P2"

echo ">>> PHASE 3 — filter + ERC validation"
bash ~/scripts/kicad9plus_phase3_filter.sh
P3=$?
echo ">>> PHASE 3 rc=$P3"

echo ">>> PHASE 4 — build dataset.jsonl"
python3 ~/scripts/build_kicad9plus_dataset.py
P4=$?
echo ">>> PHASE 4 rc=$P4"

if [ "$P4" -eq 0 ]; then
  echo ">>> PHASE 5 — upload HF"
  bash ~/scripts/kicad9plus_phase5_upload.sh
  P5=$?
  echo ">>> PHASE 5 rc=$P5"
else
  echo ">>> PHASE 5 — SKIPPED (Phase 4 failed)"
  P5=99
fi

END=$(date -u +%s)
DUR=$((END - START))
echo "================================================================"
echo "=== KiCad 9+ pipeline DONE  $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "=== Phase rc: 1=$P1 2=$P2 3=$P3 4=$P4 5=$P5  duration=${DUR}s ==="
echo "================================================================"
