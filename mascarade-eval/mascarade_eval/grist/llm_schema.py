# mascarade_eval/grist/llm_schema.py
"""Table schema for the four ailiance-llm-* Grist documents.

LLM_DOCS maps a doc key to {table_name: column_tuple}. provision_doc
ensures every declared table exists in a doc (idempotent).
"""
from __future__ import annotations

LLM_DOCS: dict[str, dict[str, tuple[str, ...]]] = {
    "domain": {
        "Sourcing": (
            "domain", "se_tags", "reddit_sources", "mining_quota",
            "mining_state", "notes",
        ),
        "Dataset_Items": (
            "item_key", "domain", "system", "user_msg", "assistant_msg",
            "extra_turns", "source", "review_status", "reviewer",
            "reviewed_at", "review_note", "notes",
        ),
    },
    "training": {
        "Exports": (
            "export_id", "domain", "created_at", "n_items",
            "content_hash", "output_file", "hf_dataset_id",
        ),
        "Training_Runs": (
            "run_id", "domain", "base_model", "export_id", "hyperparams",
            "checkpoints", "duration", "status", "lora_id", "notes",
        ),
        "Datasets": (
            "name", "family", "domain", "hf_dataset_id", "license",
            "n_items", "notes",
        ),
    },
    "bench": {
        "Bench_Results": (
            "result_id", "domain", "model", "score", "n_items",
            "created_at", "notes",
        ),
        "Eval_Items": (
            "item_key", "domain", "prompt", "reference", "response",
            "score", "judge_reasoning", "source", "notes",
        ),
    },
    "workflow": {
        "Pipeline_Status": (
            "domain", "sourced", "trained", "evaluated", "served",
            "updated_at", "notes",
        ),
        "Audit_Log": (
            "event_id", "timestamp", "kind", "domain", "detail",
        ),
    },
}


def provision_doc(client, tables: dict[str, tuple[str, ...]]) -> dict:
    """Ensure every table exists in the doc.

    Returns {table_name: "created" | "exists"}. An existing table is
    never recreated, so re-running is safe.
    """
    existing = client.list_tables()
    report: dict[str, str] = {}
    for name, columns in tables.items():
        if name in existing:
            report[name] = "exists"
        else:
            client.create_table(name, columns)
            report[name] = "created"
    return report
