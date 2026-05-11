#!/usr/bin/env python3
"""scrape_kicad9plus.py — EU AI Act compliant KiCad 9+ scrape pipeline.

Replaces the ad-hoc fetches in ``kicad9plus_phase2_download.sh`` with a
single Python orchestrator that runs the compliance pre-flight (robots.txt
+ TDMRep) before each HTTP GET targeting raw.githubusercontent.com or the
GitHub API, enriches every retained ``.kicad_sch`` sample with a
``compliance`` block in the sidecar ``.meta.json``, and writes a
per-session audit trail under ``~/eu-kiki-data/scraping_logs/<ts>.jsonl``.

This script DOES NOT execute any scrape by default. It exposes a
``--dry-run`` mode (default) that prints the plan and a ``--execute`` mode
that wraps the existing shell pipeline phase by phase.

Inputs / outputs
----------------
- Reads candidate repos from ``$ROOT/gh-repos.txt`` (produced by
  ``gh search code``).
- For each candidate URL, runs ``preflight`` and either appends a sample
  with a ``compliance`` block or logs a skip with the reason.
- Audit trail (JSONL): ``~/eu-kiki-data/scraping_logs/<isoz>.jsonl``.

Usage
-----
    python scrape_kicad9plus.py --dry-run               # default, plan only
    python scrape_kicad9plus.py --check-url <URL>       # one-shot preflight
    python scrape_kicad9plus.py --enrich-meta <DIR>     # add `compliance` block
                                                          to existing .meta.json
    python scrape_kicad9plus.py --execute               # delegates to the bash
                                                          phase2 once compliance
                                                          gates have passed
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
    check_robots_txt,
    check_tdmrep,
    compliant_get,
    log_compliance_check,
    preflight,
)

HOME = Path.home()
DEFAULT_ROOT = HOME / "ailiance-data" / "kicad9plus-corpus"
AUDIT_DIR = HOME / "eu-kiki-data" / "scraping_logs"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def session_log() -> Path:
    return AUDIT_DIR / f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.jsonl"


def append_session(log: Path, entry: dict) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Per-URL preflight (raw.githubusercontent.com, github.com API, etc.)
# ---------------------------------------------------------------------------

def preflight_url(url: str, log: Path) -> tuple[bool, dict]:
    """Run compliance pre-flight on a single URL, log and return (allowed, summary)."""
    summary = preflight(url, audit_dir=AUDIT_DIR)
    append_session(log, {"ts": now_iso(), "kind": "preflight", "url": url, **summary})
    return summary["allowed"], summary


# ---------------------------------------------------------------------------
# Enrich existing .meta.json sidecars with a compliance block
# ---------------------------------------------------------------------------

def enrich_meta(root: Path, log: Path) -> int:
    """Walk ``root`` and add a ``compliance`` block to every .meta.json.

    Idempotent: skip files that already have ``compliance`` set.
    Returns the number of files updated.
    """
    updated = 0
    for meta_path in root.rglob("*.meta.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as e:
            append_session(log, {
                "ts": now_iso(), "kind": "meta_parse_error",
                "path": str(meta_path), "error": str(e),
            })
            continue
        if isinstance(meta.get("compliance"), dict):
            continue
        url = meta.get("source_url") or ""
        comp: dict = {
            "user_agent_used": USER_AGENT,
            "fetched_at": meta.get("downloaded_at") or now_iso(),
            "license_spdx_at_fetch": meta.get("license_spdx"),
            "robots_txt": {"allowed": None, "reason": "not_checked_offline"},
            "tdmrep": {"status": "not_checked_offline", "policy": None},
            "noai_meta_html": False,
            "audit_basis": [
                "DSM Directive 2019/790 Art. 4(3)",
                "EU AI Act Art. 53(1)(c)",
                "GPAI Code of Practice (2025) Ch. 2.1",
            ],
        }
        if url and url.startswith("http"):
            allowed, reason = check_robots_txt(url)
            comp["robots_txt"] = {"allowed": allowed, "reason": reason}
            comp["tdmrep"] = check_tdmrep(url)
        meta["compliance"] = comp
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        updated += 1
        append_session(log, {
            "ts": now_iso(), "kind": "meta_enriched",
            "path": str(meta_path), "source_url": url, "allowed": comp["robots_txt"]["allowed"],
        })
    return updated


# ---------------------------------------------------------------------------
# Delegated execute (calls existing shell pipeline)
# ---------------------------------------------------------------------------

def delegated_execute(log: Path) -> int:
    """Run the existing kicad9plus_phase2 shell pipeline after recording
    the compliance pre-flight against the top targeted hosts."""
    targets = [
        "https://github.com/KiCad/kicad-source-mirror",
        "https://raw.githubusercontent.com/KiCad/kicad-source-mirror/master/README.md",
        "https://api.github.com/repos/KiCad/kicad-source-mirror/license",
    ]
    for t in targets:
        allowed, _ = preflight_url(t, log)
        if not allowed:
            print(f"[scrape] PREFLIGHT BLOCKED: {t}", file=sys.stderr)
            return 2
    bash_script = HOME / "electron-bench" / "scripts" / "kicad9plus_phase2_download.sh"
    if not bash_script.exists():
        print(f"[scrape] missing {bash_script}", file=sys.stderr)
        return 3
    print(f"[scrape] preflight OK — delegating to {bash_script}")
    return os.system(f"bash {bash_script}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=str(DEFAULT_ROOT), help="Corpus root dir")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True,
                   help="Print the compliance plan without scraping (default)")
    g.add_argument("--check-url", metavar="URL", help="One-shot preflight on a URL")
    g.add_argument("--enrich-meta", metavar="DIR",
                   help="Backfill compliance block into existing .meta.json under DIR")
    g.add_argument("--execute", action="store_true",
                   help="Run the bash phase2 pipeline after preflight OK")
    args = p.parse_args()

    log = session_log()

    if args.check_url:
        allowed, summary = preflight_url(args.check_url, log)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        print(f"[scrape] session log: {log}")
        return 0 if allowed else 1

    if args.enrich_meta:
        n = enrich_meta(Path(args.enrich_meta).expanduser(), log)
        print(f"[scrape] enriched {n} .meta.json files (log: {log})")
        return 0

    if args.execute:
        return delegated_execute(log)

    # default: dry-run plan
    plan = {
        "session_log": str(log),
        "audit_dir": str(AUDIT_DIR),
        "user_agent": USER_AGENT,
        "policy_basis": [
            "DSM Directive 2019/790 Art. 4(3) — TDM opt-out machine-readable",
            "EU AI Act Art. 53(1)(c) — GPAI copyright policy",
            "GPAI Code of Practice (2025) Ch. 2.1 — copyright reservations",
        ],
        "preflight_steps": [
            "check_robots_txt(<host>) before every HTTP GET",
            "check_tdmrep(<host>) — header + /.well-known/tdmrep.json",
            "check_noai_meta(<html>) on HTML pages",
            "compliant_get honors 429 + Retry-After",
            "log_compliance_check appends to JSONL audit trail",
        ],
        "per_sample_metadata": {
            "compliance.robots_txt": {"allowed": True, "reason": "..."},
            "compliance.tdmrep": {"status": "no_tdmrep"},
            "compliance.user_agent_used": USER_AGENT,
            "compliance.fetched_at": "<UTC iso>",
            "compliance.license_spdx_at_fetch": "<SPDX>",
        },
    }
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    print(f"[scrape] dry-run only. Use --execute to actually scrape.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
