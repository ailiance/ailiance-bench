#!/usr/bin/env bash
# Phase 3 — Filter (version >= 20240722) + ERC validation via kicad-cli
set -u
ROOT=~/ailiance-data/kicad9plus-corpus
SOURCES="$ROOT/sources"
MANIFEST="$ROOT/manifest.txt"
EXCLUDED="$ROOT/excluded.txt"
LOG=~/bench-results/kicad9plus-filter.log
KICAD=/opt/homebrew/bin/kicad-cli

echo "=== Phase 3 filter start $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$LOG"

# Étape 1 — filtre version >= 20240722
TMP=$(mktemp)
find "$SOURCES" -name "*.kicad_sch" 2>/dev/null > "$TMP"
total=$(wc -l < "$TMP" | xargs)
echo "[filter] total sch found: $total" | tee -a "$LOG"

: > "$MANIFEST"
: > "$EXCLUDED"
old=0; ok=0
while IFS= read -r f; do
  v=$(head -2 "$f" 2>/dev/null | grep -oE 'version [0-9]+' | head -1 | awk '{print $2}')
  if [ -z "$v" ]; then
    echo "$f # no-version" >> "$EXCLUDED"; old=$((old+1)); continue
  fi
  if [ "$v" -ge 20240722 ]; then
    echo "$f" >> "$MANIFEST"; ok=$((ok+1))
  else
    echo "$f # old-version=$v" >> "$EXCLUDED"; old=$((old+1))
  fi
done < "$TMP"
rm -f "$TMP"
echo "[filter] kicad9+: $ok, excluded (old/missing-version): $old" | tee -a "$LOG"

# Étape 2 — ERC validation (best-effort, pour info — exclusion seulement si kicad-cli plante)
echo "[erc] starting validation pass" | tee -a "$LOG"
KEPT="$ROOT/manifest.validated.txt"
: > "$KEPT"
ERC_LOG="$ROOT/erc-summary.tsv"
echo -e "path\trc\terrors\twarnings" > "$ERC_LOG"

erc_ok=0; erc_fail=0; n=0
total_to_check=$(wc -l < "$MANIFEST" | xargs)
while IFS= read -r sch; do
  n=$((n+1))
  out=$(mktemp)
  # `kicad-cli sch erc` requires --output
  rc=0
  timeout 30 "$KICAD" sch erc "$sch" --format json --severity-all --output "$out" >/dev/null 2>&1 || rc=$?
  errors=0; warnings=0
  if [ -s "$out" ]; then
    errors=$(python3 -c "import json,sys
try: d=json.load(open('$out'))
except: print(0); sys.exit()
n=0
for sh in d.get('sheets',[]):
  for v in sh.get('violations',[]):
    if v.get('severity')=='error': n+=1
print(n)" 2>/dev/null)
    warnings=$(python3 -c "import json,sys
try: d=json.load(open('$out'))
except: print(0); sys.exit()
n=0
for sh in d.get('sheets',[]):
  for v in sh.get('violations',[]):
    if v.get('severity')=='warning': n+=1
print(n)" 2>/dev/null)
  fi
  rm -f "$out"
  echo -e "${sch}\t${rc}\t${errors}\t${warnings}" >> "$ERC_LOG"
  if [ "$rc" -eq 0 ] || [ "$rc" -eq 5 ]; then
    # rc=0: OK; rc=5: ERC found violations but parsing OK (kicad-cli returns non-zero for any violation)
    echo "$sch" >> "$KEPT"; erc_ok=$((erc_ok+1))
  else
    echo "$sch # erc-rc=$rc" >> "$EXCLUDED"; erc_fail=$((erc_fail+1))
  fi
  if [ $((n % 100)) -eq 0 ]; then
    echo "[erc] $n/$total_to_check kept=$erc_ok rejected=$erc_fail" | tee -a "$LOG"
  fi
done < "$MANIFEST"

echo "[erc] DONE: kept=$erc_ok rejected=$erc_fail" | tee -a "$LOG"
echo "=== Phase 3 done $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$LOG"
