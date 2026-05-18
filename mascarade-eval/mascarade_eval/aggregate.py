"""Combine per-item scores into a per-LoRA verdict + markdown report."""
from __future__ import annotations
from . import MIN_HELDOUT

_LEARNED_MARGIN = 0.15   # lora - base >= this => learned
_BASE_HIGH = 0.85        # base already this good => no LoRA needed


def verdict(base_score: float, lora_score: float, n: int) -> str:
    """Four-way verdict from mean base/LoRA scores on the held-out."""
    if n < MIN_HELDOUT:
        return "basse confiance"
    if base_score >= _BASE_HIGH and lora_score - base_score < _LEARNED_MARGIN:
        return "domaine sans besoin de LoRA"
    if lora_score - base_score >= _LEARNED_MARGIN:
        return "a appris"
    return "faible"


_CAVEAT = (
    "> ⚠ Les scores des domaines `functional` et `judge` ne sont pas "
    "directement comparables — le verdict « a appris » s'applique "
    "**par domaine**, pas inter-domaines. La marge `lora - base >= "
    f"{_LEARNED_MARGIN:.2f}` est appliquée à l'échelle propre de chaque "
    "scorer, et les deux échelles n'ont ni la même variance ni le même "
    "plancher (le scorer fonctionnel pénalise durement le `parse_ok` "
    "False ; le LLM-judge sature plus vite vers 0.7–0.8)."
)


def render_report(rows: list[dict]) -> str:
    """rows: [{domain, n, base_score, lora_score, verdict, routed_to, scorer}].

    `scorer` ∈ {"functional", "judge"} ; absent rows default to "judge".
    """
    lines = ["# Mascarade Eval — verdict par LoRA", "",
             "| Domaine | n | base | +LoRA | Scorer | Verdict | Aiguillage |",
             "|---|--:|--:|--:|---|---|---|"]
    for r in rows:
        scorer = r.get("scorer", "judge")
        lines.append(
            f"| {r['domain']} | {r['n']} | {r['base_score']:.3f} | "
            f"{r['lora_score']:.3f} | {scorer} | {r['verdict']} | "
            f"{r['routed_to']} |")
    lines.extend(["", _CAVEAT])
    return "\n".join(lines) + "\n"
