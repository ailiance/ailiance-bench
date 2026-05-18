#!/usr/bin/env python3
"""Curate freecad held-out items from r/FreeCAD (hand-curate fallback).

freecad has no clean time-cut upstream Q&A source (per
`mascarade-eval/docs/heldout-sources.md`). This script fills the gap by
mining r/FreeCAD via Reddit's public JSON API, ranking posts by
engagement (comments × score), and pairing each question post with its
top-voted non-stickied substantive comment as the reference answer.

The output `heldout/freecad.curated.jsonl` is explicitly flagged
`_source_type: hand-curated-reddit-r-freecad` so the verdict aggregator
can mark the domain low-confidence per the spec.

Usage:
    python3 mascarade-eval/scripts/curate_freecad_reddit.py \\
        --cutoff-date 2026-04-01 --n 25

Requires no API key (Reddit public JSON). Polite 1.8s pacing between
comment fetches. Run takes ~60s for n=25.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = "mascarade-eval-bench/0.1 (https://github.com/ailiance/ailiance-bench)"
SUBREDDIT = "FreeCAD"


def _get(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def fetch_recent_posts(max_pages: int = 8) -> list[dict]:
    """Paginate r/FreeCAD/new.json; return raw post data dicts."""
    posts: list[dict] = []
    after: str | None = None
    for _ in range(max_pages):
        url = f"https://www.reddit.com/r/{SUBREDDIT}/new.json?limit=25"
        if after:
            url += f"&after={after}"
        try:
            data = _get(url, timeout=10)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] page fetch failed: {e!r}", file=sys.stderr)
            break
        children = data["data"]["children"]
        if not children:
            break
        posts.extend(c["data"] for c in children)
        after = data["data"].get("after")
        if not after:
            break
        time.sleep(2)
    return posts


def filter_questions(posts: list[dict], cutoff_epoch: float) -> list[dict]:
    """Keep posts post-cutoff with a usable body and ≥1 comment."""
    out = []
    for pd in posts:
        if pd["created_utc"] < cutoff_epoch:
            continue
        body = pd.get("selftext") or ""
        if not body or body in ("[deleted]", "[removed]"):
            continue
        if pd.get("num_comments", 0) < 1:
            continue
        out.append(pd)
    return out


def best_comment(permalink: str) -> str | None:
    """Top-voted non-stickied, non-bot, ≥50-char comment from the thread."""
    url = f"https://www.reddit.com{permalink}.json?limit=5&sort=top"
    try:
        data = _get(url)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] comment fetch failed for {permalink}: {e!r}",
              file=sys.stderr)
        return None
    # data[1] = comments listing
    for c in data[1]["data"]["children"]:
        cd = c.get("data", {})
        if cd.get("stickied") or cd.get("distinguished"):
            continue
        body = cd.get("body", "")
        if not body or body in ("[deleted]", "[removed]"):
            continue
        if len(body) < 50:
            continue
        if cd.get("author") in ("AutoModerator", "[deleted]"):
            continue
        return body.strip()
    return None


def shape_item(pd: dict, ref: str) -> dict:
    """Mascarade-eval item shape, with provenance metadata."""
    prompt = pd["title"]
    if pd.get("selftext"):
        prompt += "\n\n" + pd["selftext"]
    return {
        "domain": "freecad",
        "prompt": prompt.strip(),
        "reference": ref,
        "source": f"https://www.reddit.com{pd['permalink']}",
        "_source_type": "hand-curated-reddit-r-freecad",
        "_created_utc": pd["created_utc"],
        "_num_comments": pd["num_comments"],
        "_score": pd["score"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff-date", required=True,
                    help="ISO date; only posts newer are kept")
    ap.add_argument("--n", type=int, default=25, help="target item count")
    ap.add_argument("--out", default=None,
                    help="output jsonl path "
                         "(default: mascarade-eval/heldout/freecad.curated.jsonl)")
    ap.add_argument("--max-candidates", type=int, default=35,
                    help="how many top-engagement posts to probe (allows "
                         "some to fail the comment-quality filter)")
    args = ap.parse_args()

    cutoff_dt = datetime.fromisoformat(args.cutoff_date).replace(tzinfo=timezone.utc)
    cutoff_epoch = cutoff_dt.timestamp()
    out_path = Path(args.out) if args.out else (
        Path(__file__).resolve().parent.parent / "heldout" / "freecad.curated.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[1/4] fetching r/{SUBREDDIT}/new.json (paginated, polite)…")
    posts = fetch_recent_posts()
    print(f"      → {len(posts)} raw posts")

    print(f"[2/4] filtering ≥ cutoff {args.cutoff_date} + body + ≥1 comment…")
    questions = filter_questions(posts, cutoff_epoch)
    print(f"      → {len(questions)} candidate question posts")

    questions.sort(
        key=lambda p: p.get("num_comments", 0) * max(p.get("score", 1), 1),
        reverse=True)
    candidates = questions[:args.max_candidates]
    print(f"[3/4] taking top {len(candidates)} by engagement, fetching top comments…")

    shaped: list[dict] = []
    for i, pd in enumerate(candidates, 1):
        if len(shaped) >= args.n:
            break
        ref = best_comment(pd["permalink"])
        if ref is None:
            print(f"      skip [{i}] no usable comment: {pd['title'][:60]}",
                  file=sys.stderr)
            time.sleep(1.5)
            continue
        item = shape_item(pd, ref)
        shaped.append(item)
        print(f"      [{len(shaped):2d}/{args.n}] "
              f"{datetime.fromtimestamp(pd['created_utc'], timezone.utc).strftime('%Y-%m-%d')} "
              f"| comm={pd['num_comments']:3} | {pd['title'][:60]}")
        time.sleep(1.8)

    print(f"[4/4] writing {len(shaped)} items → {out_path}")
    with open(out_path, "w") as f:
        for it in shaped:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"      bytes: {os.path.getsize(out_path)}")
    print(f"\n✓ DONE — {len(shaped)} freecad items curated")
    if len(shaped) < args.n:
        print(f"  WARN: requested {args.n}, got {len(shaped)} "
              f"(retry with --max-candidates {args.max_candidates*2})")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
