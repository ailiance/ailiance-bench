#!/usr/bin/env python3
"""
Split kicad9plus-sch-corpus dataset.jsonl by license-family compatibility.

Why: CC-BY-SA-4.0 is one-way compatible only (works flow TO GPLv3, never the
reverse). A unified CC-BY-SA-4.0 umbrella over GPL-3 / CERN-OHL-S / EUPL inputs
violates copyleft reciprocity. Output is two compliant subsets:

  - permissive subset (Apache-2.0, MIT, CC0-1.0, CERN-OHL-P-2.0)  -> CC-BY-SA-4.0
  - copyleft subset   (GPL-3.0, CERN-OHL-S-2.0, EUPL-1.2)         -> GPL-3.0-or-later

Also corrects metadata.ia_act_status from 'compliant' -> 'requires_review'
on every sample (per the 2026-05-11 audit, ia_act_status: compliant was
prematurely asserted).

Audit: docs/audit_kicad9plus.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PERMISSIVE_LICENSES = {
    "Apache-2.0",
    "MIT",
    "CC0-1.0",
    "CERN-OHL-P-2.0",
    "BSD-3-Clause",
    "BSD-2-Clause",
    "ISC",
}

COPYLEFT_LICENSES = {
    "GPL-3.0",
    "GPL-3.0-only",
    "GPL-3.0-or-later",
    "CERN-OHL-S-2.0",
    "EUPL-1.2",
    "AGPL-3.0",
}


def split(src: Path, dst_perm: Path, dst_copy: Path) -> tuple[Counter, Counter, list[str]]:
    perm_lic: Counter = Counter()
    copy_lic: Counter = Counter()
    unknown: list[str] = []

    with src.open() as f, dst_perm.open("w") as fp, dst_copy.open("w") as fc:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            meta = d.setdefault("metadata", {})
            lic = meta.get("license_spdx", "")

            # Audit fix: downgrade ia_act_status to requires_review
            meta["ia_act_status"] = "requires_review"

            if lic in PERMISSIVE_LICENSES:
                fp.write(json.dumps(d, ensure_ascii=False) + "\n")
                perm_lic[lic] += 1
            elif lic in COPYLEFT_LICENSES:
                fc.write(json.dumps(d, ensure_ascii=False) + "\n")
                copy_lic[lic] += 1
            else:
                unknown.append(lic)

    return perm_lic, copy_lic, unknown


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--src",
        type=Path,
        default=Path("/Users/electron/ailiance-data/kicad9plus-corpus/dataset.jsonl"),
    )
    ap.add_argument(
        "--out-permissive",
        type=Path,
        default=Path("/Users/electron/ailiance-data/kicad9plus-corpus/dataset_permissive.jsonl"),
    )
    ap.add_argument(
        "--out-copyleft",
        type=Path,
        default=Path("/Users/electron/ailiance-data/kicad9plus-corpus/dataset_copyleft.jsonl"),
    )
    args = ap.parse_args()

    if not args.src.exists():
        print(f"ERROR: source not found: {args.src}", file=sys.stderr)
        return 2

    perm, copy, unknown = split(args.src, args.out_permissive, args.out_copyleft)

    print(f"PERMISSIVE: {sum(perm.values())} -> {args.out_permissive}")
    for k, v in perm.most_common():
        print(f"  {k}: {v}")
    print(f"COPYLEFT:   {sum(copy.values())} -> {args.out_copyleft}")
    for k, v in copy.most_common():
        print(f"  {k}: {v}")

    if unknown:
        print(f"WARN: {len(unknown)} samples with unrecognized license_spdx", file=sys.stderr)
        for lic, n in Counter(unknown).most_common():
            print(f"  {lic!r}: {n}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
