#!/usr/bin/env python3
"""
add_bench_section_to_cards.py — Add a "Benchmark / Training metrics" section to
every Ailiance-fr model card on HuggingFace that doesn't already have one.

Idempotent: skips models whose README already contains a "## Benchmark" or
"## Training metrics" section.

Data sources:
- electron-bench/scripts/data/training_metrics.json (extracted from Studio logs)
- Gemma champions are hardcoded (already benched via electron-bench pipeline)

Usage:
    python3 add_bench_section_to_cards.py [--dry-run] [--filter PATTERN] [--limit N]

Environment:
    HF_TOKEN — write token (or read from ~/.cache/huggingface/token)

Constraints:
- 2s sleep between uploads (rate-limit safety)
- Idempotent: skip if "## Benchmark" or "## Training metrics" already present
- Bash 3.2 compat (this script is Python only)
- Does NOT modify .safetensors / adapter weights
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

try:
    from huggingface_hub import HfApi, hf_hub_download
    from huggingface_hub.utils import EntryNotFoundError
except ImportError:
    print("ERR: pip install huggingface_hub", file=sys.stderr)
    sys.exit(1)


HF_ORG = "Ailiance-fr"
BENCH_MATRIX_URL = (
    "https://github.com/ailiance/ailiance-bench/"
    "blob/main/bench-results/compare_base_vs_lora.md"
)
BENCH_ISSUES_URL = "https://github.com/ailiance/ailiance-bench/issues"

SCRIPT_DIR = Path(__file__).resolve().parent
METRICS_FILE = SCRIPT_DIR / "data" / "training_metrics.json"

# Models already benched through electron-bench (Phase 1-6 of compare_base_vs_lora)
GEMMA_CHAMPIONS = {
    "gemma-4-E4B-eukiki-lora": {
        "label": "Gemma eukiki champion",
        "highlights": [
            ("P1 DSL syntax", "+55 pts"),
            ("P1 PCB syntax", "+42 pts"),
            ("SPICE simulation", "+25 pts"),
            ("P3 extraction", "+38 pts"),
        ],
    },
    "gemma-4-E4B-mascarade-lora": {
        "label": "Gemma extraction champion",
        "highlights": [
            ("P3 extraction", "+48 pts"),
        ],
    },
    "gemma-4-E4B-kicad9plus-lora": {
        "label": "Gemma KiCad 9+ specialist",
        "highlights": [
            ("KiCad 9+ DSL", "trained 500 iters"),
        ],
    },
    "gemma-4-E4B-aggro-test-lora": {
        "label": "Gemma aggressive-LR test run",
        "highlights": [
            ("status", "experimental"),
        ],
    },
}

# Base-model lookup for roadmap text
BASE_MODELS = {
    "apertus": "swiss-ai/Apertus-70B-Instruct-2509",
    "devstral": "mistralai/Devstral-Small-2-24B-Instruct-2512",
    "eurollm": "utter-project/EuroLLM-9B-Instruct",
    "qwen3": "Qwen/Qwen3-4B",
    "gemma": "lmstudio-community/gemma-4-E4B-it-MLX-4bit",
}


def family(model_name: str) -> str:
    return model_name.split("-")[0].lower()


def metric_key_for_model(model_name: str) -> str:
    """Map a HF model id to a key in training_metrics.json."""
    # strip trailing "-lora"
    if model_name.endswith("-lora"):
        return model_name[: -len("-lora")]
    return model_name


def load_metrics() -> dict[str, Any]:
    if not METRICS_FILE.exists():
        return {}
    return json.loads(METRICS_FILE.read_text())


def has_bench_section(readme: str) -> bool:
    """Detect existing benchmark / training-metrics section (idempotency)."""
    patterns = [
        r"^##\s+Benchmark",
        r"^##\s+Bench results",
        r"^##\s+Bench context",
        r"^##\s+Training metrics",
        r"^##\s+Benchmark on production tasks",
        r"^##\s+Benchmark roadmap",
    ]
    for p in patterns:
        if re.search(p, readme, re.MULTILINE | re.IGNORECASE):
            return True
    return False


def build_metrics_section(metrics: dict[str, Any]) -> str:
    """Produce a 'Training metrics' table from extracted log data."""
    rows = []
    if metrics.get("final_train_loss") is not None:
        rows.append(("Final train loss", f"{metrics['final_train_loss']:.3f}"))
    if metrics.get("final_val_loss") is not None:
        rows.append(("Final validation loss", f"{metrics['final_val_loss']:.3f}"))
    if metrics.get("initial_val_loss") is not None and metrics.get("final_val_loss") is not None:
        delta = metrics["initial_val_loss"] - metrics["final_val_loss"]
        rows.append(("Val loss reduction", f"{delta:+.3f} (from {metrics['initial_val_loss']:.3f})"))
    if metrics.get("iters_done"):
        rows.append(("Iterations completed", str(metrics["iters_done"])))
    if metrics.get("trainable_pct"):
        tp = metrics.get("trainable_params")
        tot = metrics.get("total_params")
        if tp and tot:
            rows.append(("Trainable parameters", f"{metrics['trainable_pct']} ({tp} / {tot})"))
        else:
            rows.append(("Trainable parameters", metrics["trainable_pct"]))

    if not rows:
        return ""

    table = "| Metric | Value |\n|---|---:|\n"
    for label, val in rows:
        table += f"| {label} | {val} |\n"

    return f"""## Training metrics

Extracted from training log (`{metrics.get('log_source', 'Studio batch log')}`):

{table}
> Validation loss is measured every 200 iterations on a held-out split of the
> training corpus (`val_batches=5`, `mlx-lm` LoRA trainer).
"""


def build_bench_pointer_section(base_family: str) -> str:
    """Pointer to Gemma reference benchmarks (until per-base bench exists)."""
    return f"""## Benchmark on production tasks

This LoRA has **not yet been evaluated** through the
[`electron-bench`]({BENCH_MATRIX_URL.rsplit('/', 2)[0]}) functional benchmark
pipeline. The current pipeline targets the `gemma-4-E4B` base only; support for
the **{base_family}** base is on the roadmap
([open issues]({BENCH_ISSUES_URL})).

For a comparable reference matrix on a related domain (electronics, embedded,
KiCad), see the Gemma champions:

| Adapter | Highlights |
|---|---|
| [`Ailiance-fr/gemma-4-E4B-eukiki-lora`](https://huggingface.co/Ailiance-fr/gemma-4-E4B-eukiki-lora) | +55 P1-DSL, +42 P1-PCB, +25 SPICE, +38 P3 |
| [`Ailiance-fr/gemma-4-E4B-mascarade-lora`](https://huggingface.co/Ailiance-fr/gemma-4-E4B-mascarade-lora) | +48 P3 extraction |

Full base-vs-LoRA matrix: [`compare_base_vs_lora.md`]({BENCH_MATRIX_URL}).
"""


def build_roadmap_section(base_family: str, base_model: str) -> str:
    """Used when no training metrics could be extracted from logs."""
    return f"""## Benchmark roadmap

This LoRA has **not yet been evaluated** through `electron-bench` (the current
pipeline supports `gemma-4-E4B` base only). Training was completed with the
standard `mlx-lm` LoRA trainer (rank 16, alpha 32, scale 2.0, AdamW
LR 1e-5, 500 iters) — full hyperparameters are in the `Training` table above.

Planned evaluations:

- Perplexity on the validation split of the training data
- Functional benchmark on **{base_family}**-specific tasks
- Comparison vs base `{base_model}`

Track progress: [ailiance-bench issues]({BENCH_ISSUES_URL}).

For reference benchmarks on the `gemma-4-E4B` base, see the
[base-vs-LoRA matrix]({BENCH_MATRIX_URL}).
"""


def build_gemma_champion_section(model_name: str) -> str:
    info = GEMMA_CHAMPIONS[model_name]
    rows = "\n".join(f"| {k} | {v} |" for k, v in info["highlights"])
    return f"""## Benchmark on production tasks

**{info['label']}** — evaluated through the
[`electron-bench`]({BENCH_MATRIX_URL.rsplit('/', 2)[0]}) functional pipeline
(Phases P1 → P6, base vs LoRA).

| Task | Result |
|---|---|
{rows}

Full base-vs-LoRA matrix (all phases, all adapters):
[`compare_base_vs_lora.md`]({BENCH_MATRIX_URL}).
"""


def build_section_for_model(model_name: str, metrics_lookup: dict[str, Any]) -> str:
    if model_name in GEMMA_CHAMPIONS:
        return build_gemma_champion_section(model_name)

    fam = family(model_name)
    base = BASE_MODELS.get(fam, "unknown")

    # Look up metrics by stripped key
    key = metric_key_for_model(model_name)
    metrics = metrics_lookup.get(key)

    parts = []
    if metrics:
        parts.append(build_metrics_section(metrics))
        parts.append(build_bench_pointer_section(fam))
    else:
        parts.append(build_roadmap_section(fam, base))
    return "\n".join(p for p in parts if p)


OUR_SECTION_HEADERS = (
    "## Training metrics",
    "## Benchmark on production tasks",
    "## Benchmark roadmap",
)


def strip_our_sections(readme: str) -> str:
    """Remove any of our previously-injected sections (for --force-replace)."""
    lines = readme.split("\n")
    out_lines = []
    skip = False
    for line in lines:
        if line.startswith("## "):
            if any(line.strip().startswith(h) for h in OUR_SECTION_HEADERS):
                skip = True
                continue
            else:
                skip = False
        if not skip:
            out_lines.append(line)
    return "\n".join(out_lines)


def insert_section(readme: str, section: str, force_replace: bool = False) -> str:
    """Insert section before '## License', or before '## Citation', or at end."""
    if force_replace:
        readme = strip_our_sections(readme)
    elif has_bench_section(readme):
        return readme  # idempotent
    for marker in ["## License", "## Citation", "## Related"]:
        idx = readme.find(f"\n{marker}")
        if idx != -1:
            return readme[: idx + 1] + section + "\n" + readme[idx + 1 :]
    # fallback: append
    return readme.rstrip() + "\n\n" + section + "\n"


def list_models(api: HfApi, token: str) -> list[str]:
    models = api.list_models(author=HF_ORG, token=token)
    return [m.id for m in models]


def fetch_readme(api: HfApi, repo_id: str, token: str) -> str | None:
    try:
        path = hf_hub_download(
            repo_id=repo_id,
            filename="README.md",
            token=token,
            force_download=True,
        )
        return Path(path).read_text()
    except EntryNotFoundError:
        return None
    except Exception as e:
        print(f"  fetch err: {e}", file=sys.stderr)
        return None


def upload_readme(api: HfApi, repo_id: str, content: str, token: str) -> bool:
    try:
        api.upload_file(
            path_or_fileobj=content.encode("utf-8"),
            path_in_repo="README.md",
            repo_id=repo_id,
            token=token,
            commit_message="docs: add Benchmark / Training metrics section",
        )
        return True
    except Exception as e:
        print(f"  upload err: {e}", file=sys.stderr)
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Show what would change without uploading")
    ap.add_argument("--filter", help="Process only repos whose id contains this substring")
    ap.add_argument("--limit", type=int, default=None, help="Stop after N uploads")
    ap.add_argument("--family", help="Only process this family (apertus|devstral|eurollm|qwen3|gemma|router)")
    ap.add_argument("--force-replace", action="store_true",
                    help="Replace existing bench section (matches our own markers only).")
    args = ap.parse_args()

    token = os.environ.get("HF_TOKEN")
    if not token:
        token_path = Path.home() / ".cache" / "huggingface" / "token"
        if token_path.exists():
            token = token_path.read_text().strip()
    if not token:
        print("ERR: no HF token", file=sys.stderr)
        return 2

    metrics_lookup = load_metrics()
    print(f"loaded {len(metrics_lookup)} metric entries from {METRICS_FILE.name}")

    api = HfApi()
    models = list_models(api, token)
    models = sorted(models)
    print(f"found {len(models)} models in {HF_ORG}")

    if args.family:
        models = [m for m in models if family(m.split("/")[1]) == args.family]
    if args.filter:
        models = [m for m in models if args.filter in m]

    print(f"processing {len(models)} models")

    summary = {"updated": [], "skipped_existing": [], "skipped_router": [], "errors": []}

    for full_id in models:
        name = full_id.split("/")[1]

        # Skip routers (not LoRA adapters)
        if name.startswith("router-") or name == "devstral-v3-sft":
            summary["skipped_router"].append(full_id)
            print(f"[skip-non-lora] {full_id}")
            continue

        readme = fetch_readme(api, full_id, token)
        if readme is None:
            print(f"[no-readme] {full_id}")
            summary["errors"].append((full_id, "no readme"))
            continue

        if has_bench_section(readme) and not args.force_replace:
            print(f"[already-has-bench] {full_id}")
            summary["skipped_existing"].append(full_id)
            continue

        section = build_section_for_model(name, metrics_lookup)
        if not section:
            print(f"[no-section-built] {full_id}")
            summary["errors"].append((full_id, "no section"))
            continue

        new_readme = insert_section(readme, section, force_replace=args.force_replace)
        if new_readme == readme:
            print(f"[unchanged] {full_id}")
            continue

        if args.dry_run:
            print(f"[dry-run-would-update] {full_id} (+{len(new_readme) - len(readme)} chars)")
            summary["updated"].append(full_id)
            continue

        ok = upload_readme(api, full_id, new_readme, token)
        if ok:
            summary["updated"].append(full_id)
            print(f"[updated] {full_id}")
            time.sleep(2)  # rate-limit safety
        else:
            summary["errors"].append((full_id, "upload failed"))

        if args.limit and len(summary["updated"]) >= args.limit:
            print(f"hit limit {args.limit}, stopping")
            break

    print("\n=== summary ===")
    for k, v in summary.items():
        print(f"{k}: {len(v)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
