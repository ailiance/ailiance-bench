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


def render_report(rows: list[dict]) -> str:
    """rows: [{domain, n, base_score, lora_score, verdict, routed_to}]."""
    lines = ["# Mascarade Eval — verdict par LoRA", "",
             "| Domaine | n | base | +LoRA | Verdict | Aiguillage |",
             "|---|--:|--:|--:|---|---|"]
    for r in rows:
        lines.append(
            f"| {r['domain']} | {r['n']} | {r['base_score']:.3f} | "
            f"{r['lora_score']:.3f} | {r['verdict']} | {r['routed_to']} |")
    return "\n".join(lines) + "\n"
