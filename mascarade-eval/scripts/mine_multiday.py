#!/usr/bin/env python3
"""Multi-day Stack Exchange mining scheduler for the mascarade eval harness.

Why this exists
---------------
``mascarade_eval.mine_upstream`` needs ~380-420 SE API requests to mine a
full held-out slice for the 9 Stack-Exchange-backed domains (n=40 each).
The anonymous SE quota is ~300 requests per IP per day and resets at UTC
midnight, so a full mine cannot finish in one day without an API key.

This wrapper mines as many *whole domains* as a daily budget allows,
persists progress to ``heldout/.mining_state.json``, and is meant to run
once per day (cron / launchd) until every domain is done. Once an SE API
key appears at ``~/.cache/stackexchange/api_key`` the same script still
works -- it simply finishes in a single run.

Design notes
------------
* Unit of resumability is the *domain*: ``mine()`` re-fetches a domain
  atomically (no mid-domain cursor). A domain is recorded done only once
  its ``heldout/<domain>.raw.jsonl`` is written.
* The harness is not modified. ``mine_upstream._se_get`` is monkey-patched
  to (a) count every SE request and (b) read the live ``quota_remaining``
  the API returns, so budgeting reflects reality, not just an estimate.
* The leakage filter (``filter_heldout.filter_domain``) is local, free and
  repeatable; a domain is marked done on raw-mine success even if filtering
  is skipped (e.g. missing ``huggingface_hub``). Run ``--filter-only`` later.

Usage
-----
    python scripts/mine_multiday.py            # mine one day's budget
    python scripts/mine_multiday.py --status   # show progress
    python scripts/mine_multiday.py --filter-only   # (re)filter mined data
    python scripts/mine_multiday.py --reset    # discard progress state

Run it once per day from cron until --status shows all 9 domains done.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# --- make the harness importable without installing the package ----------
_PKG_PARENT = Path(__file__).resolve().parent.parent  # .../mascarade-eval
if str(_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_PKG_PARENT))

from mascarade_eval import HELDOUT_DIR, MIN_HELDOUT  # noqa: E402
from mascarade_eval import mine_upstream as _mu      # noqa: E402

STATE_PATH = HELDOUT_DIR / ".mining_state.json"
# 9 SE-backed domains, in harness order; freecad is hand-curated, excluded.
SE_DOMAINS = [d for d in _mu.DOMAINS if d in _mu._SE_PARAMS]

DEFAULT_BUDGET = 270    # SE requests per run (margin under the ~300 daily cap)
DEFAULT_N = 40          # held-out items per domain
DEFAULT_CUTOFF = "2025-01-01"
QUOTA_FLOOR = 25        # abort before live quota_remaining drops below this


class QuotaExhausted(RuntimeError):
    """Raised by the patched _se_get when the live SE quota hits the floor."""


# --- live SE request accounting via monkey-patch -------------------------
_meter: dict = {"requests": 0, "quota_remaining": None}
_orig_se_get = _mu._se_get


def _metered_se_get(url: str) -> dict:
    """Wrap mine_upstream._se_get: count requests, watch live quota."""
    data = _orig_se_get(url)
    _meter["requests"] += 1
    quota = data.get("quota_remaining")
    if quota is not None:
        _meter["quota_remaining"] = quota
        if quota <= QUOTA_FLOOR:
            raise QuotaExhausted(
                f"SE quota_remaining={quota} <= floor {QUOTA_FLOOR}"
            )
    return data


_mu._se_get = _metered_se_get  # _fetch_* resolve _se_get at call time


def est_cost(domain: str, n: int) -> int:
    """Conservative SE-request estimate for mining one domain.

    One request per tag for the question pages, one per retained question
    for its answers, plus a 15% slack for answer-less retries.
    """
    tags = len(_mu._SE_PARAMS[domain]["tags"])
    return tags + n + math.ceil(n * 0.15) + 2


def _probe_quota() -> int | None:
    """One SE /info call to read the day's remaining quota (counted)."""
    params = {"site": "electronics"}
    key = _mu._load_api_key()
    if key:
        params["key"] = key
    url = f"{_mu._SE_API}/info?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": _mu._USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:  # network / API hiccup -- fall back to budget
        print(f"[warn] quota probe failed: {exc}", file=sys.stderr)
        return None
    _meter["requests"] += 1
    quota = data.get("quota_remaining")
    _meter["quota_remaining"] = quota
    return quota


def _load_state(n: int, cutoff: str) -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {
        "n": n,
        "cutoff_date": cutoff,
        "started": datetime.now(timezone.utc).date().isoformat(),
        "domains": {},   # domain -> {mined, raw_items, [clean_items, dropped]}
        "runs": [],      # one entry per scheduler invocation
    }


def _save_state(state: dict) -> None:
    HELDOUT_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _write_raw(domain: str, items: list[dict]) -> None:
    """Mirror mine_upstream.main(): persist the raw held-out file."""
    out = HELDOUT_DIR / f"{domain}.raw.jsonl"
    out.write_text(
        "\n".join(json.dumps(it, ensure_ascii=False) for it in items),
        encoding="utf-8",
    )


def _try_filter(domain: str) -> dict | None:
    """Run the leakage filter; tolerate a missing huggingface_hub dep."""
    try:
        from mascarade_eval.filter_heldout import filter_domain
        kept, dropped = filter_domain(domain)
    except Exception as exc:
        print(f"  [skip filter] {domain}: {exc}", file=sys.stderr)
        return None
    return {"clean_items": kept, "dropped": dropped}


def _print_next_steps(state: dict) -> None:
    unfiltered = [d for d, r in state["domains"].items()
                  if "clean_items" not in r]
    if unfiltered:
        print(f"\n[note] {len(unfiltered)} domain(s) not leakage-filtered: "
              f"{unfiltered}")
        print("       run:  python scripts/mine_multiday.py --filter-only")
    print("\nfreecad is hand-curated (not mined here) -- ensure "
          "heldout/freecad.raw.jsonl exists, then:")
    print("  python -m mascarade_eval.filter_heldout   # leakage-filter all")
    print("  python -m mascarade_eval.run_eval         # run the eval")


def run_once(args: argparse.Namespace) -> int:
    HELDOUT_DIR.mkdir(parents=True, exist_ok=True)
    state = _load_state(args.n, args.cutoff_date)
    n, cutoff = state["n"], state["cutoff_date"]  # stored config wins
    done = set(state["domains"])
    remaining = [d for d in SE_DOMAINS if d not in done]
    today = datetime.now(timezone.utc).date().isoformat()

    if not remaining:
        print(f"All {len(SE_DOMAINS)} SE domains already mined. Nothing to do.")
        _print_next_steps(state)
        return 0

    if not args.force and state["runs"] \
            and state["runs"][-1]["date"].startswith(today):
        print(f"Already ran today ({today} UTC) -- SE quota has not reset. "
              f"Use --force to override.")
        print(f"Progress: {len(done)}/{len(SE_DOMAINS)} done. "
              f"Remaining: {', '.join(remaining)}")
        return 0

    quota0 = _probe_quota()
    budget = min(args.budget, quota0) if quota0 is not None else args.budget
    print(f"[{today} UTC] quota_remaining={quota0} budget={budget} "
          f"domains remaining={len(remaining)}")

    mined: list[str] = []
    stop_reason = "all remaining domains mined"
    for domain in remaining:
        est = est_cost(domain, n)
        used = _meter["requests"]
        if used + est > budget:
            stop_reason = f"daily budget reached ({used}+{est}>{budget})"
            break
        quota = _meter["quota_remaining"]
        if quota is not None and quota - est < QUOTA_FLOOR:
            stop_reason = f"live SE quota low (quota={quota}, est={est})"
            break

        print(f"  mining {domain} (est ~{est} req)...")
        try:
            items = _mu.mine(domain, n, cutoff)
        except QuotaExhausted as exc:
            stop_reason = f"quota exhausted mid-{domain}: {exc}"
            break
        except Exception as exc:
            stop_reason = f"error mining {domain}: {exc}"
            print(f"  [error] {stop_reason}", file=sys.stderr)
            break

        _write_raw(domain, items)
        record = {"mined": today, "raw_items": len(items)}
        if len(items) < MIN_HELDOUT:
            print(f"  [warn] {domain}: {len(items)} items < MIN_HELDOUT="
                  f"{MIN_HELDOUT} -- verdict will be low-confidence")
        filt = _try_filter(domain)
        if filt:
            record.update(filt)
            print(f"  {domain}: raw={len(items)} clean={filt['clean_items']} "
                  f"dropped={filt['dropped']}")
        state["domains"][domain] = record
        mined.append(domain)
        _save_state(state)  # checkpoint after every domain

    state["runs"].append({
        "date": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "domains_mined": mined,
        "se_requests": _meter["requests"],
        "quota_start": quota0,
        "quota_end": _meter["quota_remaining"],
        "stop_reason": stop_reason,
    })
    _save_state(state)

    print(f"\nRun summary: mined {len(mined)} domain(s) {mined} "
          f"with {_meter['requests']} SE requests. Stop: {stop_reason}")
    done = set(state["domains"])
    still = [d for d in SE_DOMAINS if d not in done]
    if still:
        per_day = max(len(mined), 1)
        print(f"Progress: {len(done)}/{len(SE_DOMAINS)} done. "
              f"Remaining: {', '.join(still)} "
              f"(~{math.ceil(len(still) / per_day)} more day(s)).")
        print("Re-run tomorrow (after 00:00 UTC) to continue.")
    else:
        print(f"Progress: {len(SE_DOMAINS)}/{len(SE_DOMAINS)} -- "
              f"SE mining COMPLETE.")
        _print_next_steps(state)
    return 0


def filter_only() -> int:
    if not STATE_PATH.exists():
        print(f"No state at {STATE_PATH}; nothing mined yet.")
        return 1
    state = json.loads(STATE_PATH.read_text())
    for domain in list(state["domains"]):
        print(f"filtering {domain}...")
        filt = _try_filter(domain)
        if filt:
            state["domains"][domain].update(filt)
            print(f"  {domain}: clean={filt['clean_items']} "
                  f"dropped={filt['dropped']}")
    _save_state(state)
    return 0


def status() -> int:
    if not STATE_PATH.exists():
        print(f"No mining state at {STATE_PATH}. Nothing started.")
        return 0
    state = json.loads(STATE_PATH.read_text())
    done = state["domains"]
    print(f"State file : {STATE_PATH}")
    print(f"Config     : n={state['n']} cutoff={state['cutoff_date']} "
          f"started={state.get('started')}")
    print(f"Domains    : {len(done)}/{len(SE_DOMAINS)} mined")
    for domain in SE_DOMAINS:
        rec = done.get(domain)
        if rec:
            clean = rec.get("clean_items", "?")
            print(f"  [x] {domain:11s} raw={rec['raw_items']:3d} "
                  f"clean={clean} ({rec['mined']})")
        else:
            print(f"  [ ] {domain:11s} pending")
    for run in state.get("runs", []):
        print(f"  run {run['date']}: {len(run['domains_mined'])} domain(s), "
              f"{run['se_requests']} req, quota "
              f"{run.get('quota_start')}->{run.get('quota_end')} "
              f"| {run['stop_reason']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET,
                        help=f"max SE requests per run (default {DEFAULT_BUDGET})")
    parser.add_argument("--n", type=int, default=DEFAULT_N,
                        help=f"items per domain (default {DEFAULT_N}); "
                             "only used when seeding a fresh state")
    parser.add_argument("--cutoff-date", default=DEFAULT_CUTOFF,
                        help=f"ISO date, only newer items mined "
                             f"(default {DEFAULT_CUTOFF}); only used when "
                             "seeding a fresh state")
    parser.add_argument("--force", action="store_true",
                        help="run even if already run today (UTC)")
    parser.add_argument("--status", action="store_true",
                        help="print progress and exit")
    parser.add_argument("--filter-only", action="store_true",
                        help="(re)run the leakage filter on mined domains")
    parser.add_argument("--reset", action="store_true",
                        help="delete the mining state file and exit")
    args = parser.parse_args()

    if args.reset:
        if STATE_PATH.exists():
            STATE_PATH.unlink()
            print(f"Removed {STATE_PATH}")
        else:
            print("No state file to remove.")
        return 0
    if args.status:
        return status()
    if args.filter_only:
        return filter_only()
    return run_once(args)


if __name__ == "__main__":
    raise SystemExit(main())
