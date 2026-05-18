"""LLM-judge: home Mistral-Medium scores answers on a per-domain rubric;
a sampled subset is cross-checked by an external judge for calibration.
"""
from __future__ import annotations
import random
import re
from pathlib import Path
from .runner import chat_completion

GATEWAY = "http://localhost:9300/v1/chat/completions"
HOME_JUDGE = "ailiance-mistral-medium"
_RUBRIC_DIR = Path(__file__).resolve().parent / "rubrics"
_SCORE_RE = re.compile(r"SCORE:\s*(\d+)", re.IGNORECASE)


def parse_judge_score(judge_output: str) -> int | None:
    """Extract the integer 0-10 score from a judge response, or None."""
    m = _SCORE_RE.search(judge_output)
    if not m:
        return None
    return max(0, min(10, int(m.group(1))))


def _judge_prompt(domain: str, prompt: str, answer: str) -> str:
    rubric = (_RUBRIC_DIR / f"{domain}.txt").read_text()
    return (f"{rubric}\n\n=== QUESTION ===\n{prompt}\n\n"
            f"=== ANSWER TO GRADE ===\n{answer}\n\n"
            "Reply with one line of reasoning then `SCORE: <0-10>`.")


def judge_one(domain: str, prompt: str, answer: str,
              model: str = HOME_JUDGE, url: str = GATEWAY) -> int | None:
    """Score one answer with the LLM-judge."""
    out = chat_completion(url, model, _judge_prompt(domain, prompt, answer),
                          max_tokens=256)
    return parse_judge_score(out)


def sample_for_spotcheck(items: list[dict], fraction: float = 0.12,
                         seed: int = 0) -> list[dict]:
    """Deterministic subsample for external-judge cross-check."""
    rng = random.Random(seed)
    k = max(1, round(len(items) * fraction))
    return rng.sample(items, min(k, len(items)))
