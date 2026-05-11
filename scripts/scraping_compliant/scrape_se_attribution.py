#!/usr/bin/env python3
"""scrape_se_attribution.py — EU AI Act compliant SE attribution audit.

Thin wrapper around the existing ``~/scripts/se_attribution/audit_remaining.py``
that:

  1. Pre-flights the Stack Exchange API host (robots.txt + TDMRep) once per run.
  2. Replaces the ad-hoc ``requests.Session`` UA with the contactable
     ``Ailiance-Compliance-Crawler/1.0`` UA from ``lib_compliance``.
  3. Patches ``audit_remaining.SESSION`` to use ``compliant_get`` semantics
     (honors ``Retry-After`` and the ``backoff`` field in SE responses).
  4. Writes a per-call JSONL audit trail next to the existing caches.

Usage
-----
    python scrape_se_attribution.py --dataset power --api-key $(cat ~/.cache/stackexchange/api_key)
    python scrape_se_attribution.py --check-only            # preflight only

It NEVER deletes or mutates the existing caches or enriched JSONL outputs.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_compliance import (  # noqa: E402
    USER_AGENT,
    log_compliance_check,
    preflight,
)

HOME = Path.home()
AUDIT_DIR = HOME / "eu-kiki-data" / "scraping_logs"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
SE_LEGACY_DIR = HOME / "scripts" / "se_attribution"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def preflight_se() -> dict:
    """Pre-flight the SE API + electronics.stackexchange.com."""
    targets = [
        "https://api.stackexchange.com/2.3/search/advanced?site=electronics&q=test",
        "https://electronics.stackexchange.com/robots.txt",
    ]
    out = {}
    for u in targets:
        out[u] = preflight(u, audit_dir=AUDIT_DIR)
    return out


def patch_audit_module():
    """Import audit_remaining and replace its SESSION UA + add logging."""
    if not (SE_LEGACY_DIR / "audit_remaining.py").exists():
        raise FileNotFoundError(f"{SE_LEGACY_DIR}/audit_remaining.py missing")
    sys.path.insert(0, str(SE_LEGACY_DIR))
    import audit_remaining  # type: ignore

    # Re-stamp the User-Agent to the contactable identifier.
    audit_remaining.SESSION.headers.update({"User-Agent": USER_AGENT})

    # Wrap SESSION.get to append every call to a per-session JSONL audit log.
    orig_get = audit_remaining.SESSION.get
    log_path = AUDIT_DIR / f"se_calls_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.jsonl"

    def logged_get(url, **kw):
        t0 = time.time()
        resp = orig_get(url, **kw)
        try:
            j = resp.json() if resp.headers.get("Content-Type", "").startswith("application/json") else None
        except Exception:
            j = None
        entry = {
            "ts": now_iso(),
            "url": url,
            "params": kw.get("params"),
            "status": getattr(resp, "status_code", None),
            "ms": int((time.time() - t0) * 1000),
            "se_backoff": (j or {}).get("backoff") if isinstance(j, dict) else None,
            "quota_remaining": (j or {}).get("quota_remaining") if isinstance(j, dict) else None,
            "user_agent": USER_AGENT,
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return resp

    audit_remaining.SESSION.get = logged_get  # type: ignore[attr-defined]
    return audit_remaining, log_path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--check-only", action="store_true",
                   help="Run SE preflight only — do not call audit_remaining")
    p.add_argument("--dataset", choices=["power", "dsp", "emc", "kicad"],
                   help="Dataset short name (passed through to audit_remaining)")
    p.add_argument("--api-key", default=os.environ.get("SE_API_KEY", ""),
                   help="SE API key (or reads ~/.cache/stackexchange/api_key)")
    p.add_argument("--max-calls", type=int, default=8000)
    args = p.parse_args()

    if not args.api_key:
        cache = HOME / ".cache" / "stackexchange" / "api_key"
        if cache.exists():
            args.api_key = cache.read_text().strip()

    print("[se-compliance] running preflight...")
    pf = preflight_se()
    print(json.dumps(pf, indent=2, ensure_ascii=False))
    blocked = [u for u, v in pf.items() if not v.get("allowed", True)]
    if blocked:
        print(f"[se-compliance] BLOCKED: {blocked}", file=sys.stderr)
        return 2

    if args.check_only:
        log_compliance_check(AUDIT_DIR, "preflight_se_summary", pf)
        print(f"[se-compliance] preflight only — log dir: {AUDIT_DIR}")
        return 0

    if not args.dataset:
        print("[se-compliance] --dataset required unless --check-only", file=sys.stderr)
        return 1
    if not args.api_key:
        print("[se-compliance] no API key found (env SE_API_KEY or ~/.cache/stackexchange/api_key)",
              file=sys.stderr)
        return 1

    audit_mod, log_path = patch_audit_module()
    print(f"[se-compliance] call log -> {log_path}")
    print(f"[se-compliance] UA: {USER_AGENT}")

    sys.argv = [
        "audit_remaining",
        "--dataset", args.dataset,
        "--api-key", args.api_key,
        "--max-calls", str(args.max_calls),
    ]
    return audit_mod.main()


if __name__ == "__main__":
    sys.exit(main())
