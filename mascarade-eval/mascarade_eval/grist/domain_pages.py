# mascarade_eval/grist/domain_pages.py
"""Per-domain pages for the ailiance-llm-domain Grist doc.

reconcile_domains / page_plan are pure. create_domain_page is a
best-effort Grist /apply call (injectable transport for tests).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from mascarade_eval.grist import GRIST_BASE


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


def page_plan(domain: str) -> dict:
    """Describe the Grist page wanted for one domain."""
    return {
        "page_name": f"Domain: {domain}",
        "widgets": ["Sourcing", "Dataset_Items"],
        "filter": {"column": "domain", "value": domain},
    }


def _grist_applier(doc_id: str, key: str):
    """Build an applier that POSTs user-actions to a Grist doc."""
    def applier(actions: list) -> None:
        url = f"{GRIST_BASE}/docs/{doc_id}/apply"
        data = json.dumps(actions).encode()
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    return applier


def create_domain_page(domain: str, applier) -> dict:
    """Best-effort: create the domain's Grist page via a user action.

    `applier` applies a list of Grist user-actions and raises on
    failure. Returns {"domain", "status"} where status is "created"
    or "api_unsupported".
    """
    plan = page_plan(domain)
    actions = [["AddView", plan["page_name"], "raw"]]
    try:
        applier(actions)
        return {"domain": domain, "status": "created"}
    except Exception:
        return {"domain": domain, "status": "api_unsupported"}
