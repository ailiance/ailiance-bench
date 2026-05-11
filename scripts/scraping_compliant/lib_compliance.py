#!/usr/bin/env python3
"""lib_compliance.py — Common helpers for EU AI Act compliant scraping.

Implements opt-out signal checks (robots.txt, TDMRep, HTML noai meta) and
identifiable User-Agent rate-limited HTTP, with a JSONL audit trail.

Legal basis:
    - DSM Directive 2019/790 Art. 4(3): TDM opt-out via machine-readable means.
    - EU AI Act Art. 53(1)(c): GPAI providers must have a policy to respect
      EU copyright law, including opt-outs.
    - GPAI Code of Practice (July 2025), Chapter 2.1: copyright reservations.

Requires:
    Python 3.9+, requests (preferred) — falls back to urllib stdlib if absent.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
import urllib.robotparser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import requests  # type: ignore
    _HAS_REQUESTS = True
except Exception:  # pragma: no cover
    requests = None  # type: ignore
    _HAS_REQUESTS = False

# Identifiable, contactable User-Agent (not a generic browser string).
USER_AGENT = (
    "Ailiance-Compliance-Crawler/1.0 "
    "(+https://huggingface.co/Ailiance-fr; "
    "contact: c.saillant@gmail.com; "
    "EU AI Act compliance audit)"
)

_NOAI_META_RE = re.compile(
    r'<meta[^>]+name=["\'](?:robots|googlebot|bingbot)["\']'
    r'[^>]+content=["\'][^"\']*\b(?:noai|noimageai|noml)\b',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------

def check_robots_txt(url: str) -> tuple[bool, str]:
    """Check whether ``url`` is allowed by the host's robots.txt for our UA.

    Returns
    -------
    (allowed, reason) :
        ``allowed`` False only when a definitive Disallow rule applies.
        Network errors return True (default allow) but the reason is recorded.
    """
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return (True, "invalid_url_no_check")
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        allowed = rp.can_fetch(USER_AGENT, url)
        # robotparser also accepts wildcard '*' agents — re-check explicit UA name.
        allowed_star = rp.can_fetch("*", url)
        verdict = allowed and allowed_star
        return (
            verdict,
            f"robots.txt {'allow' if verdict else 'disallow'} "
            f"(ua_ok={allowed}, star_ok={allowed_star}) for {robots_url}",
        )
    except Exception as e:
        return (True, f"robots.txt unreachable ({type(e).__name__}: {e}) — default allow with caution")


# ---------------------------------------------------------------------------
# HTML noai/noimageai meta
# ---------------------------------------------------------------------------

def check_noai_meta(html: str) -> bool:
    """Return True when the HTML carries a `<meta name="robots" content="noai">`
    or sibling opt-out directive."""
    if not html:
        return False
    return bool(_NOAI_META_RE.search(html))


# ---------------------------------------------------------------------------
# TDM Reservation Protocol (TDMRep)
# ---------------------------------------------------------------------------

def check_tdmrep(url: str) -> dict[str, Any]:
    """Probe the host for a TDMRep policy (HTTP header + /.well-known)."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return {"status": "invalid_url", "policy": None}
    base = f"{parsed.scheme}://{parsed.netloc}"
    well_known = f"{base}/.well-known/tdmrep.json"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    # Try /.well-known/tdmrep.json
    try:
        if _HAS_REQUESTS:
            r = requests.get(well_known, headers=headers, timeout=5)
            if r.status_code == 200:
                try:
                    return {"status": "found", "policy": r.json(), "url": well_known}
                except Exception:
                    return {"status": "malformed_json", "policy": None, "url": well_known}
        else:
            req = urllib.request.Request(well_known, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    try:
                        body = resp.read().decode("utf-8", errors="replace")
                        return {"status": "found", "policy": json.loads(body), "url": well_known}
                    except Exception:
                        return {"status": "malformed_json", "policy": None, "url": well_known}
    except Exception:
        pass
    # Try TDM-Reservation HTTP header on the URL itself (HEAD)
    try:
        if _HAS_REQUESTS:
            r = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
            res = r.headers.get("TDM-Reservation") or r.headers.get("tdm-reservation")
            pol = r.headers.get("TDM-Policy") or r.headers.get("tdm-policy")
            if res is not None:
                return {"status": "header", "reservation": res, "policy_url": pol}
    except Exception:
        pass
    return {"status": "no_tdmrep", "policy": None}


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

def log_compliance_check(out_dir: Path | str, url: str, results: dict[str, Any]) -> Path:
    """Append one JSON line to ``<out_dir>/compliance_log.jsonl``.

    The file is created idempotently; one line per (url, ts).
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    log = out / "compliance_log.jsonl"
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "url": url,
        **results,
    }
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return log


# ---------------------------------------------------------------------------
# Compliant GET with 429/Retry-After backoff
# ---------------------------------------------------------------------------

def compliant_get(
    url: str,
    timeout: int = 10,
    headers: dict[str, str] | None = None,
    max_retries: int = 2,
):
    """GET ``url`` with the identifiable UA, honoring HTTP 429 Retry-After.

    Returns a ``requests.Response`` (when requests is available) or a
    lightweight stdlib-backed shim with ``.status_code``, ``.text``,
    ``.content`` and ``.headers``.
    """
    h = {"User-Agent": USER_AGENT}
    if headers:
        h.update(headers)
    if _HAS_REQUESTS:
        for attempt in range(max_retries + 1):
            resp = requests.get(url, headers=h, timeout=timeout)
            if resp.status_code == 429 and attempt < max_retries:
                retry = int(resp.headers.get("Retry-After", "60"))
                time.sleep(min(retry, 300))
                continue
            return resp
        return resp
    # stdlib fallback
    return _stdlib_get(url, h, timeout, max_retries)


class _StdlibResp:
    __slots__ = ("status_code", "text", "content", "headers", "url")

    def __init__(self, status_code: int, content: bytes, headers: dict[str, str], url: str):
        self.status_code = status_code
        self.content = content
        try:
            self.text = content.decode("utf-8", errors="replace")
        except Exception:
            self.text = ""
        self.headers = headers
        self.url = url

    def json(self) -> Any:
        return json.loads(self.text)


def _stdlib_get(url: str, headers: dict[str, str], timeout: int, max_retries: int) -> _StdlibResp:
    last: _StdlibResp | None = None
    for attempt in range(max_retries + 1):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                h = {k: v for k, v in resp.headers.items()}
                return _StdlibResp(resp.status, body, h, url)
        except urllib.error.HTTPError as e:
            body = b""
            try:
                body = e.read()
            except Exception:
                pass
            h = {k: v for k, v in (e.headers.items() if e.headers else [])}
            last = _StdlibResp(e.code, body, h, url)
            if e.code == 429 and attempt < max_retries:
                retry = int(h.get("Retry-After", "60"))
                time.sleep(min(retry, 300))
                continue
            return last
        except Exception as e:
            return _StdlibResp(0, str(e).encode(), {}, url)
    return last or _StdlibResp(0, b"", {}, url)


# ---------------------------------------------------------------------------
# Aggregate pre-flight check
# ---------------------------------------------------------------------------

def preflight(url: str, audit_dir: Path | str | None = None) -> dict[str, Any]:
    """Run all opt-out checks for ``url`` and log them. Return summary dict.

    ``summary["allowed"]`` is True only when robots.txt and TDMRep both
    allow the fetch.
    """
    robots_ok, robots_reason = check_robots_txt(url)
    tdm = check_tdmrep(url)
    tdm_reserved = False
    if tdm.get("status") == "header" and tdm.get("reservation") not in (None, "0"):
        tdm_reserved = True
    if tdm.get("status") == "found":
        pol = tdm.get("policy") or {}
        if isinstance(pol, dict) and pol.get("tdm-reservation") == 1:
            tdm_reserved = True
    allowed = robots_ok and not tdm_reserved
    summary = {
        "allowed": allowed,
        "robots_txt": {"allowed": robots_ok, "reason": robots_reason},
        "tdmrep": tdm,
        "tdmrep_reserved": tdm_reserved,
        "user_agent": USER_AGENT,
    }
    if audit_dir:
        log_compliance_check(audit_dir, url, summary)
    return summary


__all__ = [
    "USER_AGENT",
    "check_robots_txt",
    "check_noai_meta",
    "check_tdmrep",
    "log_compliance_check",
    "compliant_get",
    "preflight",
]


if __name__ == "__main__":
    # Smoke test on common targets.
    import sys

    for u in [
        "https://github.com/KiCad/kicad-source-mirror",
        "https://api.stackexchange.com/2.3/questions?site=electronics",
        "https://raw.githubusercontent.com/KiCad/kicad-source-mirror/master/README.md",
    ]:
        ok, reason = check_robots_txt(u)
        print(f"[robots] {u}\n   -> allowed={ok} | {reason}")
    if len(sys.argv) > 1:
        url = sys.argv[1]
        print(json.dumps(preflight(url), indent=2, ensure_ascii=False))
