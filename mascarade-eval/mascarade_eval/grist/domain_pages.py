# mascarade_eval/grist/domain_pages.py
"""Per-domain pages for the ailiance-llm-domain Grist doc.

reconcile_domains / page_plan are pure. create_domain_page is a
best-effort Grist /apply call (injectable transport for tests).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request


def reconcile_domains(dataset_items_rows: list[dict],
                      known_domains: tuple[str, ...]) -> dict:
    """Compare the domains seen in Dataset_Items to the known set.

    Returns sorted lists: expected (the known set), present (known
    domains with rows), orphans (domains in data but not known),
    missing (known domains with no rows).
    """
    seen = {r["domain"] for r in dataset_items_rows if r.get("domain")}
    known = set(known_domains)
    return {
        "expected": sorted(known),
        "present": sorted(seen & known),
        "orphans": sorted(seen - known),
        "missing": sorted(known - seen),
    }
