from mascarade_eval.grist.llm_schema import LLM_DOCS, provision_doc


def test_llm_docs_has_the_four_documents():
    assert set(LLM_DOCS) == {"domain", "training", "bench", "workflow"}


def test_each_doc_declares_its_tables():
    assert set(LLM_DOCS["domain"]) == {"Sourcing", "Dataset_Items"}
    assert set(LLM_DOCS["training"]) == {"Exports", "Training_Runs"}
    assert set(LLM_DOCS["bench"]) == {"Bench_Results", "Eval_Items"}
    assert set(LLM_DOCS["workflow"]) == {"Pipeline_Status", "Audit_Log"}


def test_dataset_items_carries_review_columns():
    cols = LLM_DOCS["domain"]["Dataset_Items"]
    for c in ("item_key", "domain", "user_msg", "assistant_msg",
              "review_status"):
        assert c in cols


def test_provision_doc_creates_missing_tables(fake_client):
    client = fake_client(tables=[])
    report = provision_doc(client, LLM_DOCS["training"])
    assert report == {"Exports": "created", "Training_Runs": "created"}
    assert client.created[0][0] in {"Exports", "Training_Runs"}
    assert len(client.created) == 2


def test_provision_doc_is_idempotent(fake_client):
    client = fake_client(tables=["Exports"])
    report = provision_doc(client, LLM_DOCS["training"])
    assert report == {"Exports": "exists", "Training_Runs": "created"}
    assert [t for t, _ in client.created] == ["Training_Runs"]
