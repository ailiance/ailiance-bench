"""Detect held-out items that overlap the LoRA training corpus.

Two passes: exact (normalized sha256) and near-duplicate (token-set
overlap). Dependency-free — stdlib only.

The near-duplicate pass uses the overlap coefficient on normalized
word sets: ``|A ∩ B| / min(|A|, |B|)``. This is deliberately chosen
over plain Jaccard because held-out prompts and training prompts
often differ in length and stopword padding; a short prompt that is
essentially a subset of a longer training prompt is still a leak,
and plain Jaccard would dilute that signal via the union term.
"""
from __future__ import annotations
import hashlib
import re

_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Lowercase, collapse whitespace, strip — for hashing/shingling."""
    return _WS.sub(" ", text.lower()).strip()


def _shingles(text: str, k: int = 1) -> set[str]:
    """k-word shingles of normalized text (k=1 -> token set)."""
    words = normalize(text).split()
    if len(words) < k:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}


def _overlap(a: set[str], b: set[str]) -> float:
    """Overlap coefficient: intersection over the smaller set."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def is_leak(candidate: str, train_corpus: list[str],
            overlap_threshold: float = 0.6) -> bool:
    """True if `candidate` exactly or near-duplicates any training item.

    Near-duplicate detection uses the overlap coefficient
    ``|A ∩ B| / min(|A|, |B|)`` over word shingles; a match counts as
    a leak when that coefficient is ``>= overlap_threshold``.
    """
    cand_norm = normalize(candidate)
    cand_hash = hashlib.sha256(cand_norm.encode()).hexdigest()
    cand_shingles = _shingles(candidate)
    for train_item in train_corpus:
        if hashlib.sha256(normalize(train_item).encode()).hexdigest() == cand_hash:
            return True
        if _overlap(cand_shingles, _shingles(train_item)) >= overlap_threshold:
            return True
    return False


def filter_leaks(items: list[dict], train_corpus: list[str],
                 overlap_threshold: float = 0.6) -> tuple[list[dict], list[dict]]:
    """Split `items` (each with a 'prompt' key) into (clean, dropped).

    `overlap_threshold` is forwarded to :func:`is_leak` as the
    overlap-coefficient cutoff for the near-duplicate pass.
    """
    clean, dropped = [], []
    for item in items:
        if is_leak(item["prompt"], train_corpus, overlap_threshold):
            dropped.append(item)
        else:
            clean.append(item)
    return clean, dropped
