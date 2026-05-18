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

def test_extract_prompts_multi_line_file_and_skips_empty(tmp_path):
    f = tmp_path / "d.jsonl"
    lines = [
        json.dumps({"messages": [
            {"role": "user", "content": "Qa"},
            {"role": "assistant", "content": "Aa"},
        ]}),
        json.dumps({"conversations": [
            {"from": "human", "value": "Qb"},
            {"from": "gpt", "value": "Ab"},
        ]}),
        json.dumps({"messages": [
            {"role": "user", "content": ""},
        ]}),
    ]
    f.write_text("\n".join(lines) + "\n")
    assert extract_prompts(str(f)) == ["Qa", "Qb"]

def test_extract_prompts_skips_non_dict_message_entries(tmp_path):
    f = tmp_path / "d.jsonl"
    f.write_text(json.dumps({"messages": [
        "not a dict",
        {"role": "user", "content": "Qc"},
    ]}) + "\n")
    assert extract_prompts(str(f)) == ["Qc"]
