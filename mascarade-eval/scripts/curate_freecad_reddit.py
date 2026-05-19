#!/usr/bin/env python3
"""Curate a held-out freecad slice from r/FreeCAD (Reddit public JSON).

freecad has no clean upstream Stack Exchange source (see
``mascarade-eval/docs/heldout-sources.md``), so the eval harness expects
a hand-curated ``heldout/freecad.raw.jsonl``. This script builds it
automatically from r/FreeCAD.

Selecting good Q&A items is the hard part: r/FreeCAD barely uses link
flairs, and ranking by upvotes surfaces *showcases*, not *questions*.
So selection works in three layers:
  1. Source -- Reddit search on interrogative phrases ("how do i",
     "help with", ...), sorted by comment count (= answered posts).
  2. Filter -- a question/showcase heuristic over title + body.
  3. Pairing -- each post is matched with its top-scored substantive
     non-OP comment; posts without one are dropped.

Output items match ``mine_upstream.shape_item``:
``{domain, prompt, reference, source}``. ``source`` carries the post
permalink for attribution.

No API key needed -- public ``.json`` endpoints, polite User-Agent and
pacing. Pure stdlib. Run from a residential IP if possible; Reddit
throttles datacenter IPs harder.

Usage::

    python scripts/curate_freecad_reddit.py             # 40 items
    python scripts/curate_freecad_reddit.py --target 30
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# --- make the harness importable without installing the package ----------
_PKG_PARENT = Path(__file__).resolve().parent.parent  # .../mascarade-eval
if str(_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_PKG_PARENT))

from mascarade_eval import HELDOUT_DIR  # noqa: E402

_UA = "Ailiance-Compliance-Crawler/1.0 (mascarade-eval freecad held-out)"
_SUB = "FreeCAD"
_BASE = "https://www.reddit.com"
_MULTI_WS = re.compile(r"\s+")
_BAD_AUTHORS = {"AutoModerator", "[deleted]", None}
_DEAD_BODIES = {"[deleted]", "[removed]", ""}

# Interrogative search queries -- the source pool of question-like posts.
_SEARCH_QUERIES = (
    "how do i", "how to", "is it possible", "help with",
    "problem with", "why does", "how can i",
)

# A post is question-like if its title or body carries one of these.
_QUESTION_KW = (
    "how do i", "how do you", "how to", "how can i", "how would i",
    "how should i", "is it possible", "is there a way", "any way to",
    "best way to", "what's the best way", "what is the best way",
    "can someone", "anyone know", "need help", "help with", "trouble with",
    "problem with", "issue with", "can't ", "cannot ", "won't ",
    "doesn't work", "not working", "stuck on", "stuck with",
    "what am i doing wrong", "why does", "why is", "why won't",
    "why doesn't", "beginner question", "newbie", "noob",
)

# Titles carrying these are showcases/news -- dropped even if they
# happen to match a question keyword or end with "?".
_SHOWCASE_KW = (
    "i made", "i built", "i designed", "i created", "i finished",
    "i've made", "i've built", "i'm building", "i am building",
    "my first", "check out", "behold", "showcase", "look what",
    "look at my", "finished my", "completed my", "just finished",
    "what do you think", "made in freecad", "made with freecad",
    "designed in freecad", "my latest",
)

# Titles carrying these are opinion/comparison/vent threads -- real
# discussion, but not technical Q&A, so dropped.
_DISCUSSION_KW = (
    "is it worth", "worth trying", "worth switching", "worth the switch",
    "should i switch", "switching away", "thinking about switching",
    "thinking of switching", "reasons to leave", "reasons to switch",
    " vs ", " vs.", "vs freecad", "vs fusion", "do you find",
    "do you prefer", "what is missing", "what's missing",
    "where are you at", "so hard to use", "why is this program",
    "everything is broken", "replace commercial", "career",
    "opinions on", "thoughts on", "is freecad worth", "hot take",
    "rant", "am i the only",
)


def _get(path: str, params: dict) -> dict | list:
    """GET a Reddit .json endpoint, retrying on HTTP 429."""
    url = f"{_BASE}{path}?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 3:
                time.sleep(5 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"giving up on {url}")


def _clean(text: str) -> str:
    """Collapse whitespace and unescape HTML entities."""
    return _MULTI_WS.sub(" ", html.unescape(text or "")).strip()


def _search(query: str, time_range: str) -> list[dict]:
    """Subreddit search, most-commented first (= answered posts)."""
    data = _get(f"/r/{_SUB}/search.json", {
        "q": query, "restrict_sr": "on", "sort": "comments",
        "t": time_range, "limit": 100, "raw_json": 1,
    })
    return [c["data"] for c in data["data"]["children"]
            if c.get("kind") == "t3"]


def _is_question(title: str, body: str) -> bool:
    """True for help/question posts, False for showcases and news."""
    title_l = title.lower()
    if any(kw in title_l for kw in _SHOWCASE_KW):
        return False
    if any(kw in title_l for kw in _DISCUSSION_KW):
        return False
    if title.rstrip().endswith("?"):
        return True
    return any(kw in f"{title_l} {body.lower()}" for kw in _QUESTION_KW)


def _best_comment(post_id: str, op: str | None, min_score: int,
                  min_len: int) -> dict | None:
    """Highest-scored substantive top-level non-OP comment, or None."""
    data = _get(f"/r/{_SUB}/comments/{post_id}.json",
                {"sort": "top", "limit": 50, "depth": 1, "raw_json": 1})
    if not isinstance(data, list) or len(data) < 2:
        return None
    best: dict | None = None
    for child in data[1]["data"]["children"]:
        if child.get("kind") != "t1":
            continue  # "more" stubs, etc.
        c = child["data"]
        if c.get("author") in _BAD_AUTHORS or c.get("author") == op:
            continue
        if c.get("stickied") or (c.get("body") or "") in _DEAD_BODIES:
            continue
        if c.get("score", 0) < min_score:
            continue
        if len(_clean(c.get("body", ""))) < min_len:
            continue
        if best is None or c.get("score", 0) > best.get("score", 0):
            best = c
    return best


def curate(target: int, min_comment_score: int, min_comment_len: int,
           min_body: int) -> list[dict]:
    # Source pool: interrogative searches, recent first then all-time.
    candidates: dict[str, dict] = {}
    for time_range in ("year", "all"):
        for query in _SEARCH_QUERIES:
            for post in _search(query, time_range):
                candidates.setdefault(post["id"], post)
            time.sleep(1.0)
        if len(candidates) >= target * 6:
            break
    print(f"  {len(candidates)} candidate posts gathered", file=sys.stderr)

    # Keep genuine question posts; rank by answered-ness (comment count).
    questions = [
        p for p in candidates.values()
        if not p.get("stickied") and not p.get("over_18")
        and p.get("num_comments", 0) >= 3
        and len(_clean(p.get("selftext", ""))) >= min_body
        and _is_question(_clean(p.get("title", "")),
                         _clean(p.get("selftext", "")))
    ]
    questions.sort(key=lambda p: p.get("num_comments", 0), reverse=True)
    print(f"  {len(questions)} pass the question filter", file=sys.stderr)

    items: list[dict] = []
    for post in questions:
        if len(items) >= target:
            break
        comment = _best_comment(post["id"], post.get("author"),
                                min_comment_score, min_comment_len)
        time.sleep(1.5)  # polite pacing between comment fetches
        if comment is None:
            continue
        title = _clean(post.get("title", ""))
        body = _clean(post.get("selftext", ""))
        items.append({
            "domain": "freecad",
            "prompt": f"{title}\n\n{body}".strip(),
            "reference": _clean(comment["body"]),
            "source": _BASE + post.get("permalink", ""),
        })
        print(f"  [{len(items):2d}] {title[:66]}", file=sys.stderr)
    return items


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--target", type=int, default=40,
                    help="number of items to curate (default 40)")
    ap.add_argument("--min-comment-score", type=int, default=2,
                    help="minimum Reddit score for the reference comment")
    ap.add_argument("--min-comment-len", type=int, default=80,
                    help="minimum reference comment length, chars")
    ap.add_argument("--min-body", type=int, default=280,
                    help="minimum post body length, chars -- long prompts "
                         "keep the downstream leakage metric meaningful")
    args = ap.parse_args()

    print(f"Curating r/{_SUB} -> target {args.target} items...",
          file=sys.stderr)
    items = curate(args.target, args.min_comment_score,
                   args.min_comment_len, args.min_body)

    HELDOUT_DIR.mkdir(parents=True, exist_ok=True)
    out = HELDOUT_DIR / "freecad.raw.jsonl"
    out.write_text(
        "\n".join(json.dumps(it, ensure_ascii=False) for it in items),
        encoding="utf-8",
    )
    print(f"freecad: {len(items)} items -> {out}")
    if len(items) < 25:
        print(f"[warn] only {len(items)} items (< 25 recommended) -- loosen "
              f"--min-comment-score / --min-comment-len", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
