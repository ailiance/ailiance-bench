#!/usr/bin/env python3
"""Phase 4 — Build dataset.jsonl + LICENSE_INVENTORY.md for KiCad 9+ corpus."""
from __future__ import annotations
import json, os, re, sys, time, hashlib
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path.home() / "ailiance-data" / "kicad9plus-corpus"
MANIFEST = ROOT / "manifest.validated.txt"
OUT_JSONL = ROOT / "dataset.jsonl"
OUT_INVENTORY = ROOT / "LICENSE_INVENTORY.md"
OUT_STATS = ROOT / "stats.json"
MAX_CONTENT_BYTES = 8192  # Truncate to fit context

# Public-only by default (exclude PROPRIETARY-INTERNAL grosmac files)
INCLUDE_PROPRIETARY = os.environ.get("INCLUDE_PROPRIETARY", "0") == "1"

PROMPT_TPL = (
    "Generate a KiCad {version} schematic ({hint}). "
    "Use the standard S-expression format starting with `(kicad_sch ...)`."
)

COMP_RE = re.compile(r"\(symbol\s+\(lib_id\s+\"([^\"]+)\"")
TITLE_RE = re.compile(r"\(title\s+\"([^\"]+)\"")
COMPANY_RE = re.compile(r"\(company\s+\"([^\"]+)\"")


def short_describe(content: str) -> str:
    """Build a short hint about what's in the schematic."""
    libs = COMP_RE.findall(content)
    title_m = TITLE_RE.search(content)
    company_m = COMPANY_RE.search(content)
    n_comp = len(libs)
    families = Counter()
    for lib in libs:
        # lib_id format: Library:Symbol -> take Library
        fam = lib.split(":", 1)[0] if ":" in lib else "?"
        families[fam] += 1
    top_fams = ", ".join(f"{k}({v})" for k, v in families.most_common(5))
    parts = []
    if title_m:
        parts.append(f"titled '{title_m.group(1)[:60]}'")
    if company_m:
        parts.append(f"by {company_m.group(1)[:30]}")
    parts.append(f"{n_comp} components")
    if top_fams:
        parts.append(f"libraries: {top_fams}")
    return ", ".join(parts)


def main():
    if not MANIFEST.exists():
        print(f"ERROR: missing {MANIFEST}", file=sys.stderr)
        sys.exit(1)

    paths = [Path(p) for p in MANIFEST.read_text().strip().splitlines() if p]
    print(f"[build] {len(paths)} validated sch in manifest")

    n_written = 0
    n_skipped_meta = 0
    n_skipped_prop = 0
    n_skipped_empty = 0
    inventory = []  # (license, repo, source_url, file_hash)
    license_counts = Counter()
    repo_counts = Counter()
    seen_hashes = set()  # de-dupe

    with OUT_JSONL.open("w") as out:
        for sch in paths:
            meta_path = Path(str(sch) + ".meta.json")
            if not meta_path.exists():
                n_skipped_meta += 1
                continue
            try:
                meta = json.loads(meta_path.read_text())
            except Exception:
                n_skipped_meta += 1
                continue

            lic = meta.get("license_spdx", "UNKNOWN")
            if not INCLUDE_PROPRIETARY and lic in ("PROPRIETARY-INTERNAL", "UNKNOWN"):
                n_skipped_prop += 1
                continue

            try:
                content = sch.read_text(errors="replace")
            except Exception:
                n_skipped_empty += 1
                continue
            if not content.strip():
                n_skipped_empty += 1
                continue

            # De-duplication via SHA-256
            sha = hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest()
            if sha in seen_hashes:
                continue
            seen_hashes.add(sha)

            # Truncate content for assistant turn
            truncated = content[:MAX_CONTENT_BYTES]
            if len(content) > MAX_CONTENT_BYTES:
                truncated += "\n; ... [truncated, full file at source_url] ...\n)"

            ver = meta.get("kicad_version", "?")
            ver_label = "10" if (ver and ver >= "20260000") else "9"
            hint = short_describe(content)
            prompt = PROMPT_TPL.format(version=ver_label, hint=hint)

            sample = {
                "messages": [
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": truncated},
                ],
                "metadata": {
                    "source_url": meta.get("source_url"),
                    "license_spdx": lic,
                    "commit_sha": meta.get("commit_sha"),
                    "kicad_version": ver,
                    "repo": meta.get("repo"),
                    "rel_path": meta.get("rel_path"),
                    "file_size_bytes": meta.get("file_size_bytes"),
                    "file_sha256": sha,
                    "ia_act_status": meta.get("ia_act_status"),
                    "compliance_notes": meta.get("compliance_notes"),
                    "downloaded_at": meta.get("downloaded_at"),
                },
            }
            out.write(json.dumps(sample, ensure_ascii=False) + "\n")
            n_written += 1
            license_counts[lic] += 1
            repo_counts[meta.get("repo", "?")] += 1
            inventory.append((lic, meta.get("repo"), meta.get("source_url"), sha[:12]))

    print(f"[build] written: {n_written} samples")
    print(f"[build] skipped: meta={n_skipped_meta} proprietary={n_skipped_prop} empty={n_skipped_empty}")

    # LICENSE_INVENTORY.md
    with OUT_INVENTORY.open("w") as f:
        f.write("# License Inventory — kicad9plus-sch-corpus\n\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n\n")
        f.write(f"Total samples: **{n_written}** (after dedup)\n\n")
        f.write("## License distribution\n\n| License | Count | % |\n|---|---|---|\n")
        for lic, count in license_counts.most_common():
            pct = (count * 100.0 / n_written) if n_written else 0
            f.write(f"| {lic} | {count} | {pct:.1f}% |\n")
        f.write("\n## Source repos\n\n| Repo | Count |\n|---|---|\n")
        for repo, count in repo_counts.most_common():
            f.write(f"| `{repo}` | {count} |\n")
        f.write("\n## Per-sample inventory\n\n")
        f.write("First 200 entries (full inventory in `dataset.jsonl` `metadata` field).\n\n")
        f.write("| SHA-12 | License | Repo | Source URL |\n|---|---|---|---|\n")
        for lic, repo, url, h in inventory[:200]:
            url_safe = (url or "").replace("|", "\\|")
            f.write(f"| `{h}` | {lic} | `{repo}` | {url_safe} |\n")

    OUT_STATS.write_text(json.dumps({
        "n_written": n_written,
        "n_skipped_meta": n_skipped_meta,
        "n_skipped_proprietary": n_skipped_prop,
        "n_skipped_empty": n_skipped_empty,
        "license_distribution": dict(license_counts),
        "top_repos": dict(repo_counts.most_common(20)),
    }, indent=2))
    print(f"[build] wrote {OUT_JSONL}, {OUT_INVENTORY}, {OUT_STATS}")


if __name__ == "__main__":
    main()
