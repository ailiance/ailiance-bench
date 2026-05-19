# tests/test_grist_constants.py
from mascarade_eval import grist


def test_constants_present():
    assert grist.GRIST_BASE == "https://grist.saillant.cc/api"
    assert grist.DOC_HELDOUT == "eGbbrpzN3TeLq3sUd2YFA2"
    assert grist.TRAINING_TABLE == "Mascarade_Training"
    assert grist.REGISTRY_TABLE == "Datasets_Registry"
    assert grist.EXPORTS_TABLE == "Exports"


def test_training_columns_shape():
    assert grist.TRAINING_COLUMNS == (
        "item_key", "domain", "system", "user_msg", "assistant_msg",
        "extra_turns", "source", "exclure", "notes",
    )
    assert "exclure" in grist.TRAINING_COLUMNS


def test_exports_dir_under_repo_root():
    # EXPORTS_DIR sits next to the heldout/ dir at the repo root.
    assert grist.EXPORTS_DIR.name == "exports"
