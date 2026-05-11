#!/usr/bin/env python3
"""
Generate enriched README.md files for the 8 mascarade-* datasets on
electron-rare/HF following the EU AI Act Template (AI Office, July 2025)
and the legal audit identified on 2026-05-11.

This script is idempotent and reusable for future passes:
  - Reads the local .jsonl from /tmp/audit_redo/<short>/<file>
  - Computes accurate statistics (sample count, MB)
  - Picks one representative sample preserving an existing system+human+gpt
    triple where possible
  - Writes <short>_README.md alongside the .jsonl ready for `hf upload`

Run: python3 ~/scripts/gen_attribution_readmes.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path("/tmp/audit_redo")

# (short_id, hf_short, jsonl_filename, pretty_name, tags, citation_key)
DATASETS = [
    (
        "mascarade-stm32",
        "mascarade-stm32",
        "stm32_chat.jsonl",
        "Mascarade — STM32 & ARM Cortex-M Q&A",
        ["electronics", "embedded", "stm32", "arm", "cortex-m", "firmware",
         "hal", "cmsis", "freertos", "bare-metal"],
        "electron_rare_stm32_2026",
    ),
    (
        "mascarade-spice",
        "mascarade-spice",
        "spice_chat.jsonl",
        "Mascarade — SPICE & Analog Simulation Q&A",
        ["electronics", "spice", "simulation", "analog", "ngspice", "ltspice",
         "circuit-analysis", "masala-chai"],
        "electron_rare_spice_2026",
    ),
    (
        "mascarade-iot",
        "mascarade-iot",
        "iot_chat.jsonl",
        "Mascarade — IoT & Connected Devices Q&A",
        ["electronics", "embedded", "iot", "esp32", "wifi", "ble", "mqtt",
         "lorawan", "home-assistant"],
        "electron_rare_iot_2026",
    ),
    (
        "mascarade-power",
        "mascarade-power",
        "power_chat.jsonl",
        "Mascarade — Power Electronics Q&A",
        ["electronics", "embedded", "power-electronics", "dc-dc", "buck",
         "boost", "motor-control", "foc", "battery", "regulator"],
        "electron_rare_power_2026",
    ),
    (
        "mascarade-dsp",
        "mascarade-dsp",
        "dsp_chat.jsonl",
        "Mascarade — DSP & Signal Processing Q&A",
        ["electronics", "embedded", "dsp", "signal-processing", "fft", "fir",
         "iir", "audio", "filtering"],
        "electron_rare_dsp_2026",
    ),
    (
        "mascarade-emc",
        "mascarade-emc",
        "emc_chat.jsonl",
        "Mascarade — EMC & EMI Q&A",
        ["electronics", "embedded", "emc", "emi", "esd", "compliance",
         "ferrite", "shielding", "pcb-layout"],
        "electron_rare_emc_2026",
    ),
    (
        "mascarade-kicad",
        "mascarade-kicad",
        "kicad_chat.jsonl",
        "Mascarade — KiCad EDA Q&A",
        ["electronics", "embedded", "kicad", "eda", "schematic", "pcb",
         "footprint", "drc", "erc", "bom"],
        "electron_rare_kicad_2026",
    ),
    (
        "mascarade-embedded",
        "mascarade-embedded",
        "embedded_chat.jsonl",
        "Mascarade — Embedded Systems Q&A",
        ["electronics", "embedded", "rtos", "drivers", "linux", "yocto",
         "buildroot", "device-tree", "bootloader"],
        "electron_rare_embedded_2026",
    ),
]

# Datasets with the critical SE/EEVblog scraping disclosure.
DISCLOSURE_DATASETS = {"mascarade-power", "mascarade-dsp",
                       "mascarade-emc", "mascarade-kicad"}

AUDIT_LINK = (
    "https://github.com/electron-rare/electron-bench/blob/main/"
    "docs/audit_kicad9plus.md"
)


def stats_for(jsonl_path: Path) -> tuple[int, float, dict]:
    """Return (n_samples, size_mb, first_sample_dict)."""
    n = 0
    first = None
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            n += 1
            if first is None:
                try:
                    first = json.loads(line)
                except json.JSONDecodeError:
                    first = None
    size_mb = jsonl_path.stat().st_size / (1024 * 1024)
    return n, size_mb, first or {}


def truncate_value(text: str, max_len: int = 800) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def render_sample(sample: dict) -> str:
    """Render the first sample as compact JSON, truncating long values for
    README readability while keeping the structure intact."""
    if not sample or "conversations" not in sample:
        return "{ /* sample structure unavailable */ }"
    convs = []
    for turn in sample.get("conversations", []):
        convs.append({
            "from": turn.get("from"),
            "value": truncate_value(turn.get("value", "")),
        })
    return json.dumps({"conversations": convs}, ensure_ascii=False, indent=2)


# -----------------------------------------------------------------------------
# Per-dataset attribution / source paragraphs
# -----------------------------------------------------------------------------

DESCRIPTIONS = {
    "mascarade-stm32": (
        "Q&A bilingue (FR/EN) sur le firmware STM32 et ARM Cortex-M : drivers "
        "HAL/LL, CMSIS, FreeRTOS, peripherals (UART, SPI, I2C, DMA, ADC, "
        "timers), bare-metal register-level, et assembleur ARM Thumb-2. "
        "Couvre les familles STM32F0/F1/F4/F7/G0/G4/H7/L0/L4."
    ),
    "mascarade-spice": (
        "Q&A bilingue (FR/EN) sur la simulation SPICE et l'analyse de "
        "circuits analogiques : ngspice, LTspice, modèles MOSFET/BJT, "
        "topologies analogiques, ampli-op, filtres actifs, sources de "
        "courant, polarisation."
    ),
    "mascarade-iot": (
        "Q&A bilingue (FR/EN) sur l'IoT et les objets connectés : ESP32, "
        "Wi-Fi, BLE, LoRaWAN, MQTT, intégration Home Assistant, drivers de "
        "capteurs, et gestion d'énergie pour devices battery-powered."
    ),
    "mascarade-power": (
        "Q&A bilingue (FR/EN) sur l'électronique de puissance : "
        "convertisseurs DC-DC (buck, boost, buck-boost, flyback), commande "
        "moteur (FOC, DTC, BLDC/PMSM), onduleurs, drivers de grille, gestion "
        "de batterie, et correction du facteur de puissance."
    ),
    "mascarade-dsp": (
        "Q&A bilingue (FR/EN) sur le traitement numérique du signal : FFT, "
        "filtres FIR/IIR, fenêtrage, convolution, audio, filtrage adaptatif, "
        "implémentation embarquée sur ARM Cortex-M et DSP TI/ADI."
    ),
    "mascarade-emc": (
        "Q&A bilingue (FR/EN) sur la compatibilité électromagnétique : "
        "conception EMC/EMI, ESD, ferrites, blindage, layout PCB, "
        "qualification CISPR / IEC 61000, et debug en chambre anéchoïque."
    ),
    "mascarade-kicad": (
        "Q&A bilingue (FR/EN) sur KiCad EDA : schematic capture, layout PCB, "
        "footprints, symboles, ERC/DRC, BOM, scripting Python, plugins, et "
        "fabrication outputs (Gerber, drill, pick-and-place)."
    ),
    "mascarade-embedded": (
        "Q&A bilingue (FR/EN) sur les systèmes embarqués génériques : RTOS "
        "(FreeRTOS, Zephyr), Linux embarqué (Yocto, Buildroot), device tree, "
        "bootloaders (U-Boot, BL31), drivers noyau, et toolchains croisées."
    ),
}


SOURCE_SECTIONS = {
    "mascarade-stm32": """\
### Publicly available datasets
None (no third-party datasets reused).

### Web scraping
None.

### Synthetically generated
- **100% generated by LLM** in the *electron-rare* training pipeline. \
Generator details preserved per-sample in `metadata.generator` when present; \
otherwise consult the original training pipeline.

### Licensed data
None.""",

    "mascarade-spice": """\
### Publicly available datasets
- **Derived from [Masala-CHAI dataset](https://github.com/jitendra-bhandari/Masala-CHAI)** \
([arXiv:2411.14299](https://arxiv.org/abs/2411.14299), CC-BY-4.0). \
Original Masala-CHAI is itself derived from textbooks — verify upstream \
copyright before commercial use.

### Web scraping
None directly performed by this dataset; upstream Masala-CHAI used textbook \
sources.

### Synthetically generated
- Light LLM augmentation (rephrasing, FR translation) on top of the \
Masala-CHAI base.

### Licensed data
None.""",

    "mascarade-iot": """\
### Publicly available datasets
- **~33% from [acon96/Home-Assistant-Requests](https://huggingface.co/datasets/acon96/Home-Assistant-Requests) (MIT License)**.

### Web scraping
None.

### Synthetically generated
- **~67%** generated by LLM in the *electron-rare* training pipeline \
(ESP32 / BLE / MQTT / LoRaWAN scenarios).

### Licensed data
None.""",

    "mascarade-power": """\
### Publicly available datasets
None.

### Web scraping
- **~30% scraped from [Stack Exchange Electronics](https://electronics.stackexchange.com/) \
(CC-BY-SA-4.0)** — per-sample URL + author attribution **incomplete** in legacy \
collection. Remediation in progress.
- **~30% scraped from [EEVblog Forum](https://www.eevblog.com/)** \
(public domain per forum rules).

### Synthetically generated
- **~40%** generated by LLM (power-electronics calculations, component sizing).

### Licensed data
None.""",

    "mascarade-dsp": """\
### Publicly available datasets
None.

### Web scraping
- **~37% scraped from [Stack Exchange Signal Processing / Electronics] \
(CC-BY-SA-4.0)** — including 51 explicitly cited references — per-sample \
URL + author attribution **incomplete** in legacy collection. Remediation in \
progress.

### Synthetically generated
- **~63%** generated by LLM (FFT, FIR/IIR filter design, embedded DSP code).

### Licensed data
None.""",

    "mascarade-emc": """\
### Publicly available datasets
None.

### Web scraping
- **~30% scraped from [EEVblog Forum](https://www.eevblog.com/)** \
(public domain per forum rules).
- **Additional samples scraped from [Stack Exchange Electronics] \
(CC-BY-SA-4.0)** — per-sample URL + author attribution **incomplete** in \
legacy collection. Remediation in progress.

### Synthetically generated
- Remaining samples generated by LLM (EMC/EMI debugging scenarios, layout \
guidelines, CISPR test interpretation).

### Licensed data
None.""",

    "mascarade-kicad": """\
### Publicly available datasets
None.

### Web scraping
- **~31% scraped from [Stack Exchange Electronics] \
(CC-BY-SA-4.0)** — per-sample URL + author attribution **incomplete** in \
legacy collection. Remediation in progress.

### Synthetically generated
- **~69%** generated by LLM (KiCad workflow Q&A, scripting, footprint advice).

### Licensed data
None.""",

    "mascarade-embedded": """\
### Publicly available datasets
None.

### Web scraping
- **~10–15% scraped from [Stack Exchange Electronics] (CC-BY-SA-4.0) and \
[EEVblog Forum] (public domain)** — per-sample URL + author attribution \
**incomplete** for the Stack Exchange portion (legacy collection, see warning \
on the `mascarade-power`/`-dsp`/`-emc`/`-kicad` companions).

### Synthetically generated
- **~85%** generated by LLM (RTOS, device tree, drivers, bootloader \
scenarios).

### Licensed data
None.""",
}


COPYRIGHT_NOTES = {
    "mascarade-stm32": """\
- Synthetic LLM outputs: belong to dataset author per OpenAI/Anthropic ToS.""",

    "mascarade-spice": """\
- Masala-CHAI base content: CC-BY-4.0 (attribution preserved above).
- Synthetic LLM augmentations: belong to dataset author per OpenAI/Anthropic ToS.
- Verify upstream textbook copyright before commercial use.""",

    "mascarade-iot": """\
- acon96/Home-Assistant-Requests samples: MIT License (attribution preserved \
above).
- Synthetic LLM outputs: belong to dataset author per OpenAI/Anthropic ToS.""",

    "mascarade-power": """\
- Stack Exchange content: CC-BY-SA-4.0 (compatible upgrade ; full attribution \
remediation in progress).
- EEVblog content: public domain per forum rules.
- Synthetic LLM outputs: belong to dataset author per OpenAI/Anthropic ToS.""",

    "mascarade-dsp": """\
- Stack Exchange content: CC-BY-SA-4.0 (compatible upgrade ; full attribution \
remediation in progress).
- Synthetic LLM outputs: belong to dataset author per OpenAI/Anthropic ToS.""",

    "mascarade-emc": """\
- Stack Exchange content: CC-BY-SA-4.0 (compatible upgrade ; full attribution \
remediation in progress).
- EEVblog content: public domain per forum rules.
- Synthetic LLM outputs: belong to dataset author per OpenAI/Anthropic ToS.""",

    "mascarade-kicad": """\
- Stack Exchange content: CC-BY-SA-4.0 (compatible upgrade ; full attribution \
remediation in progress).
- Synthetic LLM outputs: belong to dataset author per OpenAI/Anthropic ToS.""",

    "mascarade-embedded": """\
- Stack Exchange content: CC-BY-SA-4.0 (compatible upgrade ; full attribution \
remediation in progress for the ~10–15% scraped portion).
- EEVblog content: public domain per forum rules.
- Synthetic LLM outputs: belong to dataset author per OpenAI/Anthropic ToS.""",
}


def render_disclosure_banner(short: str) -> str:
    if short not in DISCLOSURE_DATASETS:
        return ""
    return f"""\

> [!WARNING]
> **PARTIAL ATTRIBUTION DISCLOSURE**
>
> This dataset includes a substantial fraction of samples scraped from
> **Stack Exchange Electronics** (CC-BY-SA-4.0) — and for some topics from
> **EEVblog Forum** (public domain) — for which full per-sample URL+author
> attribution is **currently incomplete**. Stack Exchange CC-BY-SA-4.0
> requires source URL + author preserved for each post.
>
> **Status**: this is being remediated — see
> [audit report]({AUDIT_LINK}) for legal context.
>
> **For DMCA-clean alternatives**, use:
> - [`kill-life-embedded-qa`](https://huggingface.co/datasets/electron-rare/kill-life-embedded-qa) (100% original)
> - [`kicad9plus-permissive`](https://huggingface.co/datasets/electron-rare/kicad9plus-permissive) (KiCad sch, fully attributed)
>
> If you author content from Stack Exchange and find your post in this
> dataset, contact `c.saillant@gmail.com` for removal or attribution. We
> honor [Article 4(3) DSM Directive](https://eur-lex.europa.eu/eli/dir/2019/790/oj) opt-outs.
"""


def render_synthetic_note(short: str) -> str:
    if short == "mascarade-stm32":
        return ""
    return ""


def build_readme(short: str, hf_short: str, jsonl_name: str,
                 pretty: str, tags: list[str], cite_key: str) -> str:
    jsonl_path = ROOT / short / jsonl_name
    n, size_mb, sample = stats_for(jsonl_path)

    tags_yaml = "\n".join(f"- {t}" for t in tags)
    sample_block = render_sample(sample)
    disclosure = render_disclosure_banner(short)
    description = DESCRIPTIONS[short]
    sources = SOURCE_SECTIONS[short]
    copy_notes = COPYRIGHT_NOTES[short]
    audit_link = AUDIT_LINK

    return f"""---
license: cc-by-sa-4.0
language:
- fr
- en
pretty_name: "{pretty}"
task_categories:
- text-generation
- question-answering
tags:
{tags_yaml}
size_categories:
- 1K<n<10K
---

# {pretty}
{disclosure}
## Description

{description}

Ce dataset fait partie de la famille **Mascarade**, un corpus thématique destiné au fine-tuning LoRA de modèles compacts (cible : Gemma-3n-E4B et équivalents) pour des assistants spécialisés en électronique embarquée.

Format : JSONL « ShareGPT-style » avec un tour `system` (rôle d'expert), un tour `human` (question) et un tour `gpt` (réponse complète, code compilable, schémas ASCII si pertinent).

## Data sources (EU AI Act Template — AI Office, July 2025)

{sources}

## Sample format

```json
{sample_block}
```

## Statistics

| Métrique     | Valeur            |
|--------------|-------------------|
| Total samples | **{n:,}** |
| Size         | **{size_mb:.2f} MB** |
| Format       | `jsonl` (ShareGPT conversations) |
| Languages    | French / English mix |
| File         | `{jsonl_name}` |

## Usage

```python
from datasets import load_dataset

ds = load_dataset("electron-rare/{hf_short}-dataset")
print(ds["train"][0]["conversations"])
```

Pour un fine-tuning ShareGPT-style direct (axolotl, unsloth, mlx-lm) :

```yaml
# axolotl config
datasets:
  - path: electron-rare/{hf_short}-dataset
    type: sharegpt
    conversation: chatml
```

## Licenses applied

This aggregated dataset is released under **CC-BY-SA-4.0**. Per-sample original licenses preserved in `metadata.license` when known.

## Copyright considerations

{copy_notes}

**Opt-out**: contact `c.saillant@gmail.com`. We respect TDMRep, robots.txt, and noai/noimageai signals. We honor [Article 4(3) DSM Directive](https://eur-lex.europa.eu/eli/dir/2019/790/oj) opt-outs.

## License & EU AI Act

**CC-BY-SA-4.0** (attribution + sharealike).

Données collectées et générées dans le cadre du projet **electron-rare** (fine-tuning LoRA sur Gemma-3n-E4B pour applications électronique embarquée).

Compatible **EU AI Act** : voir les signataires du *GPAI Code of Practice* (Anthropic, Mistral, Google) et la documentation transparence du projet : [electron-bench](https://github.com/electron-rare/electron-bench).

Audit log: see [`docs/audit_kicad9plus.md`]({audit_link}) for the legal-attribution audit performed on 2026-05-11.

## Citation

```bibtex
@dataset{{{cite_key},
  author    = {{electron-rare}},
  title     = {{ {pretty} }},
  year      = {{2026}},
  publisher = {{Hugging Face}},
  license   = {{CC-BY-SA-4.0}},
  url       = {{https://huggingface.co/datasets/electron-rare/{hf_short}-dataset}}
}}
```

## Related datasets

Famille `electron-rare/mascarade-*` couvrant : STM32, SPICE, KiCad, IoT, Power, DSP, EMC, embedded.

- [mascarade-stm32-dataset](https://huggingface.co/datasets/electron-rare/mascarade-stm32-dataset)
- [mascarade-spice-dataset](https://huggingface.co/datasets/electron-rare/mascarade-spice-dataset)
- [mascarade-kicad-dataset](https://huggingface.co/datasets/electron-rare/mascarade-kicad-dataset)
- [mascarade-iot-dataset](https://huggingface.co/datasets/electron-rare/mascarade-iot-dataset)
- [mascarade-power-dataset](https://huggingface.co/datasets/electron-rare/mascarade-power-dataset)
- [mascarade-dsp-dataset](https://huggingface.co/datasets/electron-rare/mascarade-dsp-dataset)
- [mascarade-emc-dataset](https://huggingface.co/datasets/electron-rare/mascarade-emc-dataset)
- [mascarade-embedded-dataset](https://huggingface.co/datasets/electron-rare/mascarade-embedded-dataset)
- [kill-life-embedded-qa](https://huggingface.co/datasets/electron-rare/kill-life-embedded-qa) — Q&A spécifique au projet Kill_LIFE
- [kicad9plus-sch-corpus](https://huggingface.co/datasets/electron-rare/kicad9plus-sch-corpus) — corpus de schémas KiCad 9+
"""


def main() -> int:
    if not ROOT.exists():
        print(f"ERROR: missing {ROOT} — download datasets first.",
              file=sys.stderr)
        return 1
    for short, hf_short, jsonl_name, pretty, tags, cite_key in DATASETS:
        ds_dir = ROOT / short
        jsonl_path = ds_dir / jsonl_name
        if not jsonl_path.exists():
            print(f"SKIP: {jsonl_path} missing")
            continue
        readme = build_readme(short, hf_short, jsonl_name, pretty, tags,
                              cite_key)
        out_path = ROOT / f"{short}_README.md"
        out_path.write_text(readme, encoding="utf-8")
        print(f"WROTE {out_path} ({len(readme):,} chars, "
              f"sample-count derived from {jsonl_name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
