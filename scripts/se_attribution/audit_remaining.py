#!/usr/bin/env python3
"""Audit Stack Exchange Electronics attribution on the remaining
mascarade datasets (power | dsp | emc). Reuses the proven scoring
pipeline from poc_kicad.py.

Requires a SE API key (free, https://stackapps.com/apps/oauth/register)
to lift the anonymous quota of 300 req/day to 10 000 req/day per IP.

Usage:
    python audit_remaining.py --dataset power --api-key XXXX
    python audit_remaining.py --dataset dsp   --api-key XXXX
    python audit_remaining.py --dataset emc   --api-key XXXX

Outputs (per dataset, in ~/eu-kiki-data/):
    {dataset}_chat_enriched.jsonl
    {dataset}_audit_stats.json
    {dataset}_attribution_cache.json
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

# Reuse the proven helpers from the kicad POC.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from poc_kicad import (  # noqa: E402
    first_human_message,
    is_se_candidate,
    build_query,
    score_match,
    query_key,
    API_BASE,
    SLEEP_BETWEEN,
    HIGH_CONF,
    ACCEPT_CONF,
)

HOME = Path.home()
OUT_DIR = HOME / "eu-kiki-data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DATASETS = {
    "power": "electron-rare/mascarade-power-dataset",
    "dsp": "electron-rare/mascarade-dsp-dataset",
    "emc": "electron-rare/mascarade-emc-dataset",
    "kicad": "electron-rare/mascarade-kicad-dataset",
}

# Per-dataset filename hint inside the HF snapshot. Auto-detected if None.
DATASET_FILE_HINT = {
    "power": None,
    "dsp": None,
    "emc": None,
    "kicad": "kicad_chat.jsonl",
}

# Per-dataset cache path override (re-use existing POC caches).
DATASET_CACHE_OVERRIDE = {
    "kicad": OUT_DIR / "se_attribution_cache.json",
}

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "mascarade-attribution-recovery/1.0 "
            "(+contact: c.saillant@gmail.com)"
        )
    }
)


def find_jsonl(snapshot_dir: Path, hint: str | None) -> Path:
    if hint:
        p = snapshot_dir / hint
        if p.exists():
            return p
    candidates = sorted(snapshot_dir.rglob("*.jsonl"))
    if not candidates:
        raise FileNotFoundError(f"No .jsonl found under {snapshot_dir}")
    if len(candidates) > 1:
        print(
            f"[warn] multiple .jsonl found, picking first: {candidates[0].name}",
            file=sys.stderr,
        )
    return candidates[0]


def download_dataset(dataset_id: str) -> Path:
    """Download via hf CLI (uses the same cache as the kicad POC)."""
    from huggingface_hub import snapshot_download

    local_dir = snapshot_download(repo_id=dataset_id, repo_type="dataset")
    return Path(local_dir)


def load_cache(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def save_cache(path: Path, cache: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False))
    tmp.replace(path)


def se_search(
    q: str,
    cache: dict,
    backoff: dict,
    api_key: str,
) -> dict | None:
    k = query_key(q)
    if k in cache:
        return cache[k]
    now = time.time()
    if backoff.get("until", 0) > now:
        time.sleep(min(backoff["until"] - now, 30))
    params = {
        "site": "electronics",
        "q": q,
        "order": "desc",
        "sort": "relevance",
        "pagesize": 5,
        "filter": "!9_bDDxJY5",
        "key": api_key,
    }
    try:
        r = SESSION.get(API_BASE + "/search/advanced", params=params, timeout=20)
    except requests.RequestException as e:
        return {"error": f"req_exception: {e}"}
    if r.status_code == 429:
        backoff["until"] = time.time() + 30
        return {"error": "rate_limited"}
    try:
        data = r.json()
    except Exception:
        return {"error": f"non_json status={r.status_code}"}
    if isinstance(data, dict) and data.get("backoff"):
        backoff["until"] = time.time() + int(data["backoff"]) + 1
    if isinstance(data, dict) and "error_id" in data:
        return {"error": data.get("error_message", "api_error"), "raw": data}
    cache[k] = data
    return data


def se_get_body(
    qid: int,
    cache: dict,
    backoff: dict,
    api_key: str,
) -> dict | None:
    bk = f"body:{qid}"
    if bk in cache:
        return cache[bk]
    now = time.time()
    if backoff.get("until", 0) > now:
        time.sleep(min(backoff["until"] - now, 30))
    params = {"site": "electronics", "filter": "withbody", "key": api_key}
    try:
        r = SESSION.get(f"{API_BASE}/questions/{qid}", params=params, timeout=20)
    except requests.RequestException as e:
        return {"error": f"req_exception: {e}"}
    if r.status_code == 429:
        backoff["until"] = time.time() + 30
        return {"error": "rate_limited"}
    try:
        data = r.json()
    except Exception:
        return {"error": f"non_json status={r.status_code}"}
    if isinstance(data, dict) and data.get("backoff"):
        backoff["until"] = time.time() + int(data["backoff"]) + 1
    cache[bk] = data
    return data


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", required=True, choices=list(DATASETS))
    p.add_argument(
        "--api-key",
        required=False,
        default=os.environ.get("SE_API_KEY", ""),
        help="Stack Exchange API key (or set SE_API_KEY env var). "
        "Without one, anonymous quota is 300 req/day.",
    )
    p.add_argument(
        "--max-calls",
        type=int,
        default=int(os.environ.get("SE_MAX_CALLS", "8000")),
        help="Per-run cap on new SE API calls (default 8000, < 10k/day quota).",
    )
    args = p.parse_args()

    if not args.api_key:
        print(
            "[warn] No --api-key provided. Anonymous quota is 300/day; "
            "consider registering at https://stackapps.com/apps/oauth/register",
            file=sys.stderr,
        )

    dataset_id = DATASETS[args.dataset]
    cache_path = DATASET_CACHE_OVERRIDE.get(
        args.dataset, OUT_DIR / f"{args.dataset}_attribution_cache.json"
    )
    enriched_path = OUT_DIR / f"{args.dataset}_chat_enriched.jsonl"
    stats_path = OUT_DIR / f"{args.dataset}_audit_stats.json"

    print(f"[audit] dataset = {dataset_id}")
    snap = download_dataset(dataset_id)
    print(f"[audit] snapshot = {snap}")
    src = find_jsonl(snap, DATASET_FILE_HINT[args.dataset])
    print(f"[audit] source jsonl = {src}")

    samples = [json.loads(l) for l in src.open() if l.strip()]
    print(f"[audit] total samples: {len(samples)}")

    detected = []
    for idx, s in enumerate(samples):
        q = first_human_message(s) or ""
        ok, _ = is_se_candidate(q)
        if ok:
            detected.append((idx, q))
    print(f"[audit] SE-style candidates: {len(detected)}")

    cache = load_cache(cache_path)
    backoff: dict[str, float] = {}
    api_calls = 0

    matches: dict[int, dict] = {}
    not_found: set[int] = set()
    low_conf: set[int] = set()

    for n, (idx, q) in enumerate(detected, 1):
        if api_calls >= args.max_calls:
            print(f"[audit] reached --max-calls={args.max_calls}, stopping API")
            break
        query = build_query(q)
        if not query.strip():
            continue
        kkey = query_key(query)
        new = kkey not in cache
        data = se_search(query, cache, backoff, args.api_key)
        if new:
            api_calls += 1
            time.sleep(SLEEP_BETWEEN)
            if api_calls % 50 == 0:
                save_cache(cache_path, cache)
                print(
                    f"[audit] {n}/{len(detected)} processed, "
                    f"{api_calls} API calls, cache={len(cache)}"
                )
        if not data or data.get("error"):
            continue
        items = data.get("items") or []
        if not items:
            not_found.add(idx)
            continue
        top = items[0]
        qid = top.get("question_id")
        if not qid:
            continue
        body_data = se_get_body(qid, cache, backoff, args.api_key)
        if body_data is not None and not body_data.get("error"):
            api_calls += 1
            time.sleep(SLEEP_BETWEEN)
        bitems = (body_data or {}).get("items") or []
        body = bitems[0].get("body") if bitems else ""
        sc = score_match(q, top.get("title") or "", body)
        if sc >= ACCEPT_CONF:
            owner = top.get("owner") or {}
            matches[idx] = {
                "url": top.get("link"),
                "author_display_name": owner.get("display_name"),
                "author_user_id": owner.get("user_id"),
                "post_id": qid,
                "creation_date_unix": top.get("creation_date"),
                "license": top.get("license") or "CC-BY-SA-4.0",
                "matched_via": "api_search",
                "match_confidence": round(sc, 3),
            }
        else:
            low_conf.add(idx)

    save_cache(cache_path, cache)

    n_attr = n_nf = n_lc = 0
    with enriched_path.open("w") as f:
        for idx, s in enumerate(samples):
            md = s.setdefault("metadata", {})
            if idx in matches:
                md["stack_exchange_attribution"] = matches[idx]
                md["attribution_recovery"] = "matched_on_se"
                n_attr += 1
            elif idx in not_found:
                md["attribution_recovery"] = "not_found_on_se"
                md["attribution_recovery_note"] = (
                    "Stylistically resembled a Stack Exchange Electronics "
                    "question, but no matching post returned by the SE "
                    "/search/advanced API. Likely synthetic/curated."
                )
                n_nf += 1
            elif idx in low_conf:
                md["attribution_recovery"] = "low_confidence_match"
                n_lc += 1
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    stats = {
        "dataset": dataset_id,
        "samples_total": len(samples),
        "se_detected_heuristic": len(detected),
        "api_new_calls_this_run": api_calls,
        "se_attributed_high_conf_(>=0.85)": sum(
            1 for r in matches.values() if r["match_confidence"] >= HIGH_CONF
        ),
        "se_attributed_accepted_(>=0.60)": n_attr,
        "se_not_found_on_api": n_nf,
        "se_low_confidence_match": n_lc,
        "no_attribution_needed_synthetic_or_unique": len(samples) - n_attr - n_nf - n_lc,
        "fraction_se_real_pct": round(100.0 * n_attr / len(samples), 2),
        "fraction_not_found_pct": round(100.0 * n_nf / len(samples), 2),
        "fraction_synthetic_pct": round(
            100.0 * (len(samples) - n_attr - n_nf - n_lc) / len(samples), 2
        ),
        "thresholds": {"accept": ACCEPT_CONF, "high": HIGH_CONF},
        "outputs": {
            "enriched_jsonl": str(enriched_path),
            "cache": str(cache_path),
        },
    }
    stats_path.write_text(json.dumps(stats, indent=2))
    print("[audit] STATS:", json.dumps(stats, indent=2))
    print(f"[audit] enriched -> {enriched_path}")
    print(f"[audit] stats    -> {stats_path}")
    print(f"[audit] cache    -> {cache_path}")
    print(
        "[audit] NEXT STEP: review the enriched file, then upload via:\n"
        f"    hf upload {dataset_id} {enriched_path} <hf_path>.jsonl --repo-type dataset"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
