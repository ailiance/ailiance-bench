# mascarade_eval/grist/migrate.py
"""Backfill the training corpus from HuggingFace into Grist.

Pure transforms (flatten_messages / rebuild_messages) are unit-tested;
migrate_domain wires them to HF download + insert-only ingestion.
"""
from __future__ import annotations

import json

from mascarade_eval import HF_ORG
from . import REGISTRY_COLUMNS, REGISTRY_TABLE, TRAINING_COLUMNS, TRAINING_TABLE
from .ingest import ingest_rows, item_key

_ROLE_NORMAL = {"user": "user", "human": "user",
                "assistant": "assistant", "gpt": "assistant",
                "system": "system"}


def _normalize(record: dict) -> list[dict]:
    """Return [{role, content}, ...] from an OpenAI or ShareGPT record."""
    raw = record.get("messages") or record.get("conversations") or []
    out: list[dict] = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        role = _ROLE_NORMAL.get(m.get("role") or m.get("from") or "")
        if role is None:
            continue
        content = m.get("content") or m.get("value") or ""
        out.append({"role": role, "content": content})
    return out


def flatten_messages(record: dict) -> dict:
    """Collapse a chat record into editable columns.

    Single-turn (<=1 system, exactly 1 user, exactly 1 assistant) maps to
    system/user_msg/assistant_msg with empty extra_turns. Anything else
    keeps the full normalized message list as JSON in extra_turns.
    """
    msgs = _normalize(record)
    systems = [m for m in msgs if m["role"] == "system"]
    users = [m for m in msgs if m["role"] == "user"]
    assistants = [m for m in msgs if m["role"] == "assistant"]
    single_turn = (len(systems) <= 1 and len(users) == 1
                   and len(assistants) == 1 and len(msgs) == len(systems) + 2)
    flat = {
        "system": systems[0]["content"] if systems else "",
        "user_msg": users[0]["content"] if users else "",
        "assistant_msg": assistants[0]["content"] if assistants else "",
        "extra_turns": "",
    }
    if not single_turn:
        flat["extra_turns"] = json.dumps(msgs, ensure_ascii=False)
    return flat


def rebuild_messages(row: dict) -> dict:
    """Inverse of flatten_messages: return {"messages": [...]}."""
    extra = row.get("extra_turns") or ""
    if extra:
        return {"messages": json.loads(extra)}
    msgs: list[dict] = []
    if row.get("system"):
        msgs.append({"role": "system", "content": row["system"]})
    msgs.append({"role": "user", "content": row.get("user_msg", "")})
    msgs.append({"role": "assistant", "content": row.get("assistant_msg", "")})
    return {"messages": msgs}


def _download_training_records(domain: str) -> list[dict]:
    """Download <domain>_chat.jsonl from HF and parse it into records."""
    from huggingface_hub import hf_hub_download
    path = hf_hub_download(
        repo_id=f"{HF_ORG}/mascarade-{domain}-dataset",
        filename=f"{domain}_chat.jsonl",
        repo_type="dataset",
    )
    records: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _to_training_row(domain: str, record: dict) -> dict:
    flat = flatten_messages(record)
    return {
        "item_key": item_key(domain, flat["user_msg"]),
        "domain": domain,
        "system": flat["system"],
        "user_msg": flat["user_msg"],
        "assistant_msg": flat["assistant_msg"],
        "extra_turns": flat["extra_turns"],
        "source": f"{HF_ORG}/mascarade-{domain}-dataset",
        "notes": "",
        "review_status": "pending",
    }


def migrate_domain(client, domain: str, records: list[dict] | None = None,
                   dry_run: bool = False) -> dict:
    """Backfill one domain's HF training data into Grist (insert-only).

    Pass `records` to skip the HF download (used by tests).
    """
    if records is None:
        records = _download_training_records(domain)
    rows = [_to_training_row(domain, r) for r in records]
    report = ingest_rows(client, TRAINING_TABLE, TRAINING_COLUMNS, rows,
                         dry_run=dry_run)
    if not dry_run:
        client.ensure_table(REGISTRY_TABLE, REGISTRY_COLUMNS)
        client.upsert_records(REGISTRY_TABLE, [{
            "name": f"mascarade-{domain}-train",
            "family": "mascarade-training",
            "domain": domain,
            "hf_dataset_id": f"{HF_ORG}/mascarade-{domain}-dataset",
            "license": "CC-BY-SA-4.0",
            "n_items": len(rows),
            "notes": f"backfilled {report['inserted']} new, "
                     f"{report['skipped']} already present",
        }], "name")
    return report
