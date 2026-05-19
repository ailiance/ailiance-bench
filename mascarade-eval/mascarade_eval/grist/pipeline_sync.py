# mascarade_eval/grist/pipeline_sync.py
"""Sync the workflow doc's Pipeline_Status from the other three docs.

collect_domains / domain_status are pure. fetch_served_aliases calls the
gateway (injectable transport). sync_pipeline orchestrates the upsert.
"""
from __future__ import annotations

from collections.abc import Callable
import datetime
import json
import sys
import urllib.request
from mascarade_eval.grist.client import load_doc_id
from mascarade_eval.grist.llm_schema import LLM_DOCS


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


def fetch_served_aliases(gateway_url: str,
                         transport: Callable[[str], dict] = _http_get_json
                         ) -> set[str]:
    """Return the set of model IDs exposed by the gateway /v1/models.

    `transport` is injected for testing; production uses urllib.
    """
    url = f"{gateway_url.rstrip('/')}/v1/models"
    payload = transport(url)
    return {m["id"] for m in payload.get("data", []) if m.get("id")}


def sync_pipeline(domain_client, training_client, bench_client,
                  workflow_client, served: set[str],
                  dry_run: bool = False) -> dict:
    """Compute each domain's status and upsert Pipeline_Status.

    `served` is the set of model IDs from the gateway. Returns
    {domain: status_row}.
    """
    domain_rows = domain_client.fetch_records("Dataset_Items")
    training_rows = training_client.fetch_records("Training_Runs")
    bench_rows = (bench_client.fetch_records("Mascarade_Eval")
                  + bench_client.fetch_records("Bench_31_domains"))

    sourced = {r["domain"] for r in domain_rows if r.get("domain")}
    trained = {r["domain"] for r in training_rows if r.get("domain")}
    evaluated = {r["domain"] for r in bench_rows if r.get("domain")}
    domains = collect_domains(domain_rows, training_rows, bench_rows)

    report: dict[str, dict] = {}
    for domain in sorted(domains):
        report[domain] = domain_status(
            domain,
            sourced=domain in sourced,
            trained=domain in trained,
            evaluated=domain in evaluated,
            served=f"ailiance-{domain}" in served,
        )
    if not dry_run:
        columns = LLM_DOCS["workflow"]["Pipeline_Status"]
        workflow_client.ensure_table("Pipeline_Status", columns)
        workflow_client.upsert_records(
            "Pipeline_Status", list(report.values()), "domain")
    return report


_DOC_ENV = {
    "domain": "GRIST_DOC_LLM_DOMAIN",
    "training": "GRIST_DOC_LLM_TRAINING",
    "bench": "GRIST_DOC_LLM_BENCH",
    "workflow": "GRIST_DOC_LLM_WORKFLOW",
}
_GATEWAY_ENV = "GRIST_GATEWAY_URL"


def resolve_sync_config() -> dict:
    """Resolve the 4 doc IDs + gateway URL from env / grist.env.

    Returns {"doc_ids": {key: id}, "gateway_url": url}. Exits if any
    value is missing.
    """
    doc_ids: dict[str, str] = {}
    for key, env_name in _DOC_ENV.items():
        doc_id = load_doc_id(env_name)
        if not doc_id:
            sys.exit(f"missing {env_name} (env or grist.env)")
        doc_ids[key] = doc_id
    gateway_url = load_doc_id(_GATEWAY_ENV)
    if not gateway_url:
        sys.exit(f"missing {_GATEWAY_ENV} (env or grist.env)")
    return {"doc_ids": doc_ids, "gateway_url": gateway_url}
