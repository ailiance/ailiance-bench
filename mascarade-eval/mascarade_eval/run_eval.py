"""CLI: run the full mascarade eval pipeline, write the verdict report."""
from __future__ import annotations
import argparse
import json
from statistics import mean
from . import DOMAINS, RESULTS_DIR, HELDOUT_DIR, BASE_MODEL
from .runner import run_config
from .scorers import functional_score
from .judge import judge_one
from .aggregate import verdict, render_report

_ROUTE = {
    "faible": "B (data) -> C (training)",
    "a appris": "-",
    "domaine sans besoin de LoRA": "retirer la LoRA du routing",
    "basse confiance": "re-miner du held-out",
}


def _score_one(domain: str, item: dict) -> tuple[float | None, str | None]:
    """Composite [0,1] for one answered held-out item plus the scorer kind.

    Returns (score, kind) where kind is "functional" or "judge". When no
    score is produced, returns (None, None). The kind is what actually
    ran for THIS item — `functional_score` may return None mid-stream
    (parse_ok False) and fall through to the judge."""
    fn = functional_score(domain, item["answer"], item.get("reference", ""))
    if fn is not None:
        return float(fn["composite"]), "functional"
    score = judge_one(domain, item["prompt"], item["answer"])
    if score is None:
        return None, None
    return (score / 10.0), "judge"


def _dominant_kind(kinds: list[str]) -> str:
    """Pick the kind that scored the majority of items in a config.

    Per-item granularity (mix of functional + judge fallbacks) is
    collapsed to one label for the aggregate row. Ties break toward
    "judge" since that is the more permissive / less comparable scale,
    so the verdict caveat applies. Empty input -> "judge"."""
    if not kinds:
        return "judge"
    fn = sum(1 for k in kinds if k == "functional")
    return "functional" if fn > len(kinds) / 2 else "judge"


def eval_domain(domain: str) -> dict:
    """Run + score one domain; returns an aggregate row."""
    heldout = [json.loads(l) for l in
               (HELDOUT_DIR / f"{domain}.clean.jsonl").read_text().splitlines() if l]
    n = len(heldout)
    base = run_config(heldout, "base", BASE_MODEL)
    lora = run_config(heldout, "lora", f"ailiance-{domain}")
    base_pairs = [_score_one(domain, it) for it in base]
    lora_pairs = [_score_one(domain, it) for it in lora]
    base_scored = [s for s, _ in base_pairs if s is not None]
    lora_scored = [s for s, _ in lora_pairs if s is not None]
    kinds = [k for _, k in base_pairs + lora_pairs if k is not None]
    base_s = mean(base_scored) if base_scored else 0.0
    lora_s = mean(lora_scored) if lora_scored else 0.0
    v = verdict(base_s, lora_s, n)
    return {"domain": domain, "n": n, "base_score": base_s,
            "lora_score": lora_s, "verdict": v, "routed_to": _ROUTE[v],
            "scorer": _dominant_kind(kinds)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", nargs="*", default=list(DOMAINS))
    args = ap.parse_args()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for domain in args.domains:
        try:
            rows.append(eval_domain(domain))
        except Exception as e:  # noqa: BLE001 — per-domain isolation
            print(f"{domain}: FAILED {e!r}")
            rows.append({"domain": domain, "n": 0, "base_score": 0.0,
                         "lora_score": 0.0, "verdict": "basse confiance",
                         "routed_to": _ROUTE["basse confiance"],
                         "scorer": "judge"})
    (RESULTS_DIR / "mascarade-eval.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False))
    (RESULTS_DIR / "mascarade-eval-report.md").write_text(render_report(rows))
    print(f"report -> {RESULTS_DIR / 'mascarade-eval-report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
