#!/usr/bin/env bash
# Phase 2 — Download corpus KiCad 9+
# Sources :
#   1. KiCad/kicad-source-mirror (GPL-3.0)
#   2. Top repos GitHub via gh search code (versions 2024/2025/2026)
#   3. GrosMac local (rsync 154 sch)
# Pour chaque sch téléchargé : génère .meta.json sidecar (IA Act).

set -u
ROOT=~/ailiance-data/kicad9plus-corpus
SOURCES="$ROOT/sources"
LOG=~/bench-results/kicad9plus-download.log
LOG_RAW="$ROOT/logs/download.log"
mkdir -p "$SOURCES" "$ROOT/logs"

echo "=== Phase 2 download start $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$LOG"

# Helper : crée un .meta.json sidecar pour un sch
# Args: <sch_path> <repo_owner_slash_name> <commit_sha> <license_spdx> <repo_path>
make_meta() {
  local sch="$1" repo="$2" sha="$3" lic="$4" rel="$5"
  local meta="${sch}.meta.json"
  local size; size=$(stat -f %z "$sch" 2>/dev/null || stat -c %s "$sch" 2>/dev/null)
  local ver; ver=$(head -2 "$sch" 2>/dev/null | grep -oE 'version [0-9]+' | head -1 | awk '{print $2}')
  local url="https://github.com/${repo}/blob/${sha}/${rel}"
  local now; now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  local notes
  case "$lic" in
    GPL-3.0|GPL-2.0|LGPL-2.1|LGPL-3.0)
      notes="copyleft license ($lic), public repo, source attribution + share-alike required" ;;
    MIT|Apache-2.0|BSD-2-Clause|BSD-3-Clause|CC0-1.0|Unlicense)
      notes="permissive license ($lic), public repo, attribution required in dataset card" ;;
    CERN-OHL-*|TAPR-OHL*|SHL-*|OHL-*)
      notes="open hardware license ($lic), public repo, see CERN-OHL terms" ;;
    *)
      notes="license=$lic — manual review recommended for compliance" ;;
  esac
  python3 -c "
import json
d = {
  'source_url': '$url',
  'license_spdx': '$lic',
  'commit_sha': '$sha',
  'kicad_version': '$ver',
  'file_size_bytes': $size,
  'downloaded_at': '$now',
  'source_type': 'github',
  'ia_act_status': 'compliant',
  'compliance_notes': '$notes',
  'repo': '$repo',
  'rel_path': '$rel'
}
print(json.dumps(d, indent=2))
" > "$meta"
}

# --- Source 1 : KiCad/kicad-source-mirror (GPL-3.0) ---
src1() {
  local repo="KiCad/kicad-source-mirror" lic="GPL-3.0"
  local dir="$SOURCES/KiCad__kicad-source-mirror"
  echo "[src1] Cloning $repo (sparse, demos+qa)" | tee -a "$LOG"
  if [ -d "$dir/.git" ]; then
    (cd "$dir" && git pull --depth=1 -q 2>>"$LOG" || true)
  else
    git clone --depth=1 --filter=blob:none --sparse "https://github.com/$repo.git" "$dir" 2>>"$LOG" || {
      echo "[src1] clone failed" | tee -a "$LOG"; return 1; }
    (cd "$dir" && git sparse-checkout set demos qa 2>>"$LOG")
  fi
  local sha; sha=$(cd "$dir" && git rev-parse HEAD)
  echo "[src1] HEAD=$sha" | tee -a "$LOG"
  local count=0
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    [ -f "${f}.meta.json" ] && { count=$((count+1)); continue; }
    local rel="${f#$dir/}"
    make_meta "$f" "$repo" "$sha" "$lic" "$rel"
    count=$((count+1))
  done < <(find "$dir" -name "*.kicad_sch")
  echo "[src1] $count sch processed" | tee -a "$LOG"
}

# --- Source 2 : GrosMac local rsync ---
src2() {
  local dir="$SOURCES/local__grosmac"
  echo "[src2] rsync from grosmac.local" | tee -a "$LOG"
  mkdir -p "$dir"
  # Test SSH connectivity (5s timeout)
  if ! ssh -o ConnectTimeout=5 -o BatchMode=yes electron@grosmac.local 'echo ok' >/dev/null 2>&1; then
    echo "[src2] grosmac.local unreachable, skip" | tee -a "$LOG"
    return 0
  fi
  rsync -aq --include='*/' --include='*.kicad_sch' --exclude='*' \
    electron@grosmac.local:Documents/Projets/ "$dir/" 2>>"$LOG" || \
    echo "[src2] rsync had errors (may be partial)" | tee -a "$LOG"
  local count=0
  local now; now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    [ -f "${f}.meta.json" ] && { count=$((count+1)); continue; }
    local size; size=$(stat -f %z "$f")
    local ver; ver=$(head -2 "$f" 2>/dev/null | grep -oE 'version [0-9]+' | head -1 | awk '{print $2}')
    local rel="${f#$dir/}"
    cat > "${f}.meta.json" <<EOF
{
  "source_url": "ssh://electron@grosmac.local/Documents/Projets/${rel}",
  "license_spdx": "PROPRIETARY-INTERNAL",
  "commit_sha": null,
  "kicad_version": "$ver",
  "file_size_bytes": $size,
  "downloaded_at": "$now",
  "source_type": "local-grosmac",
  "ia_act_status": "internal-use-only",
  "compliance_notes": "Internal Electron Rare project, owner has redistribution rights, exclude from public dataset by default",
  "repo": "local/grosmac",
  "rel_path": "$rel"
}
EOF
    count=$((count+1))
  done < <(find "$dir" -name "*.kicad_sch")
  echo "[src2] $count sch processed (kept LOCAL ONLY by default)" | tee -a "$LOG"
}

# --- Source 3 : top repos via gh search code ---
# Note historique : la requête initiale "(kicad_sch (version $ver" avec parenthèses
# non échappées renvoyait <5 résultats. Le fix est d'utiliser le filtre extension:kicad_sch
# et de retirer les parenthèses parasites, ce qui ramène ~30/100 par version (cap GitHub).
gh_search_repos() {
  local out="$ROOT/gh-repos.txt"
  : > "$out"
  # Versions KiCad 9.x (20240722+) et 10.x (20260101+) — couvrir tous les minor releases connus
  for ver in 20240722 20241228 20250114 20250610 20250715 20260101 20260306; do
    echo "[src3] gh search version $ver" | tee -a "$LOG"
    gh search code "version $ver extension:kicad_sch" --limit 100 --json repository 2>>"$LOG" \
      | python3 -c "
import sys,json
try:
  for it in json.loads(sys.stdin.read()):
    r = it.get('repository',{}).get('nameWithOwner')
    if r: print(r)
except Exception as e:
  print('err:',e,file=sys.stderr)
" >> "$out" || true
    sleep 3
  done
  sort -u "$out" -o "$out"
  echo "[src3] candidate repos: $(wc -l < "$out")" | tee -a "$LOG"
}

src3() {
  gh_search_repos
  local seen=0 cloned=0
  local out="$ROOT/gh-repos.txt"
  # Exclure KiCad/kicad-source-mirror (déjà fait en src1) et bots/forks suspects
  while IFS= read -r repo; do
    seen=$((seen+1))
    [ "$repo" = "KiCad/kicad-source-mirror" ] && continue
    # Limite : max 50 repos pour éviter explosion disque
    [ "$cloned" -ge 50 ] && { echo "[src3] cap 50 repos hit, stop" | tee -a "$LOG"; break; }

    local safe; safe="${repo//\//__}"
    local dir="$SOURCES/$safe"
    if [ -d "$dir/.git" ]; then
      echo "[src3] $repo: already cloned" >> "$LOG"
    else
      # Récupère licence via API GitHub
      local lic; lic=$(gh api "repos/$repo/license" --jq '.license.spdx_id' 2>/dev/null || echo "UNKNOWN")
      # On accepte: licenses libres ; rejette UNKNOWN/NULL pour conformité IA Act
      case "$lic" in
        MIT|Apache-2.0|BSD-2-Clause|BSD-3-Clause|CC0-1.0|Unlicense|MPL-2.0|GPL-3.0|GPL-2.0|LGPL-2.1|LGPL-3.0|CC-BY-4.0|CC-BY-SA-4.0|CERN-OHL-W-2.0|CERN-OHL-S-2.0|CERN-OHL-P-2.0)
          : ;;
        *)
          echo "[src3] $repo: license=$lic — skip" >> "$LOG"
          continue ;;
      esac
      echo "[src3] cloning $repo (license=$lic)" | tee -a "$LOG"
      if ! git clone --depth=1 --filter=blob:none --sparse "https://github.com/$repo.git" "$dir" 2>>"$LOG"; then
        echo "[src3] $repo clone FAIL" >> "$LOG"
        rm -rf "$dir"
        continue
      fi
      # Sparse-checkout : tout (let it pull, schématiques sont petits)
      (cd "$dir" && git sparse-checkout disable 2>>"$LOG"; git checkout HEAD -- . 2>>"$LOG" || true)
      cloned=$((cloned+1))
      # Sauve la licence pour réutilisation
      echo "$lic" > "$dir/.detected_license"
    fi
    # Génère méta pour chaque sch
    local lic; lic=$(cat "$dir/.detected_license" 2>/dev/null || echo "UNKNOWN")
    local sha; sha=$(cd "$dir" && git rev-parse HEAD 2>/dev/null)
    while IFS= read -r f; do
      [ -f "$f" ] || continue
      [ -f "${f}.meta.json" ] && continue
      local rel="${f#$dir/}"
      make_meta "$f" "$repo" "$sha" "$lic" "$rel"
    done < <(find "$dir" -name "*.kicad_sch" 2>/dev/null)
  done < "$out"
  echo "[src3] $cloned/$seen repos cloned" | tee -a "$LOG"
}

src1
src2
src3

echo "=== Phase 2 done $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" | tee -a "$LOG"
echo "Total sch found: $(find "$SOURCES" -name '*.kicad_sch' | wc -l)" | tee -a "$LOG"
echo "Total meta sidecars: $(find "$SOURCES" -name '*.meta.json' | wc -l)" | tee -a "$LOG"
