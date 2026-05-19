# tests/test_grist_constants.py
from mascarade_eval import grist


def test_constants_present():
    assert grist.GRIST_BASE == "https://grist.saillant.cc/api"
    assert grist.DOC_HELDOUT == "eGbbrpzN3TeLq3sUd2YFA2"
    assert grist.DOC_MASCARADE == "dhyrySCayizD1PNqCNhCPN"
    assert grist.TRAINING_TABLE == "Mascarade_Training"
    assert grist.REGISTRY_TABLE == "Datasets_Registry"
    assert grist.EXPORTS_TABLE == "Exports"


def test_review_constants():
    assert grist.REVIEW_COLUMNS == (
        "review_status", "reviewer", "reviewed_at", "review_note")
    assert grist.REVIEW_STATUSES == (
        "pending", "validated", "rejected", "needs_fix")
    assert grist.REVIEWER_CHOICES == ("clems",)


def test_review_targets_cover_both_docs():
    assert grist.REVIEW_TARGETS == {
        grist.DOC_HELDOUT: ("Heldout_Items", "Datasets"),
        grist.DOC_MASCARADE: ("Mascarade_Eval_Items", "Bench_31_domains"),
    }


def test_training_columns_end_with_review_columns():
    assert grist.TRAINING_COLUMNS == (
        "item_key", "domain", "system", "user_msg", "assistant_msg",
        "extra_turns", "source", "notes",
        "review_status", "reviewer", "reviewed_at", "review_note",
    )
    assert "exclure" not in grist.TRAINING_COLUMNS
    assert grist.TRAINING_COLUMNS[-4:] == grist.REVIEW_COLUMNS


def test_exports_dir_under_repo_root():
    assert grist.EXPORTS_DIR.name == "exports"
