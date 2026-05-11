#!/usr/bin/env bash
# bench_lora_phase234_orchestrator.sh — chaine Phase 2/3/4 LORA apres lora_phase1.
# Bash 3.2 compat (macOS).
set -uo pipefail

# shellcheck source=/dev/null
source ~/scripts/lib_persist.sh

echo "[orch234-lora] start $(date)"
echo "[orch234-lora] waiting for lora_phase1..."
persist_wait lora_phase1 30
echo "[orch234-lora] lora_phase1 done — sleeping 30s for GPU release"
sleep 30

VENV=/Users/electron/mlx-stack/.venv/bin/python

echo "[orch234-lora] === PHASE 2 LORA (gen .kicad_sch) ==="
$VENV ~/scripts/bench_kicad_lora_phase2.py
RC2=$?
echo "[orch234-lora] phase2 lora exit=$RC2 at $(date)"

sleep 30
echo "[orch234-lora] === PHASE 3 LORA (extraction inverse) ==="
$VENV ~/scripts/bench_kicad_lora_phase3.py
RC3=$?
echo "[orch234-lora] phase3 lora exit=$RC3 at $(date)"

sleep 30
echo "[orch234-lora] === PHASE 4 LORA (ERC kicad-cli) ==="
$VENV ~/scripts/bench_kicad_lora_phase4.py
RC4=$?
echo "[orch234-lora] phase4 lora exit=$RC4 at $(date)"

echo "[orch234-lora] all done $(date) (rc2=$RC2 rc3=$RC3 rc4=$RC4)"
