"""Mine a fresh held-out slice per domain from upstream (time-cut).

Per-domain source contract: mascarade-eval/docs/heldout-sources.md

Network I/O lives entirely inside mine() — this module is import-safe.
Requires:
    scripts/scraping_compliant/lib_compliance.py  (reused for UA/backoff)

Runtime dependencies (not needed for unit tests):
    - Internet access to api.stackexchange.com
    - Optional: SE API key at ~/.cache/stackexchange/api_key
      (anonymous quota ~300/day; key = 10 000/day)

SE content is CC-BY-SA-4.0.  The 'source' field always carries the post
URL + owner for attribution.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import DOMAINS, HELDOUT_DIR

# ---------------------------------------------------------------------------
# lib_compliance import (graceful fallback so unit tests don't need it)
# ---------------------------------------------------------------------------

_LIB_COMPLIANCE_PATH = (
    Path(__file__).resolve().parent.parent.parent  # repo root
    / "scripts" / "scraping_compliant" / "lib_compliance.py"
)

try:
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("lib_compliance", _LIB_COMPLIANCE_PATH)
    _lc_mod = _ilu.module_from_spec(_spec)  # type: ignore[arg-type]
    _spec.loader.exec_module(_lc_mod)  # type: ignore[union-attr]
    _compliant_get = _lc_mod.compliant_get
    _USER_AGENT = _lc_mod.USER_AGENT
    _HAS_LIB_COMPLIANCE = True
except Exception:  # pragma: no cover — only absent in test sandbox
    _HAS_LIB_COMPLIANCE = False
    _USER_AGENT = "Ailiance-Compliance-Crawler/1.0"
    _compliant_get = None

# ---------------------------------------------------------------------------
# Stack Exchange API parameters
# ---------------------------------------------------------------------------

_SE_API = "https://api.stackexchange.com/2.3"
_SE_PAGESIZE = 100

# Per-domain SE parameters (site, tags).
# Source: heldout-sources.md §Per-domain held-out source plan.
_SE_PARAMS: dict[str, dict[str, Any]] = {
    # Temporal-cut domains (training frontier ~2012; cutoff 2025-01-01 is safe)
    "kicad":   {"site": "electronics", "tags": ["kicad"]},
    "emc":     {"site": "electronics", "tags": ["emc"]},
    "power":   {"site": "electronics", "tags": ["power-supply"]},
    "dsp":     {"site": "dsp",         "tags": ["fft", "filters", "audio"]},
    # Alternative-source domains (training is synthetic/other-upstream;
    # SE is unseen by source, not by date — leakage guard is primary)
    "spice":     {"site": "electronics", "tags": ["spice", "ltspice", "ngspice"]},
    "stm32":     {"site": "electronics", "tags": ["stm32"]},
    "embedded":  {"site": "electronics", "tags": ["microcontroller", "embedded", "firmware"]},
    "platformio":{"site": "electronics", "tags": ["esp32"]},
    "iot":       {"site": "electronics", "tags": ["esp32", "iot"]},
    # freecad: no clean upstream → hand-curate fallback (returns [])
}

_FREECAD_NOTICE = (
    "freecad: no clean upstream SE source — requires manual curation of ≥25 items "
    "in heldout/freecad.raw.jsonl flagged source='hand-curated'. "
    "See mascarade-eval/docs/heldout-sources.md §freecad."
)

# ---------------------------------------------------------------------------
# HTML → plain text
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_WS = re.compile(r"\s{2,}")


def _strip_html(text: str) -> str:
    """Remove HTML tags and unescape HTML entities."""
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return _MULTI_WS.sub(" ", text).strip()


# ---------------------------------------------------------------------------
# SE API key loader
# ---------------------------------------------------------------------------

def _load_api_key() -> str | None:
    key_path = Path.home() / ".cache" / "stackexchange" / "api_key"
    try:
        return key_path.read_text().strip() or None
    except OSError:
        return None


# ---------------------------------------------------------------------------
# SE API HTTP helpers
# ---------------------------------------------------------------------------

def _se_get(url: str) -> dict:
    """Fetch a SE API URL, honoring 'backoff' field; return parsed JSON."""
    if _HAS_LIB_COMPLIANCE and _compliant_get is not None:
        resp = _compliant_get(url, timeout=15)
        body = resp.text
    else:  # pragma: no cover
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read().decode("utf-8", errors="replace")
    data = json.loads(body)
    backoff = data.get("backoff", 0)
    if backoff:
        time.sleep(backoff + 1)
    quota = data.get("quota_remaining")
    if quota is not None and quota < 10:
        print(f"  [warn] SE quota_remaining={quota}", file=sys.stderr)
    return data


def _fetch_se_questions(
    site: str,
    tag: str,
    fromdate: int,
    n: int,
    api_key: str | None,
) -> list[dict]:
    """Fetch up to n questions for one (site, tag) pair, fromdate epoch."""
    collected: list[dict] = []
    page = 1
    while len(collected) < n:
        params: dict[str, Any] = {
            "site": site,
            "tagged": tag,
            "fromdate": fromdate,
            "sort": "creation",
            "order": "desc",
            "pagesize": min(_SE_PAGESIZE, n - len(collected)),
            "filter": "withbody",
            "page": page,
        }
        if api_key:
            params["key"] = api_key
        qs = urllib.parse.urlencode(params)
        url = f"{_SE_API}/questions?{qs}"
        data = _se_get(url)
        items = data.get("items", [])
        collected.extend(items)
        if not data.get("has_more") or not items:
            break
        page += 1
        time.sleep(0.5)  # polite pacing
    return collected[:n]


def _fetch_answers(
    site: str,
    question_id: int,
    api_key: str | None,
) -> list[dict]:
    """Return answers for question_id, sorted by votes desc."""
    params: dict[str, Any] = {
        "site": site,
        "sort": "votes",
        "order": "desc",
        "filter": "withbody",
    }
    if api_key:
        params["key"] = api_key
    qs = urllib.parse.urlencode(params)
    url = f"{_SE_API}/questions/{question_id}/answers?{qs}"
    data = _se_get(url)
    return data.get("items", [])


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

def shape_item(raw: dict, domain: str) -> dict:
    """Map one raw upstream record to a held-out item.

    Supports both SE API 'body' (HTML) and 'body_markdown' fields.
    Prompt = title [+ stripped body when present].
    Reference = 'accepted_answer_body' key (pre-stripped by mine()), or
    empty string when absent.
    Source = 'link' key, else 'source' key, else literal 'upstream'.
    """
    title = raw.get("title", "").strip()
    body_raw = raw.get("body_markdown") or raw.get("body") or ""
    body = _strip_html(body_raw).strip() if body_raw else ""
    prompt = f"{title}\n\n{body}".strip() if body else title
    reference = raw.get("accepted_answer_body", "").strip()
    source = raw.get("link") or raw.get("source") or "upstream"
    return {
        "domain": domain,
        "prompt": prompt,
        "reference": reference,
        "source": source,
    }


def mine(domain: str, n: int, cutoff_date: str) -> list[dict]:
    """Fetch <= n records for `domain` newer than `cutoff_date`.

    Implements the per-domain source/filter from
    mascarade-eval/docs/heldout-sources.md (Task 1).

    Parameters
    ----------
    domain:
        One of the 10 mascarade domains.
    n:
        Maximum number of shaped items to return.
    cutoff_date:
        ISO-8601 date string (e.g. "2025-01-01").  Converted to a Unix
        epoch for the SE API fromdate parameter.  For non-SE domains
        (freecad) the argument is accepted but ignored.

    Returns
    -------
    list[dict]
        Each item: {"domain", "prompt", "reference", "source"}.
        Items with empty reference (no answers) are dropped.
    """
    if domain == "freecad":
        print(_FREECAD_NOTICE, file=sys.stderr)
        return []

    if domain not in _SE_PARAMS:
        print(
            f"[warn] mine(): unknown domain {domain!r} — returning []",
            file=sys.stderr,
        )
        return []

    # Parse cutoff_date → Unix epoch
    try:
        cutoff_dt = datetime.fromisoformat(cutoff_date).replace(tzinfo=timezone.utc)
    except ValueError:
        cutoff_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    fromdate = int(cutoff_dt.timestamp())

    site = _SE_PARAMS[domain]["site"]
    tags: list[str] = _SE_PARAMS[domain]["tags"]
    api_key = _load_api_key()

    # Collect raw questions across all tags (deduplicate by question_id)
    seen_ids: set[int] = set()
    raw_questions: list[dict] = []
    per_tag = max(n * 2, _SE_PAGESIZE)  # over-fetch to account for answer-less drops
    for tag in tags:
        if len(raw_questions) >= per_tag:
            break
        questions = _fetch_se_questions(site, tag, fromdate, per_tag, api_key)
        for q in questions:
            qid = q.get("question_id")
            if qid and qid not in seen_ids:
                seen_ids.add(qid)
                raw_questions.append(q)

    # Shape and resolve references
    items: list[dict] = []
    for q in raw_questions:
        if len(items) >= n:
            break
        if not q.get("answer_count"):
            continue  # no answers → skip (no reference)

        # Determine reference answer
        accepted_id = q.get("accepted_answer_id")
        answers = _fetch_answers(site, q["question_id"], api_key)
        time.sleep(0.3)

        if not answers:
            continue

        if accepted_id:
            ref_answer = next(
                (a for a in answers if a.get("answer_id") == accepted_id), answers[0]
            )
        else:
            ref_answer = answers[0]  # already sorted by votes desc

        # Build raw dict in the shape shape_item expects
        raw = {
            "title": q.get("title", ""),
            "body": q.get("body", ""),
            "accepted_answer_body": _strip_html(ref_answer.get("body", "")),
            "link": q.get("link", ""),
            # attribution metadata (CC-BY-SA-4.0)
            "source": q.get("link", ""),
            "question_id": q.get("question_id"),
            "answer_id": ref_answer.get("answer_id"),
            "answer_score": ref_answer.get("score"),
            "is_accepted": ref_answer.get("is_accepted", False),
            "creation_date": q.get("creation_date"),
            "content_license": q.get("content_license", "CC BY-SA 4.0"),
            "owner": q.get("owner", {}),
        }

        item = shape_item(raw, domain)
        if not item["reference"]:
            continue  # empty answer body → skip
        items.append(item)

    return items


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Mine held-out eval items per domain from upstream sources."
    )
    ap.add_argument("--domains", nargs="*", default=list(DOMAINS))
    ap.add_argument("--n", type=int, default=40,
                    help="Max items per domain (default: 40)")
    ap.add_argument("--cutoff-date", required=True,
                    help="ISO date (YYYY-MM-DD); only items newer are mined")
    args = ap.parse_args()
    HELDOUT_DIR.mkdir(parents=True, exist_ok=True)
    for domain in args.domains:
        print(f"Mining {domain}...", file=sys.stderr)
        items = mine(domain, args.n, args.cutoff_date)
        out = HELDOUT_DIR / f"{domain}.raw.jsonl"
        out.write_text(
            "\n".join(json.dumps(i, ensure_ascii=False) for i in items),
            encoding="utf-8",
        )
        print(f"{domain}: {len(items)} items -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
