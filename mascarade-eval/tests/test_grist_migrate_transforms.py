# tests/test_grist_migrate_transforms.py
import json
from mascarade_eval.grist.migrate import flatten_messages, rebuild_messages


def test_flatten_single_turn_openai():
    rec = {"messages": [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "Q"},
        {"role": "assistant", "content": "A"},
    ]}
    flat = flatten_messages(rec)
    assert flat == {"system": "S", "user_msg": "Q",
                    "assistant_msg": "A", "extra_turns": ""}


def test_flatten_single_turn_sharegpt():
    rec = {"conversations": [
        {"from": "human", "value": "Q"},
        {"from": "gpt", "value": "A"},
    ]}
    flat = flatten_messages(rec)
    assert flat == {"system": "", "user_msg": "Q",
                    "assistant_msg": "A", "extra_turns": ""}


def test_flatten_multi_turn_keeps_extra_turns():
    rec = {"messages": [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "Q2"},
        {"role": "assistant", "content": "A2"},
    ]}
    flat = flatten_messages(rec)
    assert flat["user_msg"] == "Q1"
    assert flat["assistant_msg"] == "A1"
    parsed = json.loads(flat["extra_turns"])
    assert parsed == [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "Q2"},
        {"role": "assistant", "content": "A2"},
    ]


def test_rebuild_single_turn_round_trip():
    rec = {"messages": [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "Q"},
        {"role": "assistant", "content": "A"},
    ]}
    flat = flatten_messages(rec)
    assert rebuild_messages(flat) == rec


def test_rebuild_single_turn_no_system():
    flat = {"system": "", "user_msg": "Q",
            "assistant_msg": "A", "extra_turns": ""}
    assert rebuild_messages(flat) == {"messages": [
        {"role": "user", "content": "Q"},
        {"role": "assistant", "content": "A"},
    ]}


def test_rebuild_multi_turn_uses_extra_turns():
    rec = {"messages": [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "Q2"},
        {"role": "assistant", "content": "A2"},
    ]}
    flat = flatten_messages(rec)
    assert rebuild_messages(flat) == rec
