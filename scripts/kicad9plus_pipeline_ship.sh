#!/usr/bin/env bash
# Pipeline SHIP: Phases 1 + 5 only (HF uploads).
# Run AFTER provisioning a write-scope HF token at ~/.cache/huggingface/token.
# Verifies write rights first; aborts if token is read-only.
set -u
START=$(date -u +%s)
echo "================================================================"
echo "=== KiCad 9+ SHIP pipeline (P1+P5) START $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "================================================================"

TOKEN=$(cat ~/.cache/huggingface/token)
ROLE=$(curl -sH "Authorization: Bearer $TOKEN" "https://huggingface.co/api/whoami-v2" \
  | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('auth',{}).get('accessToken',{}).get('role','?'))")
echo "[ship] HF token role: $ROLE"
if [ "$ROLE" != "write" ] && [ "$ROLE" != "fineGrained" ]; then
  echo "[ship] ABORT: token role is '$ROLE', need 'write'."
  echo "[ship] Generate a write token at https://huggingface.co/settings/tokens"
  echo "[ship] then: echo 'hf_xxx...' > ~/.cache/huggingface/token"
  exit 2
fi

set +e
echo ">>> PHASE 1 — license fixes on existing datasets"
bash ~/scripts/kicad9plus_phase1_licenses.sh
P1=$?
echo ">>> PHASE 1 rc=$P1"

echo ">>> PHASE 5 — upload kicad9plus dataset"
bash ~/scripts/kicad9plus_phase5_upload.sh
P5=$?
echo ">>> PHASE 5 rc=$P5"

END=$(date -u +%s)
DUR=$((END - START))
echo "================================================================"
echo "=== SHIP pipeline DONE $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "=== rc: P1=$P1 P5=$P5  duration=${DUR}s ==="
echo "================================================================"
