#!/usr/bin/env python3
"""Render updated README.md for the 4 audited mascarade-* datasets, on both
electron-rare/* and Ailiance-fr/* repos.

Strategy: pull the current README from HF, replace ONLY the warning bandeau
block AND the "Data sources" + "Statistics" sections with the audited numbers.
Everything else (Sample format, Usage, Citation, Related, scoreboard) is kept
intact.

Inputs:
    ~/eu-kiki-data/readme-pull/{org}__{ds}.md   (current README from HF)
    ~/eu-kiki-data/{ds}_audit_stats.json        (audit numbers)

Outputs:
    ~/eu-kiki-data/readme-rendered/{org}__{ds}.md  (updated, ready to upload)
"""
from __future__ import annotations
import json
import re
from pathlib import Path

HOME = Path.home()
PULL = HOME / "eu-kiki-data/readme-pull"
OUT = HOME / "eu-kiki-data/readme-rendered"
OUT.mkdir(parents=True, exist_ok=True)
STATS_DIR = HOME / "eu-kiki-data"

DATASETS = ["power", "dsp", "emc", "kicad"]
ORGS = ["electron-rare", "Ailiance-fr"]

# Optional file hint per dataset
FILENAMES = {
    "power": "power_chat.jsonl",
    "dsp": "dsp_chat.jsonl",
    "emc": "emc_chat.jsonl",
    "kicad": "kicad_chat.jsonl",
}


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def fmt_pct(p: float) -> str:
    return f"{p:.2f}".rstrip("0").rstrip(".") + " %"


def load_stats(ds: str) -> dict:
    if ds == "kicad":
        # Prefer the new kicad_audit_stats.json (full audit) if present;
        # else fall back to the POC stats finalize_enrichment block.
        p = STATS_DIR / "kicad_audit_stats.json"
        if p.exists():
            s = json.loads(p.read_text())
            return {
                "total": s["samples_total"],
                "detected": s["se_detected_heuristic"],
                "se_high": s["se_attributed_high_conf_(>=0.85)"],
                "se_accepted": s["se_attributed_accepted_(>=0.60)"],
                "not_found": s["se_not_found_on_api"],
                "low_conf": s["se_low_confidence_match"],
                "synth": s["no_attribution_needed_synthetic_or_unique"],
                "pct_se": s["fraction_se_real_pct"],
                "pct_not_found": s["fraction_not_found_pct"],
                "pct_synth": s["fraction_synthetic_pct"],
            }
        # fallback to POC
        p2 = STATS_DIR / "kicad_poc_stats.json"
        s = json.loads(p2.read_text())["finalize_enrichment"]
        return {
            "total": s["samples_total"],
            "detected": s["se_detected_heuristic"],
            "se_high": s["se_attributed_high_conf"],
            "se_accepted": s["se_attributed_high_conf"],
            "not_found": s["se_not_found_on_api"],
            "low_conf": s["se_low_confidence_match"],
            "synth": s["no_attribution_needed_synthetic_or_unique"],
            "pct_se": s["fraction_se_real_pct"],
            "pct_not_found": s["fraction_not_found_pct"],
            "pct_synth": s["fraction_synthetic_pct"],
        }
    p = STATS_DIR / f"{ds}_audit_stats.json"
    s = json.loads(p.read_text())
    return {
        "total": s["samples_total"],
        "detected": s["se_detected_heuristic"],
        "se_high": s["se_attributed_high_conf_(>=0.85)"],
        "se_accepted": s["se_attributed_accepted_(>=0.60)"],
        "not_found": s["se_not_found_on_api"],
        "low_conf": s["se_low_confidence_match"],
        "synth": s["no_attribution_needed_synthetic_or_unique"],
        "pct_se": s["fraction_se_real_pct"],
        "pct_not_found": s["fraction_not_found_pct"],
        "pct_synth": s["fraction_synthetic_pct"],
    }


def render_banner(s: dict) -> str:
    over = round(31.0 / max(s["pct_se"], 0.01), 1)
    return (
        f"> ✅ **ATTRIBUTION AUDIT COMPLETED (2026-05-11)**\n"
        f">\n"
        f"> Per-sample Stack Exchange Electronics attribution recovered via the SE\n"
        f"> `/search/advanced` + `/questions/{{id}}` API search :\n"
        f">\n"
        f"> - **{fmt_int(s['se_accepted'])} samples (~{fmt_pct(s['pct_se'])})** confirmed as Stack Exchange Electronics\n"
        f">   (CC-BY-SA-4.0) — fully attributed in `metadata.stack_exchange_attribution`\n"
        f">   (URL + author display name + author user_id + post_id + creation_date_unix + match_confidence ≥ 0.60).\n"
        f"> - **{fmt_int(s['not_found'])} samples (~{fmt_pct(s['pct_not_found'])})** marked `metadata.attribution_recovery=not_found_on_se`\n"
        f">   (stylistically resemble SE Electronics questions but no matching post returned\n"
        f">   by the SE `/search/advanced` API — probable synthetic/curated content).\n"
        f"> - **{fmt_int(s['low_conf'])} samples (~{fmt_pct(100.0*s['low_conf']/s['total'])})** marked `metadata.attribution_recovery=low_confidence_match`\n"
        f">   (API returned a candidate, but match score < 0.60 — kept as candidate URL only).\n"
        f"> - **{fmt_int(s['synth'])} samples (~{fmt_pct(s['pct_synth'])})** synthetic LLM-generated or unique to this dataset\n"
        f">   (no SE attribution required).\n"
        f">\n"
        f"> **Original heuristic estimate of \"~30 % SE\" was over-counted by ~{over}×** (style ≠ source).\n"
        f"> The heuristic flagged any first-person + question-mark + length-appropriate prompt as\n"
        f"> \"SE-style\", but only a small fraction of those flagged samples actually originate from\n"
        f"> a real SE Electronics post.\n"
        f">\n"
        f"> Methodology and full audit trail:\n"
        f"> [`docs/audit_mascarade_se_attribution.md`](https://github.com/ailiance/ailiance-bench/blob/main/docs/audit_mascarade_se_attribution.md)\n"
        f">\n"
        f"> If you author a Stack Exchange Electronics post and find your content in this dataset\n"
        f"> without proper attribution, contact `c.saillant@gmail.com` for prompt correction or\n"
        f"> removal. We honor [Article 4(3) DSM Directive](https://eur-lex.europa.eu/eli/dir/2019/790/oj) opt-outs."
    )


def render_data_sources(s: dict) -> str:
    return (
        "## Data sources (EU AI Act Template — AI Office, July 2025)\n"
        "\n"
        f"Distribution réelle des sources, mesurée le 2026-05-11 sur {fmt_int(s['total'])} samples :\n"
        "\n"
        "| Source                              | Samples | %       | Attribution status                              |\n"
        "|-------------------------------------|--------:|--------:|-------------------------------------------------|\n"
        f"| Stack Exchange Electronics          | {fmt_int(s['se_accepted']):>7} | {fmt_pct(s['pct_se']):>6} | Per-sample URL + author + post_id (CC-BY-SA-4.0)|\n"
        f"| Style SE / not found on API         | {fmt_int(s['not_found']):>7} | {fmt_pct(s['pct_not_found']):>6} | Marked `attribution_recovery=not_found_on_se`   |\n"
        f"| Low-confidence SE candidate         | {fmt_int(s['low_conf']):>7} | {fmt_pct(100.0*s['low_conf']/s['total']):>6} | Marked `attribution_recovery=low_confidence_match` |\n"
        f"| Synthetic LLM / unique content      | {fmt_int(s['synth']):>7} | {fmt_pct(s['pct_synth']):>6} | No external attribution required                |\n"
        "\n"
        "### Publicly available datasets\n"
        "None.\n"
        "\n"
        "### Web scraping\n"
        f"- **{fmt_pct(s['pct_se'])}** scraped from [Stack Exchange Electronics](https://electronics.stackexchange.com) (CC-BY-SA-4.0) — per-sample URL + author + `post_id` + `creation_date_unix` preserved in `metadata.stack_exchange_attribution`.\n"
        "\n"
        "### Synthetically generated\n"
        f"- **~{fmt_pct(s['pct_synth'])}** generated by LLM for domain-specific Q&A.\n"
        "\n"
        "### Licensed data\n"
        "None.\n"
    )


HEADING_RE = re.compile(r"^##\s", re.M)


def split_sections(md: str):
    """Return (head, sections) where head is everything before first '## ',
    and sections is a list of (heading_line, body) preserving order."""
    parts = []
    matches = list(HEADING_RE.finditer(md))
    if not matches:
        return md, []
    head = md[: matches[0].start()]
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        sec = md[start:end]
        # heading is the first line
        nl = sec.find("\n")
        heading_line = sec[: nl if nl >= 0 else len(sec)]
        body = sec[nl + 1:] if nl >= 0 else ""
        parts.append((heading_line, body))
    return head, parts


def replace_banner_in_head(head: str, banner: str) -> str:
    """Replace the existing > [!WARNING] block (or > ✅ block) that follows the
    main # heading with the new banner. The banner block is a contiguous run of
    lines that start with '>' or are blank between '>' lines, immediately
    after the '#' title line."""
    lines = head.splitlines()
    out_lines = []
    i = 0
    while i < len(lines):
        out_lines.append(lines[i])
        if lines[i].startswith("# ") and i + 1 < len(lines):
            # gather any leading blank lines, then the > block
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                out_lines.append(lines[j])
                j += 1
            if j < len(lines) and lines[j].startswith(">"):
                # skip the existing block until first non-'>' line (allow blank quote lines)
                while j < len(lines) and (lines[j].startswith(">") or (lines[j].strip() == "" and j + 1 < len(lines) and lines[j + 1].startswith(">"))):
                    j += 1
                # emit replacement
                out_lines.append(banner)
                # advance i to j-1 so next iter handles the rest
                i = j - 1
        i += 1
    return "\n".join(out_lines)


def render_readme(current_md: str, s: dict, ds: str) -> str:
    banner = render_banner(s)
    data_sources_md = render_data_sources(s)

    head, sections = split_sections(current_md)
    head_new = replace_banner_in_head(head, banner)

    # find / replace "## Data sources" section, keep everything else
    new_sections = []
    inserted_ds = False
    for heading, body in sections:
        h = heading.strip().lower()
        if h.startswith("## data sources"):
            # replace entire section
            new_sections.append((None, data_sources_md))
            inserted_ds = True
        else:
            new_sections.append((heading, body))
    if not inserted_ds:
        new_sections.insert(0, (None, data_sources_md))

    rebuilt = head_new.rstrip() + "\n\n"
    for heading, body in new_sections:
        if heading is None:
            rebuilt += body.rstrip() + "\n\n"
        else:
            rebuilt += heading + "\n" + body.rstrip() + "\n\n"
    return rebuilt.rstrip() + "\n"


def main() -> int:
    for ds in DATASETS:
        try:
            s = load_stats(ds)
        except FileNotFoundError:
            print(f"[skip] {ds}: stats not found")
            continue
        for org in ORGS:
            src = PULL / f"{org}__{ds}.md"
            if not src.exists():
                print(f"[skip] {org}/{ds}: pulled README not found")
                continue
            cur = src.read_text()
            new = render_readme(cur, s, ds)
            dst = OUT / f"{org}__{ds}.md"
            dst.write_text(new)
            print(f"[render] {org}/{ds} -> {dst}  ({len(new)} bytes)")
    print(f"[done] outputs at {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
