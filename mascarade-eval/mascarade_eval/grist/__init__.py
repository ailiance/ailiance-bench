# mascarade_eval/grist/__init__.py
"""Grist-backed dataset management for the mascarade training corpus.

Grist is the canonical source of truth. Mining ingests in insert-only
mode (human edits in Grist are never overwritten); training and HF
publication consume a deterministic export of human-validated rows.
"""
from pathlib import Path

GRIST_BASE = "https://grist.saillant.cc/api"

# New topology: doc IDs are resolved at runtime from grist.env.
DOC_DOMAIN_ENV = "GRIST_DOC_LLM_DOMAIN"
DOC_TRAINING_ENV = "GRIST_DOC_LLM_TRAINING"
DOC_BENCH_ENV = "GRIST_DOC_LLM_BENCH"
# Legacy doc IDs, kept read-only for the post-migration window.
DOC_HELDOUT_LEGACY = "eGbbrpzN3TeLq3sUd2YFA2"
DOC_MASCARADE_LEGACY = "dhyrySCayizD1PNqCNhCPN"

KEY_FILE = Path.home() / ".config" / "electron-rare" / "grist.env"

TRAINING_TABLE = "Dataset_Items"
REGISTRY_TABLE = "Datasets_Registry"  # legacy source table name
EXPORTS_TABLE = "Exports"

# Human-review columns appended to every validation-target table.
REVIEW_COLUMNS = ("review_status", "reviewer", "reviewed_at", "review_note")
REVIEW_STATUSES = ("pending", "validated", "rejected", "needs_fix")
REVIEWER_CHOICES = ("clems",)

# Existing tables that receive the review columns, keyed by legacy doc ID.
REVIEW_TARGETS = {
    DOC_HELDOUT_LEGACY: ("Heldout_Items", "Datasets"),
    DOC_MASCARADE_LEGACY: ("Mascarade_Eval_Items", "Bench_31_domains"),
}

TRAINING_COLUMNS = (
    "item_key", "domain", "system", "user_msg", "assistant_msg",
    "extra_turns", "source", "notes", "license", "provenance",
) + REVIEW_COLUMNS
REGISTRY_COLUMNS = (
    "name", "family", "domain", "hf_dataset_id", "license",
    "n_items", "notes",
)
EXPORTS_COLUMNS = (
    "export_id", "domain", "created_at", "n_items", "content_hash",
    "output_file", "hf_dataset_id",
)

_ROOT = Path(__file__).resolve().parent.parent.parent  # .../mascarade-eval
EXPORTS_DIR = _ROOT / "exports"
