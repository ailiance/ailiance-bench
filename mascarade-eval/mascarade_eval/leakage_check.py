"""Detect held-out items that overlap the LoRA training corpus.

Two passes: exact (normalized sha256) and near-duplicate (token-set
overlap). Dependency-free — stdlib only.

The near-duplicate pass uses the overlap coefficient
``|A ∩ B| / min(|A|, |B|)`` over **content-word bigrams** (k=2,
stopwords removed). Bigrams of content words fire only on shared
phrasing. An earlier version shingled unigram word sets with
stopwords kept: that saturated catastrophically when a long held-out
prompt was scored against a corpus of many short training prompts --
the long prompt covered 60%+ of some short prompt's word set through
stopwords and generic domain vocabulary alone, with no real overlap.
k=2 (not k=3) keeps the metric robust to a single-word paraphrase
between shared anchors -- trigrams break on every adjacent synonym
swap. The overlap coefficient (over plain Jaccard) is kept so a
short prompt that is a subset of a longer training prompt is a leak.
"""
from __future__ import annotations
import hashlib
import re

_WS = re.compile(r"\s+")
# Strip punctuation, but keep a period/comma between digits so numeric
# values survive intact ("3.3V" stays one token, not "3 3v").
_PUNCT = re.compile(r"(?<!\d)[^\w\s]|[^\w\s](?!\d)")


def normalize(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace — for hashing.

    Punctuation is stripped so case/punctuation-only variants of the
    same prompt (e.g. a trailing "?") collapse to one form and are
    caught by the exact-duplicate pass.
    """
    return _WS.sub(" ", _PUNCT.sub(" ", text.lower())).strip()


# Common English stopwords -- excluded from shingles so the overlap
# metric fires on shared *content*, not on grammatical padding.
_STOPWORDS = frozenset((
    "a an the and or but if then else of in on at to from by for with "
    "without as is are was were be been being do does did have has had "
    "this that these those it its i you he she we they them my your his "
    "her our their me him us not no yes can could would should will "
    "shall may might must how what why when where which who whom whose "
    "so too very just about over under into out up down off only also "
    "than there here all any some more most other such own same "
    "want need"
).split())
# Note: set/get/use/make are NOT stopwords -- in embedded/EDA prompts
# ("set the clock divider", "use a pull-up") they carry domain signal.


def _shingles(text: str, k: int = 2) -> set[str]:
    """k-word content shingles of normalized text (stopwords removed).

    k=2 (content-word bigrams): unigram word sets that kept stopwords
    false-flagged long prompts against short training prompts; k=3
    trigrams were too brittle (one synonym swap breaks every adjacent
    trigram). Bigrams hold both failure modes in check.
    """
    words = [w for w in normalize(text).split() if w not in _STOPWORDS]
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
