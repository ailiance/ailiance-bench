# mascarade_eval/grist/pipeline_sync.py
"""Sync the workflow doc's Pipeline_Status from the other three docs.

collect_domains / domain_status are pure. fetch_served_aliases calls the
gateway (injectable transport). sync_pipeline orchestrates the upsert.
"""
from __future__ import annotations

import datetime
import json
import urllib.request


def collect_domains(domain_rows: list[dict], training_rows: list[dict],
                    bench_rows: list[dict]) -> set[str]:
    """Union of the `domain` values seen across the three docs' rows."""
    domains: set[str] = set()
    for rows in (domain_rows, training_rows, bench_rows):
        for r in rows:
            value = r.get("domain")
            if value:
                domains.add(value)
    return domains


def _utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def domain_status(domain: str, sourced: bool, trained: bool,
                  evaluated: bool, served: bool) -> dict:
    """Build one Pipeline_Status row for a domain."""
    return {
        "domain": domain,
        "sourced": sourced,
        "trained": trained,
        "evaluated": evaluated,
        "served": served,
        "updated_at": _utc_now(),
        "notes": "",
    }


def _http_get_json(url: str) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", "replace")
    return json.loads(raw) if raw else {}


def fetch_served_aliases(gateway_url: str, transport=_http_get_json) -> set[str]:
    """Return the set of model IDs exposed by the gateway /v1/models.

    `transport` is injected for testing; production uses urllib.
    """
    url = f"{gateway_url.rstrip('/')}/v1/models"
    payload = transport(url)
    return {m["id"] for m in payload.get("data", []) if m.get("id")}
