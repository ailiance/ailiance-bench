import json
from mascarade_eval.train_corpus import extract_prompts

def test_extract_prompts_handles_messages_format(tmp_path):
    f = tmp_path / "d.jsonl"
    f.write_text(json.dumps({"messages": [
        {"role": "user", "content": "Q1"}, {"role": "assistant", "content": "A1"}]}) + "\n")
    assert extract_prompts(str(f)) == ["Q1"]

def test_extract_prompts_handles_conversations_format(tmp_path):
    f = tmp_path / "d.jsonl"
    f.write_text(json.dumps({"conversations": [
        {"from": "human", "value": "Q2"}, {"from": "gpt", "value": "A2"}]}) + "\n")
    assert extract_prompts(str(f)) == ["Q2"]
