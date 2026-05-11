#!/usr/bin/env bash
# Pipeline data-only: Phases 2 → 3 → 4 (no HF write needed).
# Phase 1 + Phase 5 require a write token and are skipped — run kicad9plus_pipeline_ship.sh
# once the HF token has 'write' role.
set -u
START=$(date -u +%s)
echo "================================================================"
echo "=== KiCad 9+ DATA pipeline (P2-P3-P4) START $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "================================================================"

set +e
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

END=$(date -u +%s)
DUR=$((END - START))
echo "================================================================"
echo "=== DATA pipeline DONE $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "=== rc: P2=$P2 P3=$P3 P4=$P4  duration=${DUR}s ==="
echo "=== Next step: provision HF write token, then run:"
echo "===   bash ~/scripts/kicad9plus_pipeline_ship.sh"
echo "================================================================"
