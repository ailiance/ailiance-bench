from unittest.mock import patch
from mascarade_eval.judge import parse_judge_score, sample_for_spotcheck


def test_parse_judge_score_extracts_integer():
    assert parse_judge_score("Reasoning: solid.\nSCORE: 7") == 7


def test_parse_judge_score_clamps_and_defaults():
    assert parse_judge_score("no score here") is None


def test_sample_for_spotcheck_picks_fraction():
    items = [{"i": k} for k in range(100)]
    s = sample_for_spotcheck(items, fraction=0.12, seed=0)
    assert len(s) == 12
