#!/usr/bin/env python3
"""Export the mascarade-eval held-out datasets to Grist.

Pushes two things to the ailiance Grist doc (grist.saillant.cc):
  * ``Datasets``      -- one metadata row per domain (10 rows, upserted
    on ``name``), alongside the existing iact-bench dataset registry.
  * ``Heldout_Items`` -- one row per held-out item (table created if
    absent; ~400 rows upserted on ``item_key``): domain, prompt,
    reference, source.

Judge / verdict scores are NOT exported here -- they come from
``run_eval`` and belong in a separate ``Bench_*`` table in the
mascarade doc.

Idempotent: every row is upserted on a stable key, so re-running after
a re-curate or re-filter updates in place rather than duplicating.

Grist API key: env ``GRIST_API_KEY`` or ``~/.config/electron-rare/grist.env``.
Pure stdlib. Run where ``heldout/*.clean.jsonl`` lives (electron-server).

Usage::

    python scripts/export_grist.py --dry-run   # preview, no write
    python scripts/export_grist.py             # push to Grist
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# --- make the harness importable without installing the package ----------
_PKG_PARENT = Path(__file__).resolve().parent.parent  # .../mascarade-eval
if str(_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_PKG_PARENT))

from mascarade_eval import DOMAINS, HELDOUT_DIR  # noqa: E402

GRIST_BASE = "https://grist.saillant.cc/api"
DOC_AILIANCE = "eGbbrpzN3TeLq3sUd2YFA2"
ITEMS_TABLE = "Heldout_Items"
DATASETS_TABLE = "Datasets"
KEY_FILE = Path.home() / ".config" / "electron-rare" / "grist.env"
DOWNLOAD_DATE = "2026-05-19"
# Held-out source: Stack Exchange for every domain except freecad,
# which is curated from Reddit (see curate_freecad_reddit.py).
_SE_DOMAINS = frozenset(DOMAINS) - {"freecad"}


def _load_key() -> str:
    key = os.environ.get("GRIST_API_KEY")
    if key:
        return key
    if KEY_FILE.exists():
        for line in KEY_FILE.read_text().splitlines():
            if line.strip().startswith("GRIST_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    sys.exit("GRIST_API_KEY not found (env or ~/.config/electron-rare/grist.env)")


def _api(method: str, path: str, key: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{GRIST_BASE}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        sys.exit(f"Grist API {method} {path} -> HTTP {exc.code}: {detail}")


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()
            if line.strip()]


def _item_key(domain: str, prompt: str) -> str:
    digest = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:10]
    return f"{domain}-{digest}"


def build_payload() -> tuple[list[dict], list[dict]]:
    """Build (dataset rows, item rows) from heldout/*.clean.jsonl."""
    dataset_rows: list[dict] = []
    item_rows: list[dict] = []
    for domain in DOMAINS:
        clean_path = HELDOUT_DIR / f"{domain}.clean.jsonl"
        items = _jsonl(clean_path)
        if not items:
            print(f"[warn] no clean items for {domain} -- skipped",
                  file=sys.stderr)
            continue
        raw_n = len(_jsonl(HELDOUT_DIR / f"{domain}.raw.jsonl")) or len(items)
        is_se = domain in _SE_DOMAINS
        source = ("Stack Exchange, cutoff 2025-01-01" if is_se
                  else "r/FreeCAD curated (curate_freecad_reddit.py)")
        dataset_rows.append({
            "domain": domain,
            "name": f"heldout-{domain}",
            "n_rows": len(items),
            "license": "CC-BY-SA-4.0" if is_se else "Reddit user content",
            "hf_dataset_id": "",
            "download_date": DOWNLOAD_DATE,
            "size_mb": round(clean_path.stat().st_size / 1e6, 4),
            "notes": (f"mascarade-eval held-out; {source}; "
                      f"raw={raw_n} clean={len(items)} "
                      f"dropped={raw_n - len(items)}"),
        })
        for it in items:
            item_rows.append({
                "item_key": _item_key(domain, it.get("prompt", "")),
                "domain": domain,
                "prompt": it.get("prompt", ""),
                "reference": it.get("reference", ""),
                "source": it.get("source", ""),
                "dataset": f"heldout-{domain}",
            })
    return dataset_rows, item_rows


def ensure_items_table(key: str) -> None:
    """Create Heldout_Items (all-Text columns) if it does not exist."""
    existing = {t["id"] for t in
                _api("GET", f"/docs/{DOC_AILIANCE}/tables", key).get("tables", [])}
    if ITEMS_TABLE in existing:
        return
    columns = [{"id": c, "fields": {"label": c, "type": "Text"}}
               for c in ("item_key", "domain", "prompt", "reference",
                         "source", "dataset")]
    _api("POST", f"/docs/{DOC_AILIANCE}/tables", key,
         {"tables": [{"id": ITEMS_TABLE, "columns": columns}]})
    print(f"created table {ITEMS_TABLE}")


def upsert(table: str, rows: list[dict], key_col: str, key: str) -> None:
    """Upsert rows on key_col, in chunks of 100."""
    for start in range(0, len(rows), 100):
        chunk = rows[start:start + 100]
        body = {"records": [{"require": {key_col: r[key_col]}, "fields": r}
                            for r in chunk]}
        _api("PUT",
             f"/docs/{DOC_AILIANCE}/tables/{table}/records?onmany=first",
             key, body)
    print(f"{table}: upserted {len(rows)} rows (key={key_col})")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="print the payload, write nothing to Grist")
    args = ap.parse_args()

    dataset_rows, item_rows = build_payload()
    print(f"{len(dataset_rows)} dataset rows, {len(item_rows)} item rows")
    if args.dry_run:
        for r in dataset_rows:
            print(f"  {r['name']:22s} n_rows={r['n_rows']:3d}  {r['notes']}")
        print(f"  ({len(item_rows)} item rows not dumped)")
        return 0

    key = _load_key()
    ensure_items_table(key)
    upsert(DATASETS_TABLE, dataset_rows, "name", key)
    upsert(ITEMS_TABLE, item_rows, "item_key", key)
    print("done -- held-out datasets exported to Grist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
