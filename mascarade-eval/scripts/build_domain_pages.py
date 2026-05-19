#!/usr/bin/env python3
"""Build one Grist page per domain in the ailiance-llm-domain doc.

Reconciles the domains found in Dataset_Items against the DOMAINS
constant (warns about orphans), then best-effort creates a page per
domain. Pages the Grist API cannot create are listed for the runbook.

Usage::

    python scripts/build_domain_pages.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_PKG_PARENT = Path(__file__).resolve().parent.parent
if str(_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_PKG_PARENT))

from mascarade_eval import DOMAINS  # noqa: E402
from mascarade_eval.grist.client import (  # noqa: E402
    GristClient, load_doc_id, load_grist_key,
)
from mascarade_eval.grist.domain_pages import (  # noqa: E402
    create_domain_page, reconcile_domains,
)
from mascarade_eval.grist.domain_pages import _grist_applier  # noqa: E402

DOMAIN_DOC_ENV = "GRIST_DOC_LLM_DOMAIN"


def resolve_doc_id() -> str:
    """Return the domain doc ID from env / grist.env. Exits if unset."""
    doc_id = load_doc_id(DOMAIN_DOC_ENV)
    if not doc_id:
        sys.exit(f"missing {DOMAIN_DOC_ENV} (env or grist.env)")
    return doc_id


def main(argv: list[str] | None = None) -> int:
    doc_id = resolve_doc_id()
    client = GristClient.from_env(doc_id)
    rows = client.fetch_records("Dataset_Items")

    report = reconcile_domains(rows, DOMAINS)
    if report["orphans"]:
        print(f"[warn] orphan domains in data, not in DOMAINS: "
              f"{report['orphans']}", file=sys.stderr)
    if report["missing"]:
        print(f"[info] known domains with no rows yet: "
              f"{report['missing']}")

    applier = _grist_applier(doc_id, load_grist_key())
    created, manual = [], []
    for domain in report["expected"]:
        result = create_domain_page(domain, applier=applier)
        (created if result["status"] == "created" else manual).append(
            domain)
    print(f"pages created via API: {created}")
    print(f"pages to create by hand (see runbook): {manual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
