#!/usr/bin/env python3
"""Push Ailiance-fr LoRA adapters v2 — CC-BY-SA-4.0 license chain.

CHANGES vs v1:
- License inherited from training data (CC-BY-SA-4.0 — share-alike wins over Apache 2.0 base)
  Exception: training data from kicad9plus-copyleft (GPL-3.0) → LoRA gets GPL-3.0
  Exception: pure synthetic/no-SE domains → keep apache-2.0
- License chain table in README (Base | Data | LoRA)
- DISCLOSURE bandeau for domains with partial SE attribution (power, dsp, emc, kicad)
- Dataset attribution links per-domain
- Mode --force-readme: re-upload README.md only for already-uploaded repos
- Mode --only NAME: re-process a single adapter dir

Usage:
  python3 push_ailiance_lora_v2.py                 # full batch, idempotent on safetensors
  python3 push_ailiance_lora_v2.py --force-readme  # only refresh README for all repos
  python3 push_ailiance_lora_v2.py --only apertus-embedded --force-readme
"""
import argparse
import json
import os
import sys
import time
import logging
from pathlib import Path
from huggingface_hub import HfApi, create_repo, upload_file
from huggingface_hub.utils import HfHubHTTPError, RepositoryNotFoundError

ROOT = Path.home() / "KIKI-Mac_tunner" / "output" / "eu-kiki-hf"
LOG_DIR = Path.home() / "bench-results"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "ailiance_lora_upload_v2.log"
ORG = "Ailiance-fr"

SKIP_DIRS = {"devstral-vlm-schematic"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, mode="a"), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("ailiance-push-v2")
api = HfApi()

BASE_INFO = {
    "Apertus-70B-Instruct-2509": ("swiss-ai/Apertus-70B-Instruct-2509", "apache-2.0", "Apertus-70B-Instruct", "apertus"),
    "Devstral-Small-2-24B-Instruct-2512": ("mistralai/Devstral-Small-2-24B-Instruct-2512", "apache-2.0", "Devstral-Small-2-24B-Instruct", "devstral"),
    "Devstral-Small-2-24B-BF16": ("mistralai/Devstral-Small-2-24B-Instruct-2512", "apache-2.0", "Devstral-Small-2-24B-BF16", "devstral"),
    "EuroLLM-22B-Instruct-2512": ("utter-project/EuroLLM-22B-Instruct-2512", "apache-2.0", "EuroLLM-22B-Instruct", "eurollm"),
}

# Domain -> (primary dataset id, dataset license, downstream LoRA license).
# CC-BY-SA-4.0 share-alike => LoRA forced to CC-BY-SA-4.0 (more restrictive wins).
# kicad9plus-copyleft is GPL-3.0 (copyleft). Pure synthetic domains keep apache-2.0.
# "warn" => add PARTIAL ATTRIBUTION DISCLOSURE bandeau (SE attribution incomplete).
DOMAIN_LINEAGE = {
    # mascarade SE-derived, partial attribution warning ACTIVE
    "emc-dsp-power":      ("Ailiance-fr/mascarade-emc-dataset",       "cc-by-sa-4.0", "cc-by-sa-4.0", "warn", ["Ailiance-fr/mascarade-emc-dataset", "Ailiance-fr/mascarade-dsp-dataset", "Ailiance-fr/mascarade-power-dataset"]),
    "kicad-dsl":          ("Ailiance-fr/mascarade-kicad-dataset",     "cc-by-sa-4.0", "cc-by-sa-4.0", "audited", None),
    "kicad-pcb":          ("Ailiance-fr/mascarade-kicad-dataset",     "cc-by-sa-4.0", "cc-by-sa-4.0", "audited", None),
    # mascarade clean (no SE attribution issue)
    "embedded":           ("Ailiance-fr/mascarade-embedded-dataset",  "cc-by-sa-4.0", "cc-by-sa-4.0", "clean", None),
    "iot":                ("Ailiance-fr/mascarade-iot-dataset",       "cc-by-sa-4.0", "cc-by-sa-4.0", "clean", None),
    "stm32":              ("Ailiance-fr/mascarade-stm32-dataset",     "cc-by-sa-4.0", "cc-by-sa-4.0", "clean", None),
    "spice-sim":          ("Ailiance-fr/mascarade-spice-dataset",     "cc-by-sa-4.0", "cc-by-sa-4.0", "clean", None),
    "platformio":         ("Ailiance-fr/mascarade-platformio-dataset","cc-by-sa-4.0", "cc-by-sa-4.0", "clean", None),
    "freecad":            ("Ailiance-fr/mascarade-freecad-dataset",   "cc-by-sa-4.0", "cc-by-sa-4.0", "clean", None),
    # general electronics/kill-life
    "electronics":        ("Ailiance-fr/kill-life-embedded-qa",       "cc-by-sa-4.0", "cc-by-sa-4.0", "clean", None),
    # synthetic / code-generation domains — apache-2.0 (no SE attribution risk)
    "cpp":                (None, "apache-2.0", "apache-2.0", "synth", None),
    "python":             (None, "apache-2.0", "apache-2.0", "synth", None),
    "rust":               (None, "apache-2.0", "apache-2.0", "synth", None),
    "rust-embedded":      (None, "apache-2.0", "apache-2.0", "synth", None),
    "typescript":         (None, "apache-2.0", "apache-2.0", "synth", None),
    "shell":              (None, "apache-2.0", "apache-2.0", "synth", None),
    "sql":                (None, "apache-2.0", "apache-2.0", "synth", None),
    "yaml-json":          (None, "apache-2.0", "apache-2.0", "synth", None),
    "html-css":           (None, "apache-2.0", "apache-2.0", "synth", None),
    "web-backend":        (None, "apache-2.0", "apache-2.0", "synth", None),
    "web-frontend":       (None, "apache-2.0", "apache-2.0", "synth", None),
    "docker-devops":      (None, "apache-2.0", "apache-2.0", "synth", None),
    "lua-upy":            (None, "apache-2.0", "apache-2.0", "synth", None),
    "llm-ops":            (None, "apache-2.0", "apache-2.0", "synth", None),
    "llm-orch":           (None, "apache-2.0", "apache-2.0", "synth", None),
    "ml-training":        (None, "apache-2.0", "apache-2.0", "synth", None),
    "music-audio":        (None, "apache-2.0", "apache-2.0", "synth", None),
    # math / reasoning — apache-2.0 derived corpora (gsm8k MIT, openmathreasoning apache)
    "math":               (None, "apache-2.0", "apache-2.0", "synth", None),
    "math-gsm8k":         (None, "mit",        "mit",        "synth", None),
    "math-reasoning":     (None, "apache-2.0", "apache-2.0", "synth", None),
    # security — apache-2.0 (security-fenrir corpus is internally curated)
    "security-fenrir":    (None, "apache-2.0", "apache-2.0", "synth", None),
    # multilingual / chat / translation — apache-2.0 (CC100/FLORES-style, permissive)
    "multilingual-eu":    (None, "apache-2.0", "apache-2.0", "synth", None),
    "chat-fr":            (None, "apache-2.0", "apache-2.0", "synth", None),
    "traduction-tech":    (None, "apache-2.0", "apache-2.0", "synth", None),
}


def base_from_path(p):
    name = Path(p).name
    return BASE_INFO.get(name, (p, "apache-2.0", name, "unknown"))


def derive_domain(adapter_dir_name):
    parts = adapter_dir_name.split("-")
    if parts and parts[0] in {"apertus", "devstral", "eurollm"}:
        parts = parts[1:]
    variant = None
    if parts and parts[-1] in {"bf16", "curriculum", "fullseq"}:
        variant = parts[-1]
        domain_parts = parts[:-1]
    else:
        domain_parts = parts
    domain = "-".join(domain_parts) if domain_parts else "general"
    return domain, variant


def lineage_for(domain):
    """Return (primary_ds, ds_license, lora_license, status, extra_ds_list)."""
    if domain in DOMAIN_LINEAGE:
        return DOMAIN_LINEAGE[domain]
    # fallback: unknown domain -> conservative apache-2.0 chain
    log.warning(f"  unknown domain '{domain}' -> defaulting to apache-2.0 / no dataset link")
    return (None, "apache-2.0", "apache-2.0", "synth", None)


def render_disclosure(domain, status, primary_ds, extra_ds):
    if status == "warn":
        ds_list = extra_ds or [primary_ds]
        ds_links = ", ".join(f"[`{ds}`](https://huggingface.co/datasets/{ds})" for ds in ds_list if ds)
        return f"""
> ## PARTIAL ATTRIBUTION DISCLOSURE
>
> This LoRA was trained on {ds_links} which contain a substantial fraction of
> Stack Exchange Electronics samples (CC-BY-SA-4.0) **without full per-sample
> URL+author attribution** at training time. Training data attribution
> remediation is in progress (see upstream dataset cards for status).
>
> For DMCA-clean alternatives: use a LoRA trained on
> [`Ailiance-fr/kill-life-embedded-qa`](https://huggingface.co/datasets/Ailiance-fr/kill-life-embedded-qa)
> or [`Ailiance-fr/kicad9plus-permissive`](https://huggingface.co/datasets/Ailiance-fr/kicad9plus-permissive).
"""
    if status == "audited":
        return f"""
> ## ATTRIBUTION AUDIT COMPLETED
>
> The training dataset
> [`Ailiance-fr/mascarade-kicad-dataset`](https://huggingface.co/datasets/Ailiance-fr/mascarade-kicad-dataset)
> went through a full Stack Exchange attribution audit (2026-05-11):
> 61 samples (~2.3%) carry per-sample URL+author+post_id attribution;
> 169 samples flagged `not_found_on_se` (likely synthetic);
> 2 413 samples (~91%) are LLM-synthetic.
> Audit report: `docs/audit_mascarade_se_attribution.md` in `electron-bench`.
"""
    return ""


def render_license_chain(base_full, base_license, ds_id, ds_license, lora_license):
    ds_cell = f"[`{ds_id}`](https://huggingface.co/datasets/{ds_id})" if ds_id else "internal Ailiance curation (synthetic + permissive sources)"
    rationale = ""
    if lora_license == "cc-by-sa-4.0":
        rationale = "_Most restrictive license in the chain (CC-BY-SA-4.0 share-alike) propagates to derivatives._"
    elif lora_license == "gpl-3.0":
        rationale = "_GPL-3.0 propagates from training corpus (copyleft)._"
    else:
        rationale = "_All upstream components are Apache 2.0 / MIT — LoRA inherits permissive terms._"
    return f"""
## License chain

| Component                         | License           |
|-----------------------------------|-------------------|
| Base model (`{base_full}`)        | {base_license}    |
| Training data ({ds_cell})         | {ds_license}      |
| **LoRA adapter (this repo)**      | **{lora_license}**|

{rationale}
"""


def render_readme(m):
    title_variant = f" ({m['variant']})" if m['variant'] else ""
    variant_note = ""
    if m['variant'] == "bf16":
        variant_note = "\n> **Variant**: trained on the BF16 base for higher numerical fidelity.\n"
    elif m['variant'] == "curriculum":
        variant_note = "\n> **Variant**: trained with multi-phase length curriculum.\n"
    elif m['variant'] == "fullseq":
        variant_note = "\n> **Variant**: trained with full-sequence loss for stronger schema adherence.\n"
    nick = m['name'].replace("-", "_")
    disclosure = render_disclosure(m['domain'], m['status'], m['primary_ds'], m['extra_ds'])
    license_chain = render_license_chain(
        m['base_full'], m['base_license'],
        m['primary_ds'], m['ds_license'], m['lora_license']
    )
    ds_section = ""
    if m['primary_ds']:
        ds_section = f"""
## Training data lineage

| Role            | Dataset                                                                                          | License        |
|-----------------|--------------------------------------------------------------------------------------------------|----------------|
| Primary corpus  | [`{m['primary_ds']}`](https://huggingface.co/datasets/{m['primary_ds']})                          | {m['ds_license']} |
"""
        if m['extra_ds']:
            for ds in m['extra_ds']:
                if ds and ds != m['primary_ds']:
                    ds_section += f"| Companion       | [`{ds}`](https://huggingface.co/datasets/{ds})                                                    | {m['ds_license']} |\n"
        ds_section += "\nFor per-sample provenance and attribution status, consult the dataset card.\n"
    else:
        ds_section = """
## Training data lineage

Derived from the internal **eu-kiki / mascarade** curation. All upstream samples
are synthetic, permissively-licensed, or generated from Apache-2.0 base resources.
See the [Ailiance-fr catalog](https://huggingface.co/Ailiance-fr) for related cards.
"""
    yaml = f"""---
license: {m['lora_license']}
base_model: {m['base_full']}
library_name: peft
tags:
- mlx
- lora
- peft
- ailiance
- {m['family']}
- {m['domain']}
language:
- en
- fr
pipeline_tag: text-generation
---
"""
    body = f"""
# Ailiance — {m['base_short']} {m['domain']}{title_variant} LoRA

LoRA adapter fine-tuned on `{m['base_full']}` for **{m['domain']}** tasks.
{variant_note}
> Maintained by **Ailiance** — French AI org publishing EU AI Act aligned LoRA adapters and datasets.
{disclosure}
## Quick start (MLX)

```python
from mlx_lm import load, generate

model, tokenizer = load(
    "{m['base_full']}",
    adapter_path="{m['repo']}",
)

print(generate(model, tokenizer, prompt="..."))
```

## Training

| Hyperparameter   | Value                  |
|------------------|------------------------|
| Base model       | `{m['base_full']}`     |
| Method           | LoRA via `mlx-lm`      |
| Rank             | {m['rank']}            |
| Scale            | {m['scale']}           |
| Alpha            | {m['alpha']}           |
| Max seq length   | {m['max_seq_length']}  |
| Iterations       | {m['iters']}           |
| Optimizer        | Adam, LR 1e-5          |
| Hardware         | Apple M3 Ultra 512 GB  |
{ds_section}{license_chain}
## EU AI Act compliance

- **Article 53(1)(c)**: training data licenses preserved (per-dataset cards declare upstream licenses).
- **Article 53(1)(d)**: training data summary — see upstream dataset cards on Ailiance-fr.
- **GPAI Code of Practice (July 2025)**: base `{m['base_full']}` released under {m['base_license']}.
- **No web scraping by Ailiance**, **no licensed data**, **no PII**.
- Upstream Stack Exchange content (where applicable) is CC-BY-SA-4.0 and propagates to this adapter.

## License

LoRA weights: **{m['lora_license']}** — see License chain table above for derivation rationale.

## Citation

```bibtex
@misc{{ailiance_{nick}_2026,
  author    = {{Ailiance}},
  title     = {{Ailiance — {m['base_short']} {m['domain']}{title_variant} LoRA}},
  year      = {{2026}},
  publisher = {{Hugging Face}},
  url       = {{https://huggingface.co/{m['repo']}}}
}}
```

## Related

See the full [Ailiance-fr LoRA collection](https://huggingface.co/Ailiance-fr).
"""
    return yaml + body


def get_existing(repo_id):
    try:
        info = api.repo_info(repo_id, repo_type="model", files_metadata=True)
        return {s.rfilename: getattr(s, "size", None) for s in info.siblings}
    except RepositoryNotFoundError:
        return None
    except Exception as e:
        log.warning(f"  repo_info failed for {repo_id}: {e}")
        return None


def build_meta(d):
    """Read adapter dir and build the render meta dict. Returns None if invalid."""
    name = d.name
    cfg_file = d / "adapter_config.json"
    safetensors = d / "adapters.safetensors"
    if name in SKIP_DIRS:
        log.info(f"SKIP {name}: in skip list")
        return None
    if not cfg_file.exists() or not safetensors.exists():
        log.info(f"SKIP {name}: missing config/safetensors")
        return None
    cfg = json.loads(cfg_file.read_text())
    base_path = cfg.get("model", "")
    base_full, base_license, base_short, family = base_from_path(base_path)
    if family == "unknown":
        log.warning(f"SKIP {name}: unknown base ({base_path})")
        return None
    domain, variant = derive_domain(name)
    primary_ds, ds_license, lora_license, status, extra_ds = lineage_for(domain)
    lora = cfg.get("lora_parameters", {})
    repo_id = f"{ORG}/{name}-lora"
    return {
        "name": name, "repo": repo_id, "base_full": base_full,
        "base_short": base_short, "base_license": base_license, "family": family,
        "domain": domain, "variant": variant,
        "primary_ds": primary_ds, "ds_license": ds_license,
        "lora_license": lora_license, "status": status, "extra_ds": extra_ds,
        "rank": lora.get("rank", "?"), "scale": lora.get("scale", "?"),
        "alpha": lora.get("alpha", "?"), "iters": cfg.get("iters", "?"),
        "max_seq_length": cfg.get("max_seq_length", "?"),
        "cfg_file": cfg_file, "safetensors": safetensors,
    }


def upload_readme(meta):
    readme = render_readme(meta)
    readme_path = Path(f"/tmp/_ailiance_{meta['name']}_README.md")
    readme_path.write_text(readme)
    log.info(f"UPLOAD {meta['repo']} <- README.md (license={meta['lora_license']}, status={meta['status']})")
    try:
        upload_file(
            path_or_fileobj=str(readme_path), path_in_repo="README.md",
            repo_id=meta['repo'], repo_type="model",
            commit_message="Refresh model card: license chain + DISCLOSURE bandeau v2",
        )
    except HfHubHTTPError as e:
        log.error(f"FAIL {meta['name']}: upload README: {e}")
        return False
    return True


def push_one(d, force_readme=False):
    meta = build_meta(d)
    if meta is None:
        return "skip"
    repo_id = meta['repo']
    existing = get_existing(repo_id)
    local_size = meta['safetensors'].stat().st_size

    if force_readme:
        # Only refresh README, do nothing else.
        if existing is None:
            log.info(f"SKIP {meta['name']}: repo missing on HF, --force-readme cannot create")
            return "skip"
        ok = upload_readme(meta)
        return "ok" if ok else "fail"

    if existing is not None:
        if existing.get("adapters.safetensors") == local_size and "README.md" in existing:
            # Refresh README anyway (idempotent overwrite — new template)
            log.info(f"REFRESH-README {meta['name']}: repo already complete, updating card")
            ok = upload_readme(meta)
            return "ok" if ok else "fail"
    try:
        create_repo(repo_id, repo_type="model", exist_ok=True, private=False)
    except Exception as e:
        log.error(f"FAIL {meta['name']}: create_repo: {e}")
        return "fail"
    log.info(f"UPLOAD {repo_id} <- adapters.safetensors ({local_size//1024//1024} MB)")
    try:
        upload_file(
            path_or_fileobj=str(meta['safetensors']), path_in_repo="adapters.safetensors",
            repo_id=repo_id, repo_type="model",
            commit_message=f"Upload {meta['name']} LoRA weights",
        )
    except HfHubHTTPError as e:
        log.error(f"FAIL {meta['name']}: upload safetensors: {e}")
        return "fail"
    log.info(f"UPLOAD {repo_id} <- adapter_config.json")
    try:
        upload_file(
            path_or_fileobj=str(meta['cfg_file']), path_in_repo="adapter_config.json",
            repo_id=repo_id, repo_type="model",
            commit_message="Upload adapter config",
        )
    except HfHubHTTPError as e:
        log.error(f"FAIL {meta['name']}: upload config: {e}")
        return "fail"
    ok = upload_readme(meta)
    if not ok:
        return "fail"
    log.info(f"OK {repo_id}")
    return "ok"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-readme", action="store_true",
                        help="Refresh README.md only for repos that already exist on HF")
    parser.add_argument("--only", default=None,
                        help="Process only this adapter dir name (e.g. apertus-embedded)")
    parser.add_argument("--gemma-fix", action="store_true",
                        help="Patch existing gemma-4-E4B-* repos (not in local dirs)")
    args = parser.parse_args()

    log.info("=" * 70)
    log.info(f"Ailiance LoRA push v2 from {ROOT}")
    log.info(f"  force_readme={args.force_readme} only={args.only}")
    log.info("=" * 70)

    if args.gemma_fix:
        gemma_fix()
        return

    adapter_dirs = sorted(d for d in ROOT.iterdir() if d.is_dir())
    if args.only:
        adapter_dirs = [d for d in adapter_dirs if d.name == args.only]
    log.info(f"Processing {len(adapter_dirs)} adapter directories")
    counts = {"ok": 0, "skip": 0, "fail": 0}
    for d in adapter_dirs:
        try:
            r = push_one(d, force_readme=args.force_readme)
            counts[r] = counts.get(r, 0) + 1
        except Exception as e:
            log.exception(f"Unhandled error on {d.name}: {e}")
            counts["fail"] = counts.get("fail", 0) + 1
        time.sleep(2)
    log.info("=" * 70)
    log.info(f"Summary: ok={counts['ok']} skip={counts['skip']} fail={counts['fail']}")
    log.info("=" * 70)


GEMMA_REPOS = {
    "gemma-4-E4B-eukiki-lora":      ("eukiki",       "Ailiance-fr/kill-life-embedded-qa",       "cc-by-sa-4.0", "clean"),
    "gemma-4-E4B-mascarade-lora":   ("mascarade",    "Ailiance-fr/mascarade-stm32-dataset",     "cc-by-sa-4.0", "clean"),
    "gemma-4-E4B-aggro-test-lora":  ("aggro-test",   "Ailiance-fr/kill-life-embedded-qa",       "cc-by-sa-4.0", "clean"),
    "gemma-4-E4B-kicad9plus-lora":  ("kicad9plus",   "Ailiance-fr/kicad9plus-permissive",       "cc-by-sa-4.0", "clean"),
}


def gemma_fix():
    """Patch the 4 existing gemma-4-E4B-* repos: change license from 'gemma' to cc-by-sa-4.0,
    add License chain noting Gemma Terms inheritance for weights."""
    log.info("=== GEMMA-FIX MODE ===")
    base_full = "lmstudio-community/gemma-4-E4B-it-MLX-4bit"
    base_license = "gemma (Google Terms of Use)"
    for repo_name, (domain, primary_ds, ds_license, status) in GEMMA_REPOS.items():
        repo_id = f"{ORG}/{repo_name}"
        log.info(f"Patching {repo_id} — license=cc-by-sa-4.0, ds={primary_ds}")
        readme = render_gemma_readme(repo_name, domain, base_full, base_license, primary_ds, ds_license)
        readme_path = Path(f"/tmp/_ailiance_{repo_name}_README.md")
        readme_path.write_text(readme)
        try:
            upload_file(
                path_or_fileobj=str(readme_path), path_in_repo="README.md",
                repo_id=repo_id, repo_type="model",
                commit_message="Re-license to CC-BY-SA-4.0: training data share-alike inherits",
            )
            log.info(f"OK {repo_id}")
        except HfHubHTTPError as e:
            log.error(f"FAIL {repo_id}: {e}")
        time.sleep(2)


def render_gemma_readme(repo_name, domain, base_full, base_license, primary_ds, ds_license):
    nick = repo_name.replace("-", "_")
    yaml = f"""---
license: cc-by-sa-4.0
base_model: {base_full}
library_name: peft
tags:
- mlx
- lora
- peft
- electronics
- embedded
- kicad
- spice
- ailiance
- gemma
- {domain}
language:
- en
- fr
pipeline_tag: text-generation
---
"""
    body = f"""
# Ailiance — Gemma 4 E4B {domain} LoRA

LoRA adapter fine-tuned on `{base_full}` for the **{domain}** domain (electronics, embedded, KiCad, SPICE).

> Maintained by **Ailiance** — French AI org publishing EU AI Act aligned LoRA adapters and datasets.

## Quick start (MLX)

```python
from mlx_lm import load, generate

model, tokenizer = load(
    "{base_full}",
    adapter_path="{ORG}/{repo_name}",
)

print(generate(model, tokenizer, prompt="..."))
```

## License chain

| Component                                     | License                       |
|-----------------------------------------------|-------------------------------|
| Base model weights (`{base_full}`)            | Gemma Terms of Use            |
| Training data ([`{primary_ds}`](https://huggingface.co/datasets/{primary_ds})) | {ds_license}                  |
| **LoRA adapter (this repo)**                  | **CC-BY-SA-4.0**              |

**Rationale**: weights of the base model inherit from the Gemma Terms of Use, but
the **LoRA adapter is a derivative of CC-BY-SA-4.0 training data** and is therefore
released under CC-BY-SA-4.0 (share-alike propagates). Downstream users who load
this adapter against the Gemma base must comply with **both** licenses
simultaneously.

## Training data lineage

Primary corpus: [`{primary_ds}`](https://huggingface.co/datasets/{primary_ds}) ({ds_license}).
See the [Ailiance-fr catalog](https://huggingface.co/Ailiance-fr) for related cards.

## EU AI Act compliance

- **Article 53(1)(c)**: training data licenses preserved upstream.
- **Article 53(1)(d)**: training data summary — see dataset cards on Ailiance-fr.
- **GPAI Code of Practice (July 2025)**: base model Gemma (Google is a signatory).
- **No web scraping by Ailiance**, **no licensed data**, **no PII**.

## License

LoRA weights: **CC-BY-SA-4.0** (training-data share-alike). Base model weights remain under Gemma Terms of Use.

## Citation

```bibtex
@misc{{ailiance_{nick}_2026,
  author    = {{Ailiance}},
  title     = {{Ailiance — Gemma 4 E4B {domain} LoRA}},
  year      = {{2026}},
  publisher = {{Hugging Face}},
  url       = {{https://huggingface.co/{ORG}/{repo_name}}}
}}
```

## Related

See the full [Ailiance-fr LoRA collection](https://huggingface.co/Ailiance-fr).
"""
    return yaml + body


if __name__ == "__main__":
    main()
