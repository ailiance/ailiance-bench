# mascarade_eval/grist/__init__.py
"""Grist-backed dataset management for the mascarade training corpus.

Grist is the canonical source of truth. Mining ingests in insert-only
mode (human edits in Grist are never overwritten); training and HF
publication consume a deterministic export.
"""
from pathlib import Path

GRIST_BASE = "https://grist.saillant.cc/api"

# Known existing doc (held-out eval). The training doc ID is provided at
# runtime via --doc or the GRIST_DOC_TRAINING env/file value.
DOC_HELDOUT = "eGbbrpzN3TeLq3sUd2YFA2"

KEY_FILE = Path.home() / ".config" / "electron-rare" / "grist.env"

TRAINING_TABLE = "Mascarade_Training"
REGISTRY_TABLE = "Datasets_Registry"
EXPORTS_TABLE = "Exports"

TRAINING_COLUMNS = (
    "item_key", "domain", "system", "user_msg", "assistant_msg",
    "extra_turns", "source", "exclure", "notes",
)
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
