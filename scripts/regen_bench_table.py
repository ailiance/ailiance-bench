#!/usr/bin/env python3
"""
Régénère ~/bench-results/BENCH_TABLE.md depuis ~/bench-results/all_models.txt.

Parse les sections `--- <model> / <task> ---` puis émet :
  - une table accuracy publique (gsm8k_cot strict/flex, arc_easy acc/acc_norm,
    mmlu, mmlu_pro_computer_science)
  - une table de perplexité par niche.

Les modèles inconnus sont automatiquement ajoutés ; ceux sans résultat affichent
"—" ou "TO" si timeout / no-result détecté.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

HOME = Path.home()
ALL_MODELS_TXT = HOME / "bench-results" / "all_models.txt"
TABLE_MD = HOME / "bench-results" / "BENCH_TABLE.md"

# Ordre fixe des modèles affichés ; les nouveaux qu'on découvre sont ajoutés à la fin
MODEL_ORDER = [
    "base", "eu-kiki", "mascarade",
    "gemma3-4b", "ministral-3b", "qwen-coder-3b", "llama-3.2-3b",
    "qwen3.5-9b", "jackrong-9b-opus", "helium-1-2b",
    "ministral-3-8b", "granite-4.1-3b",
]

MODEL_META = {
    "base":              ("Google",                     "Gemma Terms"),
    "eu-kiki":           ("electron-rare",              "CC-BY-SA-4.0"),
    "mascarade":         ("electron-rare",              "CC-BY-SA-4.0"),
    "gemma3-4b":         ("Google",                     "Gemma Terms"),
    "ministral-3b":      ("Mistral",                    "Apache 2.0"),
    "qwen-coder-3b":     ("Alibaba",                    "Apache 2.0"),
    "llama-3.2-3b":      ("Meta",                       "Llama 3.2"),
    "qwen3.5-9b":        ("Alibaba",                    "Apache 2.0"),
    "jackrong-9b-opus":  ("Jackrong (distill Opus)",    "Apache 2.0 + Anthropic AUP?"),
    "helium-1-2b":       ("Kyutai",                     "CC-BY 4.0"),
    "ministral-3-8b":    ("Mistral",                    "Apache 2.0"),
    "granite-4.1-3b":    ("IBM",                        "Apache 2.0"),
}

NICHES = ["spice", "stm32", "kicad", "embedded_iot", "emc_power"]

SECTION_RE = re.compile(r"^---\s+([^/]+?)\s+/\s+([^\s]+)\s+---\s*$")


def parse_all_models(text: str) -> dict[str, dict[str, dict]]:
    """Retourne {model: {task: {metric: value}}}.

    Une métrique spéciale "_status" peut valoir "TO" (timeout) ou "MISS"
    quand la section dit `_TIMEOUT_` ou `_NO RESULT_`.
    """
    results: dict[str, dict[str, dict]] = {}
    cur_model: str | None = None
    cur_task: str | None = None
    cur_buf: list[str] = []

    def flush():
        nonlocal cur_buf
        if cur_model is None or cur_task is None:
            cur_buf = []
            return
        body = "\n".join(cur_buf).strip()
        bucket = results.setdefault(cur_model, {}).setdefault(cur_task, {})
        if not body:
            cur_buf = []
            return
        if "_TIMEOUT" in body:
            bucket["_status"] = "TO"
        elif "_NO RESULT" in body or "_ERROR" in body or "_NO DATASET" in body:
            bucket["_status"] = "MISS"

        # Cherche métriques numériques  "acc,none": 0.66
        # Garde la PREMIÈRE occurrence (cas mmlu : top-level + sous-domaines mélangés)
        for m in re.finditer(r'"([^"]+)"\s*:\s*([0-9eE+\-.]+)', body):
            key, raw = m.group(1), m.group(2)
            if key in bucket:
                continue
            try:
                bucket[key] = float(raw)
            except ValueError:
                pass

        # Perplexity: 21.754 ± 0.789
        m = re.search(r"Perplexity:\s*([0-9.]+)\s*±\s*([0-9.]+)", body)
        if m:
            bucket["ppl"] = float(m.group(1))
            bucket["ppl_se"] = float(m.group(2))

        cur_buf = []

    for line in text.splitlines():
        match = SECTION_RE.match(line.strip())
        if match:
            flush()
            cur_model = match.group(1).strip()
            cur_task = match.group(2).strip()
        else:
            cur_buf.append(line)
    flush()
    return results


def fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.1f}"


def cell(bucket: dict | None, key: str) -> str:
    if not bucket:
        return "—"
    if "_status" in bucket and key not in bucket:
        return "TO" if bucket["_status"] == "TO" else "—"
    if key not in bucket:
        return "—"
    return fmt_pct(bucket[key])


def cell_ppl(bucket: dict | None) -> str:
    if not bucket:
        return "—"
    if "_status" in bucket and "ppl" not in bucket:
        return "TO" if bucket["_status"] == "TO" else "—"
    if "ppl" not in bucket:
        return "—"
    return f"{bucket['ppl']:.2f}"


def build_markdown(results: dict[str, dict[str, dict]]) -> str:
    # Combine ordre canonique + nouveaux modèles
    seen = set(MODEL_ORDER)
    extras = [m for m in results.keys() if m not in seen]
    models = MODEL_ORDER + extras

    today = dt.date.today().isoformat()
    out: list[str] = []
    out.append(f"# Bench multi-modèles consolidé (final, {today})")
    out.append("")
    out.append("## Public benchs (% accuracy, ↑ better)")
    out.append("")
    out.append("| Model | Provider | License | gsm-S | gsm-F | arc | arc-n | mmlu | mmluPro |")
    out.append("|---|---|---|---:|---:|---:|---:|---:|---:|")
    for m in models:
        meta = MODEL_META.get(m, ("?", "?"))
        gsm = results.get(m, {}).get("gsm8k_cot", {})
        arc = results.get(m, {}).get("arc_easy", {})
        mmlu = results.get(m, {}).get("mmlu", {})
        mmlupro = results.get(m, {}).get("mmlu_pro_computer_science", {})

        out.append(
            f"| **{m}** | {meta[0]} | {meta[1]} | "
            f"{cell(gsm, 'exact_match,strict-match')} | "
            f"{cell(gsm, 'exact_match,flexible-extract')} | "
            f"{cell(arc, 'acc,none')} | "
            f"{cell(arc, 'acc_norm,none')} | "
            f"{cell(mmlu, 'acc,none')} | "
            f"{cell(mmlupro, 'exact_match,custom-extract')} |"
        )
    out.append("")
    out.append("## Niches perplexity (lower=better)")
    out.append("")
    out.append("| Model | " + " | ".join(NICHES) + " |")
    out.append("|---|" + "|".join(["---:"] * len(NICHES)) + "|")
    for m in models:
        cells = []
        for niche in NICHES:
            bucket = results.get(m, {}).get(f"ppl-{niche}", {})
            cells.append(cell_ppl(bucket))
        out.append(f"| **{m}** | " + " | ".join(cells) + " |")
    out.append("")
    return "\n".join(out)


def main() -> int:
    text = ALL_MODELS_TXT.read_text()
    results = parse_all_models(text)
    md = build_markdown(results)
    TABLE_MD.write_text(md)
    print(f"Wrote {TABLE_MD}")
    print(f"Models found: {sorted(results.keys())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
