#!/usr/bin/env python3
"""Replace `## PARTIAL ATTRIBUTION DISCLOSURE` block in LoRA READMEs that
inherit the old warning from a now-audited mascarade-* dataset.

Targets explicitly identified to contain the legacy disclosure block:
    - apertus-emc-dsp-power-lora
    - apertus-emc-dsp-power-curriculum-lora

Other LoRA cards (qwen3-4b-mascarade-{power,dsp,emc,kicad}-lora,
devstral-kicad-*-lora, apertus-electronics-hw-lora) did not contain the
warning per the audit pull, so no update needed.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

HOME = Path.home()
PULL = HOME / "eu-kiki-data/lora-pull"
OUT = HOME / "eu-kiki-data/lora-rendered"
OUT.mkdir(parents=True, exist_ok=True)
STATS_DIR = HOME / "eu-kiki-data"

TARGETS = {
    "apertus-emc-dsp-power-lora": ["emc", "dsp", "power"],
    "apertus-emc-dsp-power-curriculum-lora": ["emc", "dsp", "power"],
}


def load_pct_se(ds: str) -> float:
    p = STATS_DIR / f"{ds}_audit_stats.json"
    s = json.loads(p.read_text())
    return float(s["fraction_se_real_pct"])


def render_new_block(domains: list[str]) -> str:
    pcts = {d: load_pct_se(d) for d in domains}
    lo = min(pcts.values())
    hi = max(pcts.values())
    rng = f"~{lo:.2f}–{hi:.2f} %" if hi - lo > 0.05 else f"~{lo:.2f} %"
    ds_list = ", ".join(
        f"[`Ailiance-fr/mascarade-{d}-dataset`](https://huggingface.co/datasets/Ailiance-fr/mascarade-{d}-dataset) ({pcts[d]:.2f}% SE)"
        for d in domains
    )
    return (
        "> ## ✅ Training data attribution audited (2026-05-11)\n"
        ">\n"
        f"> Trained on {ds_list}.\n"
        f"> Per-sample Stack Exchange Electronics attribution recovered via SE API search:\n"
        f"> only **{rng}** of samples per dataset are from Stack Exchange Electronics\n"
        "> (now fully attributed in `metadata.stack_exchange_attribution` — URL + author + post_id + creation_date).\n"
        ">\n"
        "> **Original heuristic estimate of \"~30 % SE\" was over-counted by ~6–7×** (style ≠ source).\n"
        "> See [audit trail](https://github.com/ailiance/ailiance-bench/blob/main/docs/audit_mascarade_se_attribution.md)\n"
        "> for the methodology (`/search/advanced` + body match ≥ 0.60).\n"
        ">\n"
        "> Remaining content is either (a) style-resembling SE but not findable on the API\n"
        "> (marked `attribution_recovery=not_found_on_se`, probable synthetic) or (b) synthetic LLM-generated."
    )


# match the legacy block: starts at "> ## PARTIAL ATTRIBUTION DISCLOSURE",
# ends at the first non-quoted blank line followed by a "## " section header
BLOCK_RE = re.compile(
    r"^> ## PARTIAL ATTRIBUTION DISCLOSURE\s*$(?:\n>[^\n]*)*",
    re.M,
)


def patch(md: str, domains: list[str]) -> str:
    new_block = render_new_block(domains)
    new_md, count = BLOCK_RE.subn(new_block, md, count=1)
    if count == 0:
        print("[warn] no PARTIAL ATTRIBUTION block found; no change")
        return md
    return new_md


def main() -> int:
    for name, domains in TARGETS.items():
        src = PULL / f"{name}.md"
        if not src.exists():
            print(f"[skip] {name}: pulled README missing")
            continue
        cur = src.read_text()
        new = patch(cur, domains)
        dst = OUT / f"{name}.md"
        dst.write_text(new)
        print(f"[render] {name} -> {dst}  ({len(new)} bytes, was {len(cur)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
