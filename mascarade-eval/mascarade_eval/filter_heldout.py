"""Apply the leakage filter to held-out raw items → clean items.

Pipeline glue between :mod:`mine_upstream` (produces
``heldout/<domain>.raw.jsonl``) and :mod:`run_eval` (consumes
``heldout/<domain>.clean.jsonl``).  Without this step, ``run_eval``
silently assumes someone filtered the raw files by hand.

Usage::

    python -m mascarade_eval.filter_heldout --domain kicad
    python -m mascarade_eval.filter_heldout --domains kicad spice emc
    python -m mascarade_eval.filter_heldout            # all 10 domains

A drop log is written next to the clean file as
``heldout/<domain>.dropped.jsonl`` — one JSON line per discarded item
with the original prompt and an ``overlap`` field carrying the
maximum overlap-coefficient observed against the training corpus.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import DOMAINS, HELDOUT_DIR
from .leakage_check import _overlap, _shingles, normalize, filter_leaks
from .train_corpus import load_train_prompts


def _max_overlap(prompt: str, train_corpus: list[str]) -> float:
    """Maximum overlap coefficient of ``prompt`` vs any training item.

    Mirrors :func:`leakage_check.is_leak`'s near-duplicate metric so the
    drop log carries a comparable score. Exact-hash matches return 1.0.
    """
    cand_norm = normalize(prompt)
    cand_shingles = _shingles(prompt)
    best = 0.0
    for train_item in train_corpus:
        if normalize(train_item) == cand_norm:
            return 1.0
        ov = _overlap(cand_shingles, _shingles(train_item))
        if ov > best:
            best = ov
    return best


def filter_domain(
    domain: str,
    heldout_dir: Path = HELDOUT_DIR,
    overlap_threshold: float = 0.6,
    train_prompts_provider=load_train_prompts,
) -> tuple[int, int]:
    """Filter raw → clean for one domain. Returns (kept, dropped).

    ``train_prompts_provider`` is injected so tests can substitute a
    pure-stdlib callable and avoid the ``huggingface_hub`` round-trip.
    """
    raw_path = heldout_dir / f"{domain}.raw.jsonl"
    clean_path = heldout_dir / f"{domain}.clean.jsonl"
    dropped_path = heldout_dir / f"{domain}.dropped.jsonl"
    if not raw_path.exists():
        print(f"{domain}: no raw file at {raw_path} — skipping", file=sys.stderr)
        return (0, 0)

    items = [json.loads(line) for line in raw_path.read_text().splitlines() if line]
    if not items:
        clean_path.write_text("")
        dropped_path.write_text("")
        return (0, 0)

    train_corpus = train_prompts_provider(domain)
    clean, dropped = filter_leaks(items, train_corpus, overlap_threshold)

    clean_path.write_text(
        "\n".join(json.dumps(it, ensure_ascii=False) for it in clean),
        encoding="utf-8",
    )
    dropped_with_score = []
    for it in dropped:
        ov = _max_overlap(it.get("prompt", ""), train_corpus)
        dropped_with_score.append({**it, "overlap": round(ov, 4)})
    dropped_path.write_text(
        "\n".join(json.dumps(it, ensure_ascii=False) for it in dropped_with_score),
        encoding="utf-8",
    )
    return (len(clean), len(dropped))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Filter held-out raw → clean by removing items that "
                    "overlap the LoRA training corpus."
    )
    ap.add_argument("--domain", help="Single domain (shortcut for --domains).")
    ap.add_argument("--domains", nargs="*", default=None,
                    help="Domains to filter (default: all 10).")
    ap.add_argument("--overlap-threshold", type=float, default=0.6,
                    help="Overlap-coefficient cutoff (default: 0.6).")
    args = ap.parse_args()

    if args.domain and args.domains:
        ap.error("use --domain or --domains, not both")
    if args.domain:
        domains = [args.domain]
    elif args.domains is not None:
        domains = args.domains
    else:
        domains = list(DOMAINS)

    for domain in domains:
        kept, dropped = filter_domain(
            domain, overlap_threshold=args.overlap_threshold
        )
        print(f"{domain}: kept={kept} dropped={dropped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
