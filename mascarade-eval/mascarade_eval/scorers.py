"""Hybrid scoring: functional scorers where output is structured."""
from __future__ import annotations
import sys
from pathlib import Path

# Reuse the repo's functional scorers.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from bench_kicad_functional import score_dsl, score_pcb, score_spice  # noqa: E402, F401

# Domain -> functional scorer. None = no structural scorer; LLM-judge only.
DOMAIN_SCORER = {
    "kicad": score_dsl,      # also score_pcb for pcb-shaped tasks
    "spice": score_spice,
    "emc": score_spice,      # SPICE-shaped (emc-dsp-power family)
    "dsp": score_spice,
    "power": score_spice,
    "stm32": None,
    "embedded": None,
    "platformio": None,      # extend later: a .ini parser
    "freecad": None,
    "iot": None,
}


def functional_score(domain: str, generated: str, expected: str) -> dict | None:
    """Functional composite for `domain`, or None if no structural scorer."""
    scorer = DOMAIN_SCORER.get(domain)
    if scorer is None:
        return None
    return scorer(generated, expected)


def perplexity_score(reference: str, logprob_fn) -> float | None:
    """Secondary signal: perplexity of the reference answer under a model.

    `logprob_fn(text) -> list[float]` returns per-token logprobs. The
    chat-completions HTTP API does not expose logprobs, so this is
    best-effort: pass None (or a fn that raises) and it returns None —
    perplexity is a SECONDARY cross-check per the spec, never load-bearing.
    """
    if logprob_fn is None:
        return None
    try:
        lps = logprob_fn(reference)
    except Exception:  # noqa: BLE001
        return None
    if not lps:
        return None
    import math
    return math.exp(-sum(lps) / len(lps))
